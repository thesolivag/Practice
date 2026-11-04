"""Small per-user trading journals and incrementally revealed replay windows."""
import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import re
import time
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from fastapi import APIRouter,Body,Depends,HTTPException
from slk import instruments,replay_cache,tenancy

MAX_JOURNAL=200
MAX_JOURNAL_BYTES=8*1024*1024
MAX_NOTES=2000
KINDS={'bias','entry','watch','watch_event','event','manual'}
REPLAY_TIMEFRAMES=('H1','H2','H3','H4','D','W')
REPLAY_MIN_START=1515974400  # 2018-01-15 UTC; leaves fourteen days of context
CONTEXT_DAYS=14
FORWARD_DAYS=7
HISTORY_PAGE_DAYS=21  # Bound every broker request; shared cache remains 16 MiB.
NY=ZoneInfo('America/New_York')


def epoch(value):
    if isinstance(value,(int,float)):return int(value)
    if isinstance(value,datetime):return int(value.replace(tzinfo=timezone.utc).timestamp()) if value.tzinfo is None else int(value.timestamp())
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return int((parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed).timestamp())


def _finite_price(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<value<1e12


def _event_details(row,kind,anchor):
    """Only frozen delivered-event payloads produce model/level markers.

    Legacy bias/entry rows are mutable lifecycle records, not historical alert
    snapshots; their current target/result must not leak into an earlier replay.
    """
    event={'kind':kind,'id':int(row['id']),'time':anchor,'pair':row['pair'],
           'snapshot':kind=='watch_event','label':f"{row['pair']} · {kind} #{row['id']}"}
    markers=[]
    if kind=='watch_event':
        payload=row.get('event_payload') or '{}'
        try:payload=json.loads(payload) if isinstance(payload,(str,bytes)) else payload
        except (ValueError,TypeError):payload={}
        if not isinstance(payload,dict):payload={}
        for key in ('model','timeframe','side'):
            value=row.get(key)
            if isinstance(value,str):event[key]=value[:32]
        candidates=[('level',row.get('level'),'Watched level'),('close',payload.get('close'),'Trigger close')]
        matches=payload.get('matches')
        if isinstance(matches,list) and matches and isinstance(matches[0],dict):
            candidates += [('reference_level',matches[0].get('reference_level'),'Reference level'),
                           ('pattern_level',matches[0].get('pattern_level'),'Pattern level')]
        for key,value,label in candidates:
            if _finite_price(value):markers.append({'time':anchor,'price':float(value),'label':label,'kind':key})
    return event,markers


def source(db,uid,kind,ident,now=None,require_anchor=True):
    if not isinstance(kind,str) or kind not in {'bias','entry','watch','watch_event','event'} or not isinstance(ident,int) or isinstance(ident,bool) or not 1<=ident<2**63:
        raise HTTPException(422,'Choose an owned alert or entry.')
    kind='watch_event' if kind=='event' else kind
    with tenancy.scope(uid):
        if kind=='bias':rows=db.query('SELECT * FROM bias WHERE id=%s',(ident,))
        elif kind=='entry':rows=db.query('SELECT * FROM entries WHERE id=%s',(ident,))
        elif kind=='watch_event':rows=db.query('SELECT * FROM manual_alert_events WHERE id=%s AND user_id=%s',(ident,uid))
        else:rows=db.query('SELECT * FROM manual_alerts WHERE id=%s AND user_id=%s',(ident,uid))
    if not rows:raise HTTPException(404,'Source not found.')
    r=rows[0]
    anchor=(r.get('confirm_time') if kind=='bias' else (r.get('alerted_at') or r.get('created_at')) if kind=='entry' else r.get('event_time'))
    if anchor is None and not require_anchor:anchor=r.get('created_at') or int(now or time.time())
    if anchor is None:raise HTTPException(409,'This alert has no confirmed replay time yet.')
    anchor=epoch(anchor)
    if anchor>int(now or time.time()):raise HTTPException(409,'Source time has not happened yet.')
    event,markers=_event_details(r,kind,anchor)
    return {'mode':'alert','kind':kind,'id':int(r['id']),'pair':r['pair'],'anchor':anchor,
            'label':event['label'],'event':event,'markers':markers}


def known_pairs():
    known={r['key'] for r in instruments.deriv_symbols()}
    try:known.update(r['key'] for r in json.loads((Path(__file__).resolve().parents[1]/'data'/'broker_symbols.json').read_text())['symbols'])
    except (FileNotFoundError,KeyError):pass
    return known


def replay_timeframe(value):
    if not isinstance(value,str) or value not in REPLAY_TIMEFRAMES:
        raise HTTPException(422,'Replay timeframes are H1, H2, H3, H4, D and W. Minute bars cannot be reconstructed from H1 history.')
    return value


def price_source(body,now=None):
    now=int(time.time() if now is None else now)
    pair=body.get('pair')
    if not isinstance(pair,str) or pair.upper() not in known_pairs():raise HTTPException(422,'Choose a known broker instrument.')
    value=body.get('start')
    try:
        if isinstance(value,bool) or not isinstance(value,(str,int,float)):raise ValueError()
        if isinstance(value,str):
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            if parsed.tzinfo is None:raise ValueError()
            start=int(parsed.timestamp())
        else:
            if not math.isfinite(value) or int(value)!=value:raise ValueError()
            start=int(value)
    except (ValueError,TypeError,OverflowError):raise HTTPException(422,'Choose a UTC start date/time or an epoch timestamp.') from None
    if not REPLAY_MIN_START<=start<=now//3600*3600:
        raise HTTPException(422,'Replay start must be from 2018-01-15 through the latest closed hour. Retained history varies by instrument.')
    return {'mode':'price','pair':pair.upper(),'anchor':start,'event':None,'markers':[],
            'label':pair.upper()+' · price replay'}


def clean_journal(body,partial=False):
    allowed={'source_kind','source_id','pair','side','entry','stop','target','result_r','outcome','notes'}
    if set(body)-allowed:raise HTTPException(422,'Unknown journal fields.')
    out={}
    for key in ('entry','stop','target','result_r'):
        if key not in body:continue
        value=body[key]
        if value in (None,''):out[key]=None;continue
        if isinstance(value,bool):raise HTTPException(422,'Journal prices/results must be finite numbers.')
        try:value=float(value)
        except (ValueError,TypeError):raise HTTPException(422,'Journal prices/results must be finite numbers.') from None
        if not math.isfinite(value) or (key!='result_r' and not 0<value<1e12) or (key=='result_r' and abs(value)>10000):
            raise HTTPException(422,'Journal price/result is out of range.')
        out[key]=value
    if 'notes' in body:
        if not isinstance(body['notes'],str) or len(body['notes'])>MAX_NOTES:raise HTTPException(422,'Notes must be text up to 2000 characters.')
        out['notes']=body['notes']
    if 'outcome' in body:
        if not isinstance(body['outcome'],str) or body['outcome'] not in {'OPEN','WIN','LOSS','BREAKEVEN','CLOSED'}:raise HTTPException(422,'Invalid journal outcome.')
        out['outcome']=body['outcome']
    if 'side' in body:
        if not isinstance(body['side'],str) or body['side'] not in {'BUY','SELL'}:raise HTTPException(422,'Invalid journal side.')
        out['side']=body['side']
    if not partial:
        kind=body.get('source_kind','manual')
        if not isinstance(kind,str) or kind not in KINDS:raise HTTPException(422,'Invalid journal source.')
        out.update(source_kind=kind,source_id=body.get('source_id'),pair=str(body.get('pair','')).upper())
        out.setdefault('side','BUY');out.setdefault('notes','');out.setdefault('outcome','OPEN')
        for key in ('entry','stop','target','result_r'):out.setdefault(key,None)
    elif any(k in body for k in ('source_kind','source_id','pair')):
        raise HTTPException(422,'The journal source cannot be changed.')
    return out


def write_journal(db,uid,values,ident=None):
    """Global byte cap and per-user row cap checked under one short advisory lock."""
    conn=db.connect();now=int(time.time());locked=False
    try:
        with conn.cursor() as c:
            c.execute("SELECT GET_LOCK('slk_journal_write',2) AS ok");locked=bool(c.fetchone()['ok'])
            if not locked:raise HTTPException(429,'Journal is busy; try again shortly.')
            conn.begin()
            old={}
            if ident is not None:
                c.execute('SELECT * FROM trade_journal WHERE id=%s AND user_id=%s FOR UPDATE',(ident,uid));old=c.fetchone()
                if not old:raise HTTPException(404,'Journal entry not found.')
            else:
                c.execute('SELECT COUNT(*) AS n FROM trade_journal WHERE user_id=%s',(uid,))
                if int(c.fetchone()['n'])>=MAX_JOURNAL:raise HTTPException(422,'Journal limit is 200 entries. Remove an older entry first.')
            c.execute('SELECT COALESCE(SUM(OCTET_LENGTH(notes)+256),0) AS n FROM trade_journal')
            total=int(c.fetchone()['n'])
            growth=len(values.get('notes',old.get('notes','')).encode())-(len(old.get('notes','').encode()) if old else 0)+(0 if old else 256)
            if total+growth>MAX_JOURNAL_BYTES:raise HTTPException(507,'Journal storage is full. Remove older notes or entries.')
            if ident is None:
                cols=['user_id',*values,'created_at','updated_at']
                c.execute('INSERT INTO trade_journal('+','.join(cols)+') VALUES('+','.join(['%s']*len(cols))+')',[uid,*values.values(),now,now]);ident=c.lastrowid
            elif values:
                c.execute('UPDATE trade_journal SET '+','.join(k+'=%s' for k in values)+',updated_at=%s WHERE id=%s AND user_id=%s',[*values.values(),now,ident,uid])
            conn.commit()
            c.execute('SELECT * FROM trade_journal WHERE id=%s AND user_id=%s',(ident,uid));return c.fetchone()
    except Exception:
        conn.rollback();raise
    finally:
        try:
            if locked:
                with conn.cursor() as c:c.execute("SELECT RELEASE_LOCK('slk_journal_write')")
        finally:conn.close()


def _token(payload):
    key=os.environ.get('TELEGRAM_BOT_TOKEN','')
    if not key:raise HTTPException(503,'Replay signing is not configured.')
    data=base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).decode().rstrip('=')
    return data+'.'+hmac.new(key.encode(),('replay:'+data).encode(),hashlib.sha256).hexdigest()


def _read_token(value,uid):
    try:
        if not isinstance(value,str) or len(value)>1200:raise ValueError()
        data,signature=value.split('.')
        p=json.loads(base64.urlsafe_b64decode(data+'='*(-len(data)%4)))
        if not isinstance(p,dict) or not hmac.compare_digest(_token(p),value):raise ValueError()
        base={'version','user','mode','pair','anchor','revealed','timeframe','expires'}
        expected=base|({'kind','id'} if p.get('mode')=='alert' else set())
        if set(p)!=expected or p['version']!=2 or p['mode'] not in ('alert','price'):raise ValueError()
        for key in ('user','anchor','revealed','expires'):
            if not isinstance(p[key],int) or isinstance(p[key],bool):raise ValueError()
        if p['user']!=uid or p['expires']<time.time() or p['expires']>time.time()+3601:raise ValueError()
        if not isinstance(p['pair'],str) or not re.fullmatch('[A-Z0-9]{3,12}',p['pair']):raise ValueError()
        if not isinstance(p['timeframe'],str) or p['timeframe'] not in REPLAY_TIMEFRAMES:raise ValueError()
        now=int(time.time())
        if not 0<p['anchor']<=p['revealed']<=now:raise ValueError()
        if p['mode']=='price' and p['anchor']<REPLAY_MIN_START:raise ValueError()
        if p['mode']=='alert' and (not isinstance(p['kind'],str) or p['kind'] not in {'bias','entry','watch','watch_event'} or not isinstance(p['id'],int) or isinstance(p['id'],bool) or not 1<=p['id']<2**63):raise ValueError()
        return p
    except (KeyError,ValueError,TypeError,binascii.Error,UnicodeDecodeError,json.JSONDecodeError,OverflowError):raise HTTPException(403,'Invalid or expired replay cursor.') from None


def _cursor_source(db,uid,cursor):
    if cursor['mode']=='price':
        src=price_source({'pair':cursor['pair'],'start':cursor['anchor']})
    else:
        src=source(db,uid,cursor['kind'],cursor['id'])
    if src['anchor']!=cursor['anchor'] or src['pair']!=cursor['pair']:
        raise HTTPException(409,'Source changed. Open a new replay.')
    return src


def _bucket(t,tf,pair):
    if tf=='H1':return t,t+3600
    utc_market=instruments.is_deriv(pair)
    continuous_crypto=not utc_market and instruments.market_category(pair)=='Cryptocurrencies'
    wall=datetime.fromtimestamp(t,timezone.utc)
    wall=wall.replace(tzinfo=None) if utc_market else wall.astimezone(NY).replace(tzinfo=None)+timedelta(hours=7)
    if tf.startswith('H'):
        hours=int(tf[1:]);start=wall.replace(hour=wall.hour//hours*hours,minute=0,second=0,microsecond=0);end=start+timedelta(hours=hours)
    else:
        start=wall.replace(hour=0,minute=0,second=0,microsecond=0)
        if tf=='W':start-=timedelta(days=start.weekday())
        end=start+timedelta(days=(7 if utc_market or continuous_crypto else 5) if tf=='W' else 1)
    if utc_market:return int(start.replace(tzinfo=timezone.utc).timestamp()),int(end.replace(tzinfo=timezone.utc).timestamp())
    def ny_epoch(wall):
        # Match the scanner's ambiguous='raise'/nonexistent='raise' policy.
        # In a continuous crypto weekend, omit uncertain DST-edge Hn bars.
        first=wall.replace(tzinfo=NY,fold=0);second=wall.replace(tzinfo=NY,fold=1)
        if first.utcoffset()!=second.utcoffset() or first.astimezone(timezone.utc).astimezone(NY).replace(tzinfo=None)!=wall:
            raise ValueError('Ambiguous broker candle edge')
        return int(first.timestamp())
    return ny_epoch(start-timedelta(hours=7)),ny_epoch(end-timedelta(hours=7))


def _expected_hour(t,pair,continuous=None):
    if continuous is None:continuous=instruments.deriv_continuous(pair) if instruments.is_deriv(pair) else instruments.market_category(pair)=='Cryptocurrencies'
    if continuous:return True
    ny=datetime.fromtimestamp(t,timezone.utc).astimezone(NY)
    return not (ny.weekday()==5 or (ny.weekday()==4 and ny.hour>=17) or (ny.weekday()==6 and ny.hour<17))


def completed_closes(rows,tf,pair,limit):
    """Determine calendar completion times from timestamps, never future OHLC."""
    groups={}
    continuous=instruments.deriv_continuous(pair) if instruments.is_deriv(pair) else instruments.market_category(pair)=='Cryptocurrencies'
    for row in rows:
        t=int(row[0])
        if t+3600>limit:continue
        try:a,b=_bucket(t,tf,pair)
        except ValueError:continue
        if a<=t<b and b<=limit:groups.setdefault((a,b),set()).add(t)
    out=[]
    for (a,b),have in sorted(groups.items()):
        if tf!='H1':
            expected={t for t in range(a,b,3600) if _expected_hour(t,pair,continuous)}
            if not expected or expected!=have:continue
        out.append((a,b))
    return out


def aggregate_replay(rows,tf,pair,clock):
    """Filter at the replay clock before aggregation; omit partial/gapped bins."""
    tf=replay_timeframe(tf)
    visible=[r for r in rows if int(r[0])+3600<=clock]
    complete=set(completed_closes(visible,tf,pair,clock));groups={}
    for row in visible:
        try:key=_bucket(int(row[0]),tf,pair)
        except ValueError:continue
        if key in complete:groups.setdefault(key,[]).append(row)
    out=[]
    for (a,b),group in sorted(groups.items()):
        group=sorted(group,key=lambda r:r[0])
        out.append({'time':a,'end':b,'open':group[0][1],'high':max(r[2] for r in group),
                    'low':min(r[3] for r in group),'close':group[-1][4]})
    return out


def _bars(rows):
    return [dict(zip(('time','open','high','low','close'),row)) for row in rows]


def queue_replay(db,uid,pair,lo,hi,now):
    conn=db.connect();locked=False
    try:
        with conn.cursor() as c:
            c.execute("SELECT GET_LOCK('slk_replay_queue',2) AS ok");locked=bool(c.fetchone()['ok'])
            if not locked:raise HTTPException(429,'Replay queue is busy. Try again shortly.')
            c.execute('DELETE FROM replay_requests WHERE updated_at<%s',(now-replay_cache.RETENTION,))
            c.execute('SELECT id FROM replay_requests WHERE user_id=%s AND pair=%s AND lo=%s AND hi=%s',(uid,pair,lo,hi));old=c.fetchone()
            c.execute("SELECT COUNT(*) AS n FROM replay_requests WHERE user_id=%s AND status='QUEUED'",(uid,))
            if int(c.fetchone()['n'])>=20 and not old:raise HTTPException(429,'Replay queue limit reached. Wait for the next hourly scan.')
            c.execute('SELECT COUNT(*) AS n FROM replay_requests')
            if int(c.fetchone()['n'])>=10000 and not old:raise HTTPException(429,'Replay request storage is full. Try again later.')
            c.execute("INSERT INTO replay_requests(user_id,pair,lo,hi,status,created_at,updated_at) VALUES(%s,%s,%s,%s,'QUEUED',%s,%s) ON DUPLICATE KEY UPDATE status='QUEUED',updated_at=VALUES(updated_at)",(uid,pair,lo,hi,now,now))
        conn.commit()
    finally:
        try:
            if locked:
                with conn.cursor() as c:c.execute("SELECT RELEASE_LOCK('slk_replay_queue')")
        finally:conn.close()


def _latest_possible_close(tf,pair,now):
    """Latest scheduled completed bucket (missing history is retryable, not EOF)."""
    t=now//3600*3600-3600
    for _ in range(24*9):
        if _expected_hour(t,pair):
            try:
                _,end=_bucket(t,tf,pair)
                if end<=now:return end
            except ValueError:pass
        t-=3600
    return now//3600*3600


def replay_view(db,uid,src,cursor=None,count=0,timeframe=None):
    now=int(time.time());anchor=src['anchor']
    mode=src.get('mode','alert');tf=replay_timeframe(timeframe or (cursor['timeframe'] if cursor else 'H1'))
    clock=anchor if cursor is None else int(cursor['revealed'])
    context_days=21 if tf in ('D','W') and not count else CONTEXT_DAYS
    lo=max(0,(clock//3600-context_days*24)*3600)
    # Initial D/W requests spend the bounded budget on visible context. Steps
    # roll around the revealed clock, so replay is not limited to seven days.
    hi=(clock//3600+(FORWARD_DAYS*24+1 if count or tf not in ('D','W') else 0))*3600
    envelope={'mode':mode,'pair':src['pair'],'anchor':anchor,'clock':clock,'timeframe':tf,
              'timeframes':list(REPLAY_TIMEFRAMES),'window':{'context_days':context_days,'forward_days':FORWARD_DAYS},'event':src.get('event'),'markers':src.get('markers',[])}
    cached=replay_cache.available(db,src['pair'],lo,hi,now,required_until=_latest_possible_close('H1',src['pair'],clock),metadata=True)
    if cached is None:
        from webapp.replay_loader import fill
        fill(db,src['pair'],lo,hi,now)
        cached=replay_cache.available(db,src['pair'],lo,hi,now,required_until=_latest_possible_close('H1',src['pair'],clock),metadata=True)
    rows=None if cached is None else cached['rows']
    if rows is None:
        old=db.query('SELECT status,updated_at FROM replay_requests WHERE user_id=%s AND pair=%s AND lo=%s AND hi=%s',(uid,src['pair'],lo,hi))
        if old and old[0]['status']=='UNAVAILABLE' and now-int(old[0]['updated_at'])<3600:
            return {**envelope,'available':False,'status':'unavailable','message':'This historical window could not be loaded from the broker or retained candle storage. Try another date or retry later.'}
        queue_replay(db,uid,src['pair'],lo,hi,now)
        return {**envelope,'available':False,'status':'queued','message':'Replay history could not be loaded immediately. The broker may be busy or this date may be unavailable. Try opening it again shortly; the hourly history publisher is also queued as a fallback.'}
    if count and not any(end>clock for _,end in completed_closes(rows,tf,src['pair'],min(now,hi))) and hi>clock:
        from webapp.replay_loader import fill
        fill(db,src['pair'],lo,hi,now)
        newer=replay_cache.available(db,src['pair'],lo,hi,now,required_until=_latest_possible_close('H1',src['pair'],clock),metadata=True)
        if newer is not None:cached=newer;rows=newer['rows']
    # Recheck the hard data boundary even if cache internals change. Never let an
    # initial aggregation see bars after its replay clock.
    rows=[r for r in rows if lo<=r[0] and r[0]+3600<=min(hi,now//3600*3600)]
    refresh_pending=False
    if rows and rows[-1][0]+3600<min(hi,now//3600*3600):
        state=db.query('SELECT status,updated_at FROM replay_requests WHERE user_id=%s AND pair=%s AND lo=%s AND hi=%s',(uid,src['pair'],lo,hi))
        refresh_pending=bool(state and state[0]['status']=='QUEUED')
        if not state or (not refresh_pending and now-int(state[0]['updated_at'])>=3600):
            queue_replay(db,uid,src['pair'],lo,hi,now);refresh_pending=True
    # Find only future completion times, never aggregate future OHLC before
    # moving the replay clock. Price aggregation below sees the visible prefix.
    candidates=[end for start,end in completed_closes(rows,tf,src['pair'],min(now,hi))]
    future=[end for end in candidates if end>clock]
    if count and future:clock=future[min(count,len(future))-1]
    payload={'version':2,'user':uid,'mode':mode,'pair':src['pair'],'anchor':anchor,'revealed':clock,'timeframe':tf,'expires':now+3600}
    if mode=='alert':payload.update(kind=src['kind'],id=src['id'])
    return {**envelope,'available':True,'clock':clock,'cursor':_token(payload),
            'bars':aggregate_replay(rows,tf,src['pair'],clock),
            'finished':clock>=_latest_possible_close(tf,src['pair'],now),
            'provider':cached['provider'],
            'available_until':rows[-1][0]+3600 if rows else None,'refresh_pending':refresh_pending,
            'gaps':[[a[0]+3600,b[0]] for a,b in zip(rows,rows[1:]) if b[0]-a[0]>3600 and b[0]+3600<=clock],
            'feed':{'deriv':'Deriv UTC','ctrader':'IC Markets cTrader','dukascopy':'Dukascopy'}.get(cached['provider'],'Unknown cached feed')+' · true H1 source',
            'message':'Closed H1-derived candles only; incomplete or gapped higher-timeframe bars are omitted. Missing history stays unavailable. Legacy lifecycle records are not immutable decision snapshots.'}


def replay_history(db,uid,src,cursor,before=None):
    """Page strictly older completed bars without advancing the signed clock.

    Each request is bounded to 21 calendar days of genuine H1 history. Higher
    intervals can be paged repeatedly; this does not manufacture native D/W or
    promise multi-year coverage that the provider has not returned.
    """
    now=int(time.time());clock=cursor['revealed'];tf=cursor['timeframe'];pair=src['pair']
    if before is None:before=clock
    if not isinstance(before,int) or isinstance(before,bool) or not REPLAY_MIN_START<=before<=clock:
        raise HTTPException(422,'History boundary must be an epoch timestamp no later than the replay clock.')
    hi=before//3600*3600
    # Aim for about 200 bars in intraday intervals, while preserving the same
    # hard source/request ceiling for sparse higher-timeframe history.
    hours=int(tf[1:]) if tf.startswith('H') else 24 if tf=='D' else 168
    continuous=instruments.deriv_continuous(pair) if instruments.is_deriv(pair) else instruments.market_category(pair)=='Cryptocurrencies'
    wanted=int(math.ceil(200*hours*(1 if continuous else 7/5)))
    lo=max(REPLAY_MIN_START,hi-min(HISTORY_PAGE_DAYS*24,wanted)*3600)
    # End is exclusive by bar-open time, so a previous page's first bar cannot
    # be repeated. Bucket aggregation below also discards partial left edges.
    required=hi
    for _ in range(72):
        if _expected_hour(required-3600,pair,continuous):break
        required-=3600
    envelope={'clock':clock,'timeframe':tf,'pair':pair,'before':lo,
              'has_more':lo>REPLAY_MIN_START,'page_days':(hi-lo)/86400}
    if hi<=lo:return {**envelope,'available':True,'bars':[],'has_more':False,'status':'boundary'}
    cached=replay_cache.available(db,pair,lo,hi,now,required_until=required,metadata=True)
    if cached is None:
        from webapp.replay_loader import fill
        fill(db,pair,lo,hi,now)
        cached=replay_cache.available(db,pair,lo,hi,now,required_until=required,metadata=True)
    if cached is None:
        # Busy and unavailable are retryable. Never label a transient feed miss
        # as the historical beginning, and never skip that page on retry.
        old=db.query('SELECT status,updated_at FROM replay_requests WHERE user_id=%s AND pair=%s AND lo=%s AND hi=%s',(uid,pair,lo,hi))
        unavailable=bool(old and old[0]['status']=='UNAVAILABLE' and now-int(old[0]['updated_at'])<3600)
        if not unavailable:queue_replay(db,uid,pair,lo,hi,now)
        return {**envelope,'available':False,'before':before,'bars':[],
                'status':'unavailable' if unavailable else 'queued',
                'message':'Earlier history is unavailable for this page.' if unavailable else 'Earlier history is being prepared. Retry shortly; your chart and replay clock have been kept.'}
    visible=[r for r in cached['rows'] if lo<=r[0] and r[0]+3600<=min(hi,clock,now//3600*3600)]
    result=aggregate_replay(visible,tf,pair,clock)
    # When a page starts inside an Hn/D/W candle, retry that partial bucket in
    # the next page. Moving to lo directly could permanently drop the candle.
    boundary=result[0]['time'] if result else lo
    return {**envelope,'available':True,'bars':result,'before':boundary,
            'has_more':boundary>REPLAY_MIN_START,'status':'ready','provider':cached['provider'],
            'message':'Earlier completed candles; replay time is unchanged. History is paged in bounded H1-backed windows.'}


def register_routes(app,require_user,db):
    router=APIRouter()
    @router.get('/api/journal')
    def journal(user=Depends(require_user)):
        return db.query('SELECT * FROM trade_journal WHERE user_id=%s ORDER BY id DESC LIMIT 200',(user['id'],))
    @router.post('/api/journal')
    def create(body:dict=Body(...),user=Depends(require_user)):
        values=clean_journal(body)
        if values['source_kind']!='manual':
            src=source(db,user['id'],values['source_kind'],values['source_id'],require_anchor=False);values['pair']=src['pair']
        else:
            if values['source_id'] is not None:raise HTTPException(422,'Manual journals do not have a source ID.')
            known={r['key'] for r in instruments.deriv_symbols()}
            try:
                from pathlib import Path
                known.update(r['key'] for r in json.loads((Path(__file__).resolve().parents[1]/'data'/'broker_symbols.json').read_text())['symbols'])
            except (FileNotFoundError,KeyError):pass
            if values['pair'] not in known:raise HTTPException(422,'Choose a known broker instrument.')
        return write_journal(db,user['id'],values)
    @router.put('/api/journal/{ident}')
    def update(ident:int,body:dict=Body(...),user=Depends(require_user)):
        return write_journal(db,user['id'],clean_journal(body,True),ident)
    @router.delete('/api/journal/{ident}')
    def delete(ident:int,user=Depends(require_user)):
        if not db.execute('DELETE FROM trade_journal WHERE id=%s AND user_id=%s',(ident,user['id'])):raise HTTPException(404,'Journal entry not found.')
        return {'ok':True}
    @router.get('/api/replay/sources')
    def sources(user=Depends(require_user)):
        uid=user['id'];out=[]
        with tenancy.scope(uid):
            event_rows=db.query('SELECT * FROM manual_alert_events WHERE user_id=%s ORDER BY event_time DESC LIMIT 50',(uid,))
            event_watch_ids={r['watch_id'] for r in event_rows}
            groups=[('watch_event',event_rows),
                    ('bias',db.query('SELECT * FROM bias WHERE confirm_time IS NOT NULL ORDER BY confirm_time DESC LIMIT 50')),
                    ('entry',db.query('SELECT * FROM entries ORDER BY created_at DESC LIMIT 50')),
                    ('watch',[r for r in db.query('SELECT * FROM manual_alerts WHERE user_id=%s AND event_time IS NOT NULL ORDER BY event_time DESC LIMIT 50',(uid,)) if r['id'] not in event_watch_ids])]
        for kind,rows in groups:
            for row in rows:
                anchor=row.get('confirm_time') if kind=='bias' else (row.get('alerted_at') or row.get('created_at')) if kind=='entry' else row.get('event_time')
                if anchor and epoch(anchor)<=time.time():
                    item={'kind':kind,'id':row['id'],'pair':row['pair'],'anchor':epoch(anchor),'label':f"{row['pair']} · {kind} #{row['id']}"}
                    if kind=='watch_event':item['watch_id']=row['watch_id']
                    out.append(item)
        return sorted(out,key=lambda x:x['anchor'],reverse=True)[:100]
    @router.post('/api/replay/open')
    def open_replay(body:dict=Body(...),user=Depends(require_user)):
        mode=body.get('mode','alert')
        if not isinstance(mode,str) or mode not in ('alert','price'):raise HTTPException(422,'Choose Alert replay or Price replay.')
        tf=replay_timeframe(body.get('timeframe','H1'))
        if mode=='price':
            if set(body)-{'mode','pair','start','timeframe'}:raise HTTPException(422,'Price replay takes a market, start time and timeframe, not an alert ID.')
            src=price_source(body)
        else:
            if set(body)-{'mode','kind','id','timeframe'}:raise HTTPException(422,'Alert replay takes an owned source and timeframe.')
            src=source(db,user['id'],body.get('kind'),body.get('id'))
        return replay_view(db,user['id'],src,timeframe=tf)
    @router.post('/api/replay/step')
    def step(body:dict=Body(...),user=Depends(require_user)):
        if set(body)-{'cursor','count'}:raise HTTPException(422,'Replay steps take only the signed cursor and count.')
        cursor=_read_token(body.get('cursor'),user['id']);count=body.get('count',1)
        if not isinstance(count,int) or isinstance(count,bool) or not 1<=count<=24:raise HTTPException(422,'Replay steps must be 1–24 candles.')
        return replay_view(db,user['id'],_cursor_source(db,user['id'],cursor),cursor,count)
    @router.post('/api/replay/timeframe')
    def switch_timeframe(body:dict=Body(...),user=Depends(require_user)):
        if set(body)-{'cursor','timeframe'}:raise HTTPException(422,'Timeframe switching takes only the signed cursor and timeframe.')
        cursor=_read_token(body.get('cursor'),user['id']);tf=replay_timeframe(body.get('timeframe'))
        return replay_view(db,user['id'],_cursor_source(db,user['id'],cursor),cursor,timeframe=tf)
    @router.post('/api/replay/history')
    def history(body:dict=Body(...),user=Depends(require_user)):
        if set(body)-{'cursor','before'}:raise HTTPException(422,'History paging takes only the signed cursor and before timestamp.')
        cursor=_read_token(body.get('cursor'),user['id'])
        return replay_history(db,user['id'],_cursor_source(db,user['id'],cursor),cursor,body.get('before'))
    app.include_router(router)

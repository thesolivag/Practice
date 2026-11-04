"""Explicit, versioned manual watches. Closed candles only; no AI or broker order execution.

Rule names identify our testable v1 definitions, not a claim of an exact Radar clone.
The web API imports this module without pandas; the scanner loads market data lazily.
"""
import json
import math
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc
MAX_ACTIVE = 20
MAX_DAILY = 100
TIMEFRAMES = {'M5': 5, 'M15': 15, 'M30': 30, 'M45': 45, 'H1': 60, 'H2': 120, 'H3': 180, 'H4': 240, 'D': 1440, 'W': 10080}
LOWER = {'M5':'M1','M15':'M5','M30':'M15','M45':'M15','H1':'M30','H2':'H1','H3':'H1','H4':'H2','D':'H4','W':'D'}
CONDITIONS = [
    {'value': 'crossing', 'label': 'Sampled-price crossing',
     'description': 'A fresh broker-price sample crosses your level compared with the previous checked sample. The first sample establishes a baseline. Sampling can miss moves between checks.'},
    {'value':'closed_crossing','label':'Closed-candle crossing','description':'Two consecutive completed candles close on opposite sides of your price.'},
    {'value': 'close_above', 'label': 'Close above', 'description': 'A completed candle closes strictly above your price.'},
    {'value': 'close_below', 'label': 'Close below', 'description': 'A completed candle closes strictly below your price.'},
    {'value': 'rejection', 'label': 'Rejection',
     'description': 'A completed candle touches your price and closes back on its opening side; BUY opens/closes above, SELL below.'},
    {'value': 'breakout', 'label': 'Breakout confirmation',
     'description': 'A completed candle breaks the latest confirmed close-line swing. At a level also requires a prior level reaction. Includes breakouts with a liquidity sweep; no separate sweep-and-break model. Local swings use one completed candle on each side; context is limited to eight bars.'},
    {'value': 'engulfing', 'label': 'Engulfing confirmation',
     'description': 'Three consecutive candles: the first two form the open-close key level; the third closes strictly beyond it. BUY closes above the first bearish candle close; SELL is mirrored. Full-body engulfing is not required.'},
    {'value': 'fourth_man', 'label': '4th man confirmation',
     'description': 'BUY: sweep the previous candle low, leave its high standing and close strictly inside its range. SELL is mirrored. Candle colour is unrestricted. The completed pattern identifies a level for a later retest; it is not a retest alert.'},
]
VALUES = {c['value'] for c in CONDITIONS}
CONFIRMATIONS = {'breakout', 'engulfing', 'fourth_man'}
RETIRED = {'pinbar_v1', 'cisd_v1'}


MAX_CONFIRMATION_TIMEFRAMES = 6
MAX_EVENT_BYTES = 16384
MAX_USER_EVENTS = 1000
MAX_GLOBAL_EVENTS = 10000
MAX_HISTORY_BYTES = 8 * 1024 * 1024
EVENT_RETENTION_DAYS = 30
MODEL_ORDER = ['breakout','engulfing','fourth_man']


def watch_options(watch):
    """Legacy rows remain single, level-scoped, one-shot watches."""
    raw=watch.get('options_json')
    if not raw:
        kind='confirmation' if watch['condition'] in CONFIRMATIONS else 'price'
        return {'kind':kind,'models':[watch['condition']] if kind=='confirmation' else [],
                'timeframes':[watch['timeframe']],'scope':'level','repeat':'once','legacy':True,'cursors':{}}
    try:options=json.loads(raw) if isinstance(raw,str) else dict(raw)
    except (ValueError,TypeError):raise ValueError('Invalid saved alert options') from None
    kind=options.get('kind')
    if kind not in ('price','confirmation'):raise ValueError('Invalid saved alert kind')
    tfs=options.get('timeframes')
    if not isinstance(tfs,list) or not 1<=len(tfs)<=MAX_CONFIRMATION_TIMEFRAMES or any(not isinstance(tf,str) or tf not in TIMEFRAMES for tf in tfs):
        raise ValueError('Invalid saved alert timeframes')
    if kind=='confirmation':
        models=options.get('models')
        if not isinstance(models,list) or not 1<=len(models)<=3 or any(not isinstance(m,str) or m not in CONFIRMATIONS for m in models):
            raise ValueError('Invalid saved confirmation models')
        if options.get('scope') not in ('anywhere','level') or options.get('repeat') not in ('once','each'):
            raise ValueError('Invalid saved confirmation scope or repetition')
    else:options={**options,'models':[],'scope':'level','repeat':'once'}
    cursors=options.get('cursors',{})
    if not isinstance(cursors,dict) or any(tf not in tfs or isinstance(n,bool) or not isinstance(n,int) or n<0 for tf,n in cursors.items()):
        raise ValueError('Invalid saved alert cursors')
    return {**options,'legacy':False,'cursors':cursors}


def public_watch(row):
    out=dict(row)
    try:
        options=watch_options(row)
        out.update({key:options[key] for key in ('kind','models','timeframes','scope','repeat')})
        if options['scope']=='anywhere':out['level']=None
    except ValueError:
        out.update(kind='invalid',models=[],timeframes=[],scope='level',repeat='once',error='Saved alert options are unavailable; cancel and recreate this watch')
    out.pop('options_json',None)
    out.pop('lease_token',None)
    return out


def _options_json(options):
    return json.dumps({k:v for k,v in options.items() if k!='legacy'},separators=(',',':'),sort_keys=True)


def _variants(watch):
    options=watch_options(watch)
    if options['kind']=='price':return [dict(watch,scope='level')]
    variants=[]
    for tf in options['timeframes']:
        for model in options['models']:
            variants.append({**watch,'condition':model,'timeframe':tf,'scope':options['scope'],
                             'level':None if options['scope']=='anywhere' else watch['level'],
                             'last_checked':options['cursors'].get(tf,watch['created_at']) if not options['legacy'] else watch.get('last_checked',watch['created_at'])})
    return variants


def _combine_events(events,watch):
    if not events:return None
    stamp=min(event['time'] for event in events)
    matches=[dict(event) for event in events if event['time']==stamp]
    matches.sort(key=lambda event:(MODEL_ORDER.index(event['condition']) if event['condition'] in MODEL_ORDER else -1,TIMEFRAMES.get(event['timeframe'],0),event['side']))
    unique={ (m['condition'],m['timeframe'],m['side']):m for m in matches }
    matches=list(unique.values())
    options=watch_options(watch)
    return {**matches[0],'kind':options['kind'],'scope':options['scope'],
            'level':None if options['scope']=='anywhere' else float(watch['level']),
            'matches':matches}


def freeze_event(watch,event):
    frozen=dict(event)
    options=watch_options(watch)
    frozen.update(kind=options['kind'],scope=options['scope'],level=None if options['scope']=='anywhere' else float(watch['level']))
    if not frozen.get('matches'):frozen['matches']=[{k:v for k,v in event.items() if k not in ('matches','kind','scope','level')}]
    encoded=json.dumps(frozen,separators=(',',':'),sort_keys=True,allow_nan=False)
    if len(encoded.encode())>MAX_EVENT_BYTES:raise ValueError('Alert event exceeds its storage limit')
    return frozen,encoded

def schema():
    return {'conditions': CONDITIONS, 'timeframes': list(TIMEFRAMES), 'max_active': MAX_ACTIVE,
            'price_conditions':[c for c in CONDITIONS if c['value'] not in CONFIRMATIONS],
            'confirmation_models':[c for c in CONDITIONS if c['value'] in CONFIRMATIONS],
            'confirmation_timeframes':list(TIMEFRAMES), 'max_confirmation_timeframes':MAX_CONFIRMATION_TIMEFRAMES,
            'event_retention':{'days':EVENT_RETENTION_DAYS,'per_user':MAX_USER_EVENTS,'global':MAX_GLOBAL_EVENTS,'payload_bytes':MAX_EVENT_BYTES,'global_bytes':MAX_HISTORY_BYTES},
            'lower_timeframes': LOWER, 'max_expiry_hours': 168,
            'engulfing_definition': 'The third consecutive lower-timeframe candle closes beyond the open-close key level formed by the first two, within the confirming parent candle.',
            'timing': 'Completed broker candles only; price crossing uses fresh sampled quotes. One-minute external checks can be busy, deferred or delayed and can miss quote moves between samples. Minute-history catch-up is bounded to the available recent window; expired candle watches get at most 24 hours for a final check. Messages include actual event times. No historical signals before watch creation.'}


def symbols():
    from . import instruments
    p = Path(__file__).resolve().parents[1] / 'data' / 'broker_symbols.json'
    regular = json.loads(p.read_text())['symbols'] if p.exists() else []
    return {r['key'] for r in regular} | {r['key'] for r in instruments.deriv_symbols()}


def validate(body, now=None):
    now=int(time.time() if now is None else now)
    if not isinstance(body,dict):raise ValueError('Alert must be an object')
    common={'pair','side','level','engulfing','note','expires_hours'}
    kind=body.get('kind')
    if kind is not None and kind not in ('price','confirmation'):raise ValueError('Choose Price or Confirmation')
    if kind=='confirmation':allowed=common|{'kind','models','timeframes','scope','repeat'}
    else:allowed=common|{'condition','timeframe'}|({'kind'} if kind=='price' else set())
    if set(body)-allowed:raise ValueError('Unknown alert fields: '+', '.join(sorted(set(body)-allowed)))
    pair=str(body.get('pair','')).strip().upper()
    if pair not in symbols():raise ValueError('Choose a symbol from the broker catalogue')
    scope='level';repeat='once';models=None;tfs=None
    if kind=='confirmation':
        models=body.get('models');tfs=body.get('timeframes')
        if not isinstance(models,list) or not 1<=len(models)<=3 or any(not isinstance(m,str) or m not in CONFIRMATIONS for m in models):
            raise ValueError('Choose one or more of Breakout, Engulfing and 4th man')
        if not isinstance(tfs,list) or not 1<=len(tfs)<=MAX_CONFIRMATION_TIMEFRAMES or any(not isinstance(tf,str) or tf not in TIMEFRAMES for tf in tfs):
            raise ValueError('Choose from one to six supported confirmation timeframes')
        models=[model for model in MODEL_ORDER if model in models]
        tfs=[tf for tf in TIMEFRAMES if tf in tfs]
        scope=body.get('scope','anywhere');repeat=body.get('repeat','once')
        if scope not in ('anywhere','level'):raise ValueError('Scope must be anywhere or level')
        if repeat not in ('once','each'):raise ValueError('Repeat must be once or each')
        condition,tf=models[0],tfs[0]
    else:
        condition=body.get('condition');tf=body.get('timeframe','H1')
        if not isinstance(condition,str) or condition not in VALUES:raise ValueError('Choose an alert condition')
        if kind=='price' and condition in CONFIRMATIONS:raise ValueError('Choose a price condition, or switch to Confirmation')
        if not isinstance(tf,str) or tf not in TIMEFRAMES:raise ValueError('Choose a supported candle timeframe')
    side=body.get('side','EITHER')
    if not isinstance(side,str) or side not in {'BUY','SELL','EITHER'}:raise ValueError('Side must be BUY, SELL or EITHER')
    if scope=='anywhere':
        if body.get('level') not in (None,''):raise ValueError('Anywhere confirmation does not use a price; choose At a level to set one')
        level=0.0  # unused storage value for the legacy NOT NULL column; detectors receive None
    else:
        if isinstance(body.get('level'),bool):raise ValueError('Price must be a positive finite number')
        try:level=float(body['level'])
        except (ValueError,TypeError,KeyError):raise ValueError('Price must be a positive finite number') from None
        if not math.isfinite(level) or level<=0:raise ValueError('Price must be a positive finite number')
    engulfing=body.get('engulfing',False)
    if not isinstance(engulfing,bool):raise ValueError('Engulfing must be true or false')
    if engulfing and condition not in CONFIRMATIONS:raise ValueError('Engulfing is available for confirmation conditions only')
    hours=body.get('expires_hours',24)
    if isinstance(hours,bool) or not isinstance(hours,int) or not 1<=hours<=168:raise ValueError('Expiry must be a whole number of hours from 1 to 168')
    note=body.get('note','')
    if not isinstance(note,str) or len(note)>300:raise ValueError('Note must contain at most 300 characters')
    result=dict(pair=pair,condition=condition,timeframe=tf,side=side,level=level,engulfing=int(engulfing),note=note.strip(),created_at=now,expires_at=now+hours*3600,last_checked=now)
    if kind is not None:
        result['options_json']=_options_json({'kind':kind,'models':models or [],'timeframes':tfs or [tf],'scope':scope,'repeat':repeat,'cursors':{}})
    return result


class Repository:
    """One connection per operation/batch. Tables always have explicit ownership predicates."""
    def __init__(self, db): self.db = db
    def __enter__(self): self.conn = self.db.connect(); return self
    def __exit__(self, *exc): self.conn.close()
    def query(self, sql, args=()):
        with self.conn.cursor() as c:
            c.execute(sql, args)
            return list(c.fetchall())
    def execute(self, sql, args=()):
        with self.conn.cursor() as c:
            return c.execute(sql, args)
    def list(self, uid):
        self.execute("UPDATE manual_alerts SET status='EXPIRED',error=NULL WHERE user_id=%s AND status='PAUSED' AND expires_at<=%s", (int(uid),int(time.time())))
        return [public_watch(row) for row in self.query('SELECT * FROM manual_alerts WHERE user_id=%s ORDER BY id DESC LIMIT 200', (int(uid),))]
    def create(self, uid, data):
        uid = int(uid)
        self.conn.begin()
        try:
            self.execute('INSERT IGNORE INTO manual_alert_users (user_id) VALUES (%s)', (uid,))
            self.query('SELECT user_id FROM manual_alert_users WHERE user_id=%s FOR UPDATE', (uid,))
            active = self.query("SELECT COUNT(*) AS n FROM manual_alerts WHERE user_id=%s AND (status='TRIGGERED' OR (status IN ('ACTIVE','PAUSED') AND expires_at>%s))", (uid,data['created_at']))[0]['n']
            daily = self.query('SELECT COUNT(*) AS n FROM manual_alerts WHERE user_id=%s AND created_at>%s', (uid, data['created_at'] - 86400))[0]['n']
            if active >= MAX_ACTIVE: raise ValueError(f'Up to {MAX_ACTIVE} active alerts per account')
            if daily >= MAX_DAILY: raise ValueError('Daily alert-creation limit reached; try again tomorrow')
            cols = ['user_id', *data]
            with self.conn.cursor() as c:
                c.execute('INSERT INTO manual_alerts (' + ','.join('`'+x+'`' for x in cols) + ') VALUES (' + ','.join(['%s']*len(cols)) + ')', [uid, *data.values()])
                alert_id = int(c.lastrowid)
            self.conn.commit()
        except Exception:
            self.conn.rollback(); raise
        return public_watch(self.query('SELECT * FROM manual_alerts WHERE id=%s AND user_id=%s', (alert_id, uid))[0])
    def cancel(self, uid, alert_id, now=None):
        stamp = int(time.time() if now is None else now)
        won = self.execute("UPDATE manual_alerts SET status='CANCELLED',lease_token=NULL,lease_until=0 WHERE id=%s AND user_id=%s AND status IN ('ACTIVE','TRIGGERED','PAUSED') AND lease_until<=%s", (alert_id, int(uid), stamp))
        if won: return True
        rows = self.query('SELECT status,lease_until FROM manual_alerts WHERE id=%s AND user_id=%s', (alert_id, int(uid)))
        if not rows: return None
        if rows[0]['status'] in {'ACTIVE', 'TRIGGERED'}: raise ValueError('Delivery is in progress; refresh before cancelling')
        return True
    def set_paused(self, uid, alert_id, paused, now=None):
        """Keep expiry fixed; resume from now without replaying the paused interval."""
        stamp = int(time.time() if now is None else now)
        self.conn.begin()
        try:
            rows = self.query('SELECT * FROM manual_alerts WHERE id=%s AND user_id=%s FOR UPDATE', (alert_id, int(uid)))
            if not rows:
                self.conn.commit(); return None
            row = rows[0]
            target = 'PAUSED' if paused else 'ACTIVE'
            source = 'ACTIVE' if paused else 'PAUSED'
            if row['status'] not in (source, target):
                raise ValueError('Only active alerts can pause and paused alerts can resume; refresh the list')
            if int(row['expires_at']) <= stamp:
                self.execute("UPDATE manual_alerts SET status='EXPIRED' WHERE id=%s AND user_id=%s", (alert_id, int(uid)))
                self.conn.commit()
                raise ValueError('This alert has expired; create a new alert')
            if int(row.get('lease_until') or 0) > stamp:
                raise ValueError('Delivery is in progress; refresh before pausing')
            if row['status'] == source:
                options = watch_options(row)
                if not paused and not options['legacy']:
                    options['cursors'] = {tf:stamp for tf in options['timeframes']}
                self.execute("UPDATE manual_alerts SET status=%s,last_checked=GREATEST(last_checked,%s),options_json=%s,last_quote=NULL,quote_time=NULL,lease_token=NULL,lease_until=0,error=NULL WHERE id=%s AND user_id=%s",
                             (target,stamp,_options_json(options) if row.get('options_json') else None,alert_id,int(uid)))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback(); raise
    def pending(self, now):
        # Old interpreted definitions must not silently acquire different semantics.
        self.execute("UPDATE manual_alerts SET status='EXPIRED',error='Confirmation definition retired; recreate using Breakout, Engulfing or 4th man',lease_token=NULL,lease_until=0 WHERE `condition` IN ('pinbar_v1','cisd_v1') AND status IN ('ACTIVE','TRIGGERED') AND lease_until<=%s", (now,))
        # Quotes cannot reconstruct an unobserved historical crossing. Candle
        # conditions get one bounded day of final catch-up before terminal expiry.
        self.execute("UPDATE manual_alerts SET status='EXPIRED',error=CASE WHEN `condition`='crossing' THEN 'Expired before another fresh price sample' ELSE 'Expired outside retained candle catch-up window' END WHERE status='ACTIVE' AND ((`condition`='crossing' AND expires_at<%s) OR (`condition`<>'crossing' AND expires_at<%s))",(now,now-86400))
        self.execute("UPDATE manual_alerts SET status='EXPIRED',error=NULL WHERE status='PAUSED' AND expires_at<=%s", (now,))
        # Retain tiny user records for30days, not an unbounded candle/research history.
        self.execute("DELETE FROM manual_alerts WHERE status IN ('FIRED','CANCELLED','EXPIRED') AND expires_at<%s", (now-30*86400,))
        return self.query("SELECT * FROM manual_alerts WHERE status IN ('ACTIVE','TRIGGERED') ORDER BY last_attempt,id LIMIT 200")
    def attempted(self, row, stamp, error=None):
        self.execute('UPDATE manual_alerts SET last_attempt=%s,error=%s WHERE id=%s AND user_id=%s', (stamp, error, row['id'], row['user_id']))
    def checked(self,row,stamp,cursors=None):
        if not row.get('options_json') or not cursors:
            return self.execute("UPDATE manual_alerts SET last_checked=GREATEST(last_checked,%s),error=NULL WHERE id=%s AND user_id=%s AND status='ACTIVE'",(stamp,row['id'],row['user_id']))
        self.conn.begin()
        try:
            rows=self.query("SELECT * FROM manual_alerts WHERE id=%s AND user_id=%s AND status='ACTIVE' FOR UPDATE",(row['id'],row['user_id']))
            if not rows:self.conn.commit();return 0
            options=watch_options(rows[0])
            merged=dict(options['cursors'])
            for tf,value in cursors.items():
                if tf in options['timeframes']:merged[tf]=max(merged.get(tf,int(rows[0]['created_at'])),int(value))
            options['cursors']=merged
            result=self.execute("UPDATE manual_alerts SET last_checked=GREATEST(last_checked,%s),options_json=%s,error=NULL WHERE id=%s AND user_id=%s AND status='ACTIVE'",(stamp,_options_json(options),row['id'],row['user_id']))
            self.conn.commit();return result
        except Exception:self.conn.rollback();raise
    def _trigger_locked(self,current,event):
        if current['status']!='ACTIVE':return False
        options=watch_options(current)
        if not int(current['created_at'])<int(event['time'])<=int(current['expires_at']):return False
        if options['kind']=='confirmation' and not options['legacy']:
            matches=event.get('matches') or [event]
            fresh=[m for m in matches if options['cursors'].get(m['timeframe'],int(current['created_at']))<int(m['time'])]
            if not fresh:return False
            event=_combine_events(fresh,current)
        elif int(current['last_checked'])>=int(event['time']):return False
        frozen,payload=freeze_event(current,event)
        return bool(self.execute("UPDATE manual_alerts SET status='TRIGGERED',event_time=%s,event_payload=%s,error=NULL WHERE id=%s AND user_id=%s AND status='ACTIVE'",(frozen['time'],payload,current['id'],current['user_id'])))
    def trigger(self,row,event):
        self.conn.begin()
        try:
            rows=self.query('SELECT * FROM manual_alerts WHERE id=%s AND user_id=%s FOR UPDATE',(row['id'],row['user_id']))
            won=self._trigger_locked(rows[0],event) if rows else False
            self.conn.commit();return won
        except Exception:self.conn.rollback();raise
    def expire(self,row,stamp,error=None):
        return self.execute("UPDATE manual_alerts SET status='EXPIRED',error=%s WHERE id=%s AND user_id=%s AND status='ACTIVE' AND expires_at<=%s",(error,row['id'],row['user_id'],stamp))
    def observe_quote(self,row,price,quote_time,now):
        """Lock baseline and event together: parallel ticks cannot roll it backward."""
        if not fresh_quote(price,quote_time,now):return None
        self.conn.begin()
        try:
            rows=self.query('SELECT * FROM manual_alerts WHERE id=%s AND user_id=%s FOR UPDATE',(row['id'],row['user_id']))
            if not rows or rows[0]['status']!='ACTIVE':self.conn.commit();return None
            current=rows[0]
            event=quote_event(current,price,quote_time,now)
            if int(quote_time)>max(int(current['created_at']),int(current.get('last_checked') or 0),int(current.get('quote_time') or 0)):
                self.execute("UPDATE manual_alerts SET last_quote=%s,quote_time=%s,error=NULL WHERE id=%s AND user_id=%s AND status='ACTIVE'",(price,int(quote_time),row['id'],row['user_id']))
            if event:
                won=self._trigger_locked(current,event)
                if not won:event=None
                else:
                    frozen,payload=freeze_event(current,event)
                    current={**current,'status':'TRIGGERED','event_time':event['time'],'event_payload':payload}
            self.conn.commit()
            return current if event else None
        except Exception:self.conn.rollback();raise
    def acknowledge(self,row,token,stamp):
        """Record immutable delivered evidence and advance recurrence in one transaction."""
        self.conn.begin()
        try:
            # Reserved account0 serializes the small global retention budget.
            self.execute('INSERT IGNORE INTO manual_alert_users (user_id) VALUES (0)')
            self.query('SELECT user_id FROM manual_alert_users WHERE user_id=0 FOR UPDATE')
            rows=self.query("SELECT * FROM manual_alerts WHERE id=%s AND user_id=%s AND lease_token=%s AND status='TRIGGERED' FOR UPDATE",(row['id'],row['user_id'],token))
            if not rows:self.conn.commit();return False
            current=rows[0]
            event,payload=freeze_event(current,json.loads(current['event_payload']))
            self.execute('INSERT IGNORE INTO manual_alert_events (user_id,watch_id,pair,event_time,model,timeframe,side,level,event_payload,sent_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (current['user_id'],current['id'],current['pair'],event['time'],event['condition'],event.get('timeframe') or 'QUOTE',event['side'],event['level'],payload,stamp))
            options=watch_options(current)
            repeating=options['kind']=='confirmation' and options['repeat']=='each'
            if repeating:
                cursors=dict(options['cursors'])
                for match in event['matches']:
                    tf=match['timeframe']
                    if tf in options['timeframes']:cursors[tf]=max(cursors.get(tf,int(current['created_at'])),int(match['time']))
                options['cursors']=cursors
            self.execute("UPDATE manual_alerts SET status=%s,last_checked=GREATEST(last_checked,%s),options_json=%s,event_payload=%s,sent_at=%s,lease_until=0,lease_token=NULL,error=NULL WHERE id=%s AND user_id=%s AND lease_token=%s AND status='TRIGGERED'",
                         ('ACTIVE' if repeating else 'FIRED',event['time'],_options_json(options) if current.get('options_json') else None,payload,stamp,current['id'],current['user_id'],token))
            self.execute('DELETE FROM manual_alert_events WHERE sent_at<%s',(stamp-EVENT_RETENTION_DAYS*86400,))
            user_count=int(self.query('SELECT COUNT(*) AS n FROM manual_alert_events WHERE user_id=%s',(current['user_id'],))[0]['n'])
            if user_count>MAX_USER_EVENTS:self.execute('DELETE FROM manual_alert_events WHERE user_id=%s ORDER BY id LIMIT %s',(current['user_id'],user_count-MAX_USER_EVENTS))
            total=int(self.query('SELECT COUNT(*) AS n FROM manual_alert_events')[0]['n'])
            if total>MAX_GLOBAL_EVENTS:self.execute('DELETE FROM manual_alert_events ORDER BY id LIMIT %s',(total-MAX_GLOBAL_EVENTS,))
            total_bytes=int(self.query('SELECT COALESCE(SUM(OCTET_LENGTH(event_payload)+256),0) AS n FROM manual_alert_events')[0]['n'])
            if total_bytes>MAX_HISTORY_BYTES:
                # One event can exceed the budget by at most16KiB. Evict a
                # bounded batch rather than one round-trip per tiny old record.
                self.execute('DELETE FROM manual_alert_events ORDER BY id LIMIT 128')
            self.conn.commit();return True
        except Exception:self.conn.rollback();raise
    def deliver(self,row,sender,stamp):
        token=secrets.token_hex(16)
        won=self.execute("UPDATE manual_alerts SET lease_token=%s,lease_until=%s WHERE id=%s AND user_id=%s AND status='TRIGGERED' AND lease_until<=%s",(token,stamp+600,row['id'],row['user_id'],stamp))
        if not won:return None
        # Use the payload actually claimed, not an earlier scanner snapshot.
        claimed=self.query("SELECT * FROM manual_alerts WHERE id=%s AND user_id=%s AND lease_token=%s AND status='TRIGGERED'",(row['id'],row['user_id'],token))
        if not claimed:return None
        current=claimed[0]
        try:ok=bool(sender(message(current,json.loads(current['event_payload'])),chat=int(current['user_id'])))
        except Exception:ok=False
        if ok:
            return self.acknowledge(current,token,stamp)
        self.execute("UPDATE manual_alerts SET lease_until=0,lease_token=NULL,error='Telegram delivery failed; retry pending' WHERE id=%s AND user_id=%s AND lease_token=%s AND status='TRIGGERED'",(row['id'],row['user_id'],token))
        return False


def complete_bars(frame, tf, now, pair='EURUSD'):
    from . import alert_data
    out = alert_data.complete_bars(frame, tf, pair, now)
    return out.to_dict('records') if hasattr(out,'to_dict') else out


def adjacent(previous,current,tf):
    """Never turn missing candles into adjacent pattern candles."""
    seconds=(current['start']-previous['start']).total_seconds()
    expected=TIMEFRAMES[tf]*60
    tolerance=3600 if tf in {'D','W'} else 0
    return abs(seconds-expected)<=tolerance


def oc_boundary(bars, index, side, tf):
    """Bishop diagram: two opposing bodies share an open-close key level.

    Use the first candle close (same level as the next open in a gapless feed).
    Do not demand coverage of both bodies or a close beyond the run's first open.
    """
    if index < 2: return None
    first, second, current = bars[index-2:index+1]
    if not adjacent(first, second, tf) or not adjacent(second, current, tf):
        return None
    opposing = (lambda r: r['close'] < r['open']) if side == 'BUY' else (lambda r: r['close'] > r['open'])
    if not opposing(first) or not opposing(second):
        return None
    boundary = float(first['close'])
    beyond = (lambda r: r['close'] > boundary) if side == 'BUY' else (lambda r: r['close'] < boundary)
    return boundary if beyond(current) and not beyond(second) else None


def confirmation_detail(watch, bars, index, side):
    """Prefix-only pattern evidence, bounded to the ten bars acquired per watch."""
    condition = watch['condition']; tf = watch['timeframe']; anywhere=watch.get('scope')=='anywhere'
    level=None if anywhere else float(watch['level'])
    if condition not in CONFIRMATIONS or index < 1: return None
    lo = max(0, index-8)
    # Never bridge a missing component or invent adjacency over a gap.
    for j in range(lo+1, index+1):
        if not adjacent(bars[j-1], bars[j], tf): lo = j
    r, p = bars[index], bars[index-1]
    if anywhere:
        if int(r['start'].timestamp())<int(watch['created_at']):return None
        touches=[index]
    else:
        touches = [j for j in range(lo,index+1) if bars[j]['low'] <= level <= bars[j]['high']
                   and int(bars[j]['start'].timestamp()) >= int(watch['created_at'])]
    if not touches: return None
    if condition == 'fourth_man':
        if index-1 < lo or index not in touches: return None
        inside = p['low'] < r['close'] < p['high']
        swept = r['low'] < p['low'] and r['high'] < p['high'] if side == 'BUY' else r['high'] > p['high'] and r['low'] > p['low']
        if inside and swept:
            return {'reference_level':float(p['low'] if side=='BUY' else p['high']),
                    'pattern_level':float(r['close']), 'stage':'confirmation; retest pending'}
        return None
    if condition == 'engulfing':
        if index-2 < lo: return None
        boundary = oc_boundary(bars,index,side,tf)
        if boundary is not None:
            return {'reference_level':boundary, 'pattern_level':boundary, 'stage':'confirmation; retest pending'}
        return None
    # Latest already-confirmed one-bar close-line pivot, never the forming bar.
    kind = 'H' if side == 'BUY' else 'L'
    from .structure import pivots
    candidates = pivots([b['close'] for b in bars[lo:index]],1)
    refs = [q for q in candidates if q[1] == kind]
    if not refs: return None
    pivot, _, boundary, _ = refs[-1]; pivot += lo
    # A prior break consumes this pivot. A wick sweep is optional, not a new type.
    if side == 'BUY':
        crossed = p['close'] <= boundary < r['close']
        consumed = any(bars[j]['close'] > boundary for j in range(pivot+1,index))
    else:
        crossed = p['close'] >= boundary > r['close']
        consumed = any(bars[j]['close'] < boundary for j in range(pivot+1,index))
    if crossed and not consumed:
        return {'reference_level':float(boundary), 'pattern_level':float(boundary), 'stage':'confirmation; retest pending'}
    return None


def matches(watch, bars, index, side):
    r = bars[index]; condition = watch['condition']
    if condition in CONFIRMATIONS:return confirmation_detail(watch,bars,index,side) is not None
    level=float(watch['level'])
    p = bars[index-1] if index and adjacent(bars[index-1],r,watch['timeframe']) else None
    touch = r['low'] <= level <= r['high']
    if condition == 'close_above': return side == 'BUY' and r['close'] > level
    if condition == 'close_below': return side == 'SELL' and r['close'] < level
    if condition == 'closed_crossing':
        return bool(p and ((side=='BUY' and p['close']<=level<r['close']) or (side=='SELL' and p['close']>=level>r['close'])))
    if condition == 'rejection':
        return touch and ((side=='BUY' and r['open']>level and r['close']>level) or (side=='SELL' and r['open']<level and r['close']<level))
    if condition in CONFIRMATIONS:
        return confirmation_detail(watch,bars,index,side) is not None
    return False


def _cached_bars(source,tf,now,pair,cache):
    key=(id(source),tf,pair)
    if key not in cache:cache[key]=complete_bars(source,tf,now,pair)
    return cache[key]


def _evaluate_one(watch,source,now,cache=None):
    """All directional matches at this variant's earliest eligible close."""
    cache={} if cache is None else cache
    bars=_cached_bars(source,watch['timeframe'],now,watch['pair'],cache)
    lower=_cached_bars(source,LOWER[watch['timeframe']],now,watch['pair'],cache) if watch.get('engulfing') else []
    cutoff=max(int(watch['created_at']),int(watch.get('last_checked') or 0))
    for i,r in enumerate(bars):
        stamp=int(r['end'].timestamp())
        if not cutoff<stamp<=int(watch['expires_at']):continue
        found=[]
        for side in ('BUY','SELL') if watch['side']=='EITHER' else (watch['side'],):
            if not matches(watch,bars,i,side):continue
            if watch.get('engulfing'):
                engulfed=any(j>=2 and r['start']<l['end']<=r['end']
                    and oc_boundary(lower,j,side,LOWER[watch['timeframe']]) is not None
                    and (watch.get('scope')=='anywhere' or any(r['start']<t['end']<=l['end']
                        and int(t['start'].timestamp())>=int(watch['created_at'])
                        and t['low']<=float(watch['level'])<=t['high'] for t in lower[max(0,j-8):j+1]))
                    for j,l in enumerate(lower))
                if not engulfed:continue
            found.append({'time':stamp,'side':side,'close':float(r['close']),
                'condition':watch['condition'],'timeframe':watch['timeframe'],
                'engulfing':bool(watch.get('engulfing')),
                **(confirmation_detail(watch,bars,i,side) or {})})
        if found:return found
    return []


def evaluate(watch,source,now):
    """Evaluate all selected models/timeframes against this one source snapshot."""
    from . import candles
    events=[];cache={}
    with candles.market(watch['pair']):
        for variant in _variants(watch):events.extend(_evaluate_one(variant,source,now,cache))
    return _combine_events(events,watch)


def evaluate_market(watch,market,now,snapshot_stamp,cache=None):
    """Each selected TF uses its fresh source independently; absent TFs stay unconsumed."""
    events=[];checked={};missing=[];cache={} if cache is None else cache
    for variant in _variants(watch):
        tf=variant['timeframe']
        source=market.get('hourly') if tf in ('D','W') else market.get('frame')
        if tf.startswith('H') and not data_fresh(source,min(snapshot_stamp,int(watch['expires_at'])),watch['pair']):source=market.get('hourly')
        if not data_fresh(source,min(snapshot_stamp,int(watch['expires_at'])),watch['pair']):
            if tf not in missing:missing.append(tf)
            continue
        try:
            found=_evaluate_one(variant,source,now,cache)
            events.extend(found)
            bars=_cached_bars(source,tf,now,watch['pair'],cache)
            if bars:checked[tf]=int(bars[-1]['end'].timestamp())
        except ValueError:
            if tf not in missing:missing.append(tf)
    return _combine_events(events,watch),checked,missing


def message(watch,event):
    from . import instruments
    options=watch_options(watch)
    at=datetime.fromtimestamp(event['time'],UTC)
    model=event.get('condition',watch['condition']);tf=event.get('timeframe',watch['timeframe'])
    labels={c['value']:c['label'] for c in CONDITIONS}
    lines=[f"🔔 {event['side']} · {instruments.label(watch['pair'])}",labels[model]]
    if event.get('scope',options['scope'])=='anywhere':lines.append('Scope: anywhere on this market')
    else:lines.append(f"Watched price: {instruments.fmt(watch['pair'],event.get('level',watch['level']))}")
    lines.extend([(f"Broker quote sampled {at:%Y-%m-%d %H:%M:%S} UTC" if model=='crossing' else f"{tf} candle closed {at:%Y-%m-%d %H:%M} UTC"),
        f"{'Sample' if model=='crossing' else 'Close'}: {instruments.fmt(watch['pair'],event['close'])}"])
    if event.get('reference_level') is not None:
        lines.append(f"Confirmation reference: {instruments.fmt(watch['pair'],event['reference_level'])}")
        lines.append(f"Candidate level for a later retest: {instruments.fmt(watch['pair'],event['pattern_level'])}; retest not yet confirmed.")
    tied=event.get('matches',[])
    if len(tied)>1:
        lines.append('All matches at this close:')
        lines.extend(f"• {match['side']} · {labels[match['condition']]} · {match['timeframe']}" for match in tied)
    if watch.get('engulfing'):lines.append('Lower-timeframe open-close engulfing confirmed.')
    if watch.get('note'):lines.append(watch['note'])
    lines.extend(['Manual watch, not an automatic order. Prices use the selected broker feed.',
                  'Scheduled delivery can follow the candle-close time.'])
    return '\n'.join(lines)


def fresh_quote(price,quote_time,now):
    try:
        return math.isfinite(float(price)) and float(price)>0 and 0<=int(now)-int(quote_time)<=120
    except (ValueError,TypeError,OverflowError):return False


def quote_event(watch,price,quote_time,now):
    if not fresh_quote(price,quote_time,now):return None
    stamp=int(quote_time)
    if not int(watch['created_at'])<=stamp<=int(watch['expires_at']):return None
    if stamp<=int(watch.get('quote_time') or 0) or watch.get('last_quote') is None:return None
    previous=float(watch['last_quote']);level=float(watch['level']);price=float(price)
    side='BUY' if previous<=level<price else 'SELL' if previous>=level>price else None
    if side and watch['side'] in ('EITHER',side):
        return {'time':stamp,'side':side,'close':price,'condition':'crossing','timeframe':None,'engulfing':False}
    return None


def data_fresh(frame,now,pair=None):
    """Require coverage through the captured provider snapshot, not fetch finish.

    Closed FX markets have no Saturday/current-minute candles: their latest
    expected source close is Friday17:00 New York. Continuous markets keep UTC.
    """
    import pandas as pd
    from . import instruments,store
    if frame is None or frame.empty:return False
    grain=int(frame.attrs.get('granularity',3600))
    expected=(int(now)//grain)*grain
    if pair is not None:
        continuous=instruments.deriv_continuous(pair) if instruments.is_deriv(pair) else instruments.market_category(pair)=='Cryptocurrencies'
        snapshot=pd.Timestamp(int(now),unit='s',tz='UTC')
        if not continuous and store.fx_closed(snapshot):
            ny=snapshot.tz_convert('America/New_York')
            friday=(ny-pd.DateOffset(days=(ny.dayofweek-4)%7)).normalize()+pd.Timedelta(hours=17)
            expected=min(expected,int(friday.tz_convert('UTC').timestamp()))
    return int(frame.index[-1].timestamp())+grain>=expected


def send_with_budget(text,chat,deadline):
    """Telegram send timeout shares this scan's remaining wall-clock budget."""
    import os
    import urllib.request
    token=os.environ.get('TELEGRAM_BOT_TOKEN')
    remaining=deadline-time.monotonic()
    if not token or remaining<=0:return False
    request=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',
        data=json.dumps({'chat_id':int(chat),'text':text,'disable_web_page_preview':True}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=min(10,remaining)) as response:
            return bool(json.load(response).get('ok'))
    except Exception:return False


def tick(now=None, refresh=True, sender=None, budget_seconds=180, max_pairs=8):
    from . import db,alert_data
    if isinstance(budget_seconds,bool) or not isinstance(budget_seconds,(int,float)) or not math.isfinite(budget_seconds) or not 1<=budget_seconds<=180:
        raise ValueError('Alert scan budget must be between 1 and 180 seconds')
    if isinstance(max_pairs,bool) or not isinstance(max_pairs,int) or not 1<=max_pairs<=8:
        raise ValueError('Alert scan pair cap must be from 1 to 8')
    stamp=int(time.time() if now is None else now)
    deadline=time.monotonic()+budget_seconds
    result={'ok':True,'processed':0,'triggered':0,'sent':0,'failed':0,'deferred':0}
    with Repository(db) as repo:
        pending=repo.pending(stamp)
        chosen=[];pairs=set();ordered_pairs=[];expired_before_selection=0
        for row in pending:
            if row['status']=='ACTIVE' and int(row['expires_at'])<stamp and (row['condition']=='crossing' or int(row['expires_at'])<stamp-86400):
                repo.expire(row,stamp,'Expired before another fresh price sample' if row['condition']=='crossing' else 'Expired outside retained candle catch-up window')
                expired_before_selection+=1
                continue
            if row['status']=='ACTIVE' and row['pair'] not in pairs and len(pairs)>=max_pairs:continue
            if row['status']=='ACTIVE' and row['pair'] not in pairs:
                pairs.add(row['pair']);ordered_pairs.append(row['pair'])
            chosen.append(row)
            if len(chosen)>=80:break
        result['deferred']=len(pending)-len(chosen)-expired_before_selection
        # Admission counts as an attempt even if acquisition exhausts its budget;
        # untouched pairs then rotate ahead on the next external tick.
        for row in chosen:repo.attempted(row,stamp)
        snapshot_stamp=stamp
        clock=datetime.fromtimestamp(snapshot_stamp,UTC)
        requirements={}
        for row in chosen:
            if row['status']!='ACTIVE':continue
            need=requirements.setdefault(row['pair'],{'timeframes':set(),'primary_timeframes':set(),'quote':False})
            if row['condition']=='crossing':need['quote']=True
            else:
                try:options=watch_options(row)
                except ValueError:
                    repo.attempted(row,stamp,'Invalid saved alert options; cancel and recreate');continue
                for tf in options['timeframes']:
                    need['primary_timeframes'].add(tf)
                    need['timeframes'].add(tf)
                    if row.get('engulfing'):need['timeframes'].add(LOWER[tf])
        for need in requirements.values():
            need['timeframes']=sorted(need['timeframes'])
            need['primary_timeframes']=sorted(need['primary_timeframes'])
        data_deadline=deadline-min(12,budget_seconds/3)
        data=alert_data.load(ordered_pairs,clock,deadline=data_deadline,requirements=requirements,max_pairs=max_pairs) if refresh and pairs else {}
        stamp=int(time.time() if now is None else now)
        # Keep clock/snapshot_stamp unchanged for fetched candles. A slow fetch
        # cannot provide candles closing after its original request cutoff.
        bar_cache={}
        for row in chosen:
            if time.monotonic()>=deadline:result['deferred']+=len(chosen)-result['processed'];break
            result['processed']+=1
            if row['status']=='ACTIVE':
                market=data.get(row['pair'],{})
                try:
                    if row['condition']=='crossing':
                        price,qtime=market.get('quote'),market.get('quote_time')
                        if int(row['expires_at'])<stamp and (not fresh_quote(price,qtime,stamp) or int(qtime)>int(row['expires_at'])):
                            repo.expire(row,stamp,'Expired before another fresh price sample');continue
                        if not fresh_quote(price,qtime,stamp):raise ValueError('fresh quote unavailable')
                        repo.attempted(row,stamp)
                        fired=repo.observe_quote(row,price,qtime,stamp)
                        if fired:row=fired;result['triggered']+=1
                        else:
                            if int(row['expires_at'])<=stamp:repo.expire(row,stamp)
                            continue
                    else:
                        repo.attempted(row,stamp)
                        event,checked,missing=evaluate_market(row,market,clock,snapshot_stamp,bar_cache)
                        if event:
                            if repo.trigger(row,event):
                                frozen,payload=freeze_event(row,event)
                                row={**row,'status':'TRIGGERED','event_time':event['time'],'event_payload':payload}
                                result['triggered']+=1
                            else:continue
                        else:
                            if checked:
                                if row.get('options_json'):repo.checked(row,max(checked.values()),checked)
                                else:repo.checked(row,max(checked.values()))
                            if missing:
                                repo.attempted(row,snapshot_stamp,'Fresh broker data unavailable for '+', '.join(missing)+'; retry pending')
                                result['failed']+=1
                            if int(row['expires_at'])<=snapshot_stamp and not missing:repo.expire(row,stamp)
                            continue
                except Exception:
                    repo.attempted(row,snapshot_stamp,'Fresh broker data unavailable; retry pending');result['failed']+=1;continue
            if row['status']=='TRIGGERED':
                sent=repo.deliver(row,sender or (lambda text,chat:send_with_budget(text,chat,deadline)),int(time.time() if now is None else now))
                if sent is True:result['sent']+=1
                elif sent is False:result['failed']+=1
    return result


if __name__=='__main__':
    from . import db
    db.apply_schema()
    print(json.dumps(tick()))

"""Separate Bishop paper runner; reads the existing selected-market candle store.

No broker connection, token refresh, live order or Kevin-table writes. One bounded
child per market isolates expensive source-engine work from the KK live scan.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

UTC=timezone.utc
ENTRY_TFS=('H4','H3','H2','H1')
TERMINAL={'WIN','LOSS','BREAK_EVEN','EXPIRED','CANCELLED','REPLACED'}
SCHEMA='''
CREATE TABLE IF NOT EXISTS bishop_app_entries (
 user_id BIGINT NOT NULL, signal_id VARCHAR(64) NOT NULL, pair VARCHAR(16) NOT NULL,
 status VARCHAR(24) NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
 payload MEDIUMTEXT NOT NULL, PRIMARY KEY(user_id,signal_id),
 KEY ix_bishop_user_time(user_id,created_at), KEY ix_bishop_pair(user_id,pair)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS bishop_app_state (
 user_id BIGINT NOT NULL, pair VARCHAR(16) NOT NULL, activated_at BIGINT NOT NULL,
 checked_at BIGINT NOT NULL DEFAULT 0, note VARCHAR(200) NOT NULL DEFAULT '',
 PRIMARY KEY(user_id,pair)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS bishop_app_outbox (
 user_id BIGINT NOT NULL, event_id VARCHAR(128) NOT NULL, payload TEXT NOT NULL,
 sent_at BIGINT NULL, lease_until BIGINT NOT NULL DEFAULT 0, lease_token VARCHAR(32) NULL,
 PRIMARY KEY(user_id,event_id), KEY ix_bishop_delivery(sent_at,lease_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
'''


def iso(stamp):return datetime.fromtimestamp(int(stamp),UTC).isoformat()
def encode(value):return json.dumps(value,separators=(',',':'),sort_keys=True,allow_nan=False)


def feed_from_store(pair, now):
    """Read the primary store directly: never append the Dukascopy overlay."""
    from slk import store,instruments,settings
    from bishop.v2.types import Instrument,Bar
    from bishop.v2.aggregation import expected_slots
    saved=store.Pair(pair)
    continuous=instruments.deriv_continuous(pair)
    if saved.src=='deriv' and continuous:
        calendar,anchor,venue='24x7_utc_v1','utc_epoch_v1','Deriv'
    elif saved.src=='ctrader' and pair in settings.PAIRS:
        calendar,anchor,venue='fx_ny_v1','ny17_wall_v2','IC Markets cTrader'
    else:
        raise ValueError('Bishop needs primary cTrader FX or continuous Deriv data; this market/calendar is not supported yet')
    digits=(saved.sym or {}).get('digits')
    if digits is None:raise ValueError('Broker price precision unavailable')
    tick=Decimal(1).scaleb(-int(digits))
    inst=Instrument(pair,str(tick),str(instruments.pip(pair)),calendar,anchor,'MID' if saved.src=='deriv' else 'BID',saved.src+':'+pair,venue)
    clock=datetime.fromisoformat(now)
    lower=clock-timedelta(days=180)
    h=saved.frame(int(lower.timestamp()))
    bars=[]
    for at,row in h.iterrows():
        start=at.to_pydatetime();end=start+timedelta(hours=1)
        if end>clock:continue
        prices=[]
        for name in ('open','high','low','close'):
            raw=Decimal(str(row[name]));rounded=raw.quantize(tick)
            if abs(raw-rounded)>tick/Decimal('1000'):raise ValueError('Material off-grid broker price')
            prices.append(inst.to_ticks(rounded))
        bars.append(Bar(pair,'H1',start,end,*prices,end,inst.source_id,'0'))
    if len(bars)<240:raise ValueError('Insufficient closed H1 history for Bishop context')
    if next(expected_slots(bars[-1].end,clock.replace(minute=0,second=0,microsecond=0),'H1',calendar),None) is not None:
        raise ValueError('Latest closed broker hour is missing; Bishop scan deferred')
    return {'instrument':inst,'bars':tuple(bars),'manifest':{'calendar':calendar,'base_tf':'H1'},'hashes':{}}


def thaw_order(raw):
    from bishop.v2.types import Order,Clock
    return Order(**{**raw,'clock':Clock(**raw['clock'])})


def history_hash(bars,order,until):
    import hashlib
    return hashlib.sha256(encode([(b.start.isoformat(),b.end.isoformat(),b.open_ticks,b.high_ticks,b.low_ticks,b.close_ticks)
        for b in bars if b.start>=order.available_at and b.available_at<=until]).encode()).hexdigest()


def compute(payload):
    """Pure engine + frozen-order replay. Used only in a time-bounded child."""
    from bishop.v2.engine import run
    from bishop.v2.types import StrategyPolicy,Instrument,jsonable,utc
    from bishop.v2.simulation import simulate,Costs
    feed=feed_from_store(payload['pair'],payload['now'])
    policy=StrategyPolicy(source_profile='bishop_confirmation',entry_tfs=ENTRY_TFS)
    costs=Costs()  # explicit zero-cost hypothesis, shown on every paper result
    detection={**feed,'bars':tuple(b for b in feed['bars'] if b.start>=utc(payload['now'])-timedelta(days=35))}
    result=run(detection,as_of=payload['now'],scan_start=payload['since'],policy=policy,costs=costs,compact_story_diagnostics=True)
    setups={s['id']:s for s in result['setups']}
    observations={o['id']:o for o in result['observations']}
    events=result['execution_events']
    incoming={o['id']:dict(order=o,setup=setups[o['setup_id']],observation=observations[o['id']],
                  actions=[a for a in result['actions'] if a['order_id']==o['id']],
                  instrument=result['instrument'],costs=result['costs'],calendar=feed['manifest']['calendar'],
                  policy_id=policy.id,source_status=result['status']) for o in result['orders']}
    # Geometry and policy for already published entries are immutable. A rolling
    # context losing a setup is not a cancellation and must not replace its plan.
    if not payload.get('new_entries',True):incoming={}
    for saved in payload.get('existing',[]):
        saved=dict(saved);saved.pop('tracking_suspended',None)
        order=thaw_order(saved['order']);inst=Instrument(**saved['instrument'])
        if inst!=feed['instrument']:raise ValueError('Frozen Bishop source/price metadata changed')
        if saved['observation']['outcome']=='CENSORED':
            incoming[order.id]=saved; continue
        if order.available_at<feed['bars'][0].start:
            saved={**saved,'observation':{**saved['observation'],'outcome':'CENSORED','net_r':None,'censor_reason':'Original active history is outside retained window'}}
        elif saved.get('history_hash') and history_hash(feed['bars'],order,utc(saved['history_to']))!=saved['history_hash']:
            saved={**saved,'observation':{**saved['observation'],'outcome':'CENSORED','net_r':None,'censor_reason':'Previously observed broker candles changed; original paper evidence retained'}}
        else:
            actions={encode(a):a for a in saved.get('actions',[])}
            for event in result['story_events']:
                if (event['reference_id']==order.details.get('story_id') and utc(event['clock']['available_at'])>=order.available_at
                    and (event['kind'] in ('STORY_INVALIDATED','STORY_DESTINATION_REACHED','STORY_CANCELLED','STORY_FLIPPED') or event.get('details',{}).get('pending_action')=='CANCEL_DEPENDENT')):
                    a=dict(order_id=order.id,kind='CANCEL',available_at=event['clock']['available_at'],reason=event['kind'])
                    actions[encode(a)]=a
            replay=simulate((order,),feed['bars'],inst,Costs(**saved['costs']),utc(payload['now']),tuple(actions.values()),calendar=saved['calendar'])
            saved={**saved,'observation':jsonable(replay['observations'][0]),'actions':list(actions.values())}
            events.extend(jsonable(replay['events']))
        incoming[order.id]=saved
    for row in incoming.values():
        if row['observation']['outcome']!='CENSORED':
            row['history_to']=payload['now']
            row['history_hash']=history_hash(feed['bars'],thaw_order(row['order']),utc(payload['now']))
        row['evaluated_at']=payload['now']
        ident=row['order']['id'];own=[e for e in events if e['reference_id']==ident]
        row['filled_at']=next((e['clock']['available_at'] for e in own if e['kind']=='ORDER_FILLED'),row.get('filled_at'))
        row['closed_at']=next((e['clock']['available_at'] for e in reversed(own) if e['kind'].startswith('POSITION_') and row['observation']['outcome'] in TERMINAL),row.get('closed_at'))
    return {'entries':list(incoming.values()),'note':result['status']+'; 35-day context; H1/H2/H3/H4 only; zero-cost paper'}


def display_status(row):
    if row.get('tracking_suspended'):return 'SUSPENDED'
    obs=row['observation'];outcome=obs['outcome']
    if outcome=='CENSORED':return 'UNKNOWN'
    if outcome=='OPEN':return 'TRIGGERED' if obs['status']=='FILLED' else 'PENDING'
    return outcome


def public_entry(row):
    order=row['order'];obs=row['observation'];tick=Decimal(row['instrument']['tick_size'])
    price=lambda v:float(Decimal(v)*tick) if v is not None else None
    return dict(id='bishop:'+order['id'],strategy='bishop',strategy_label='Bishop · Paper',pair=order['instrument'],
                tf=order['tf'],side=order['side'],model=order['model'],entry=price(order['entry_ticks']),
                stop=price(order['stop_ticks']),tp1=None,tp2=price(order['target_ticks']),status=display_status(row),
                result_r=float(obs['net_r']) if obs.get('net_r') is not None else None,result_r_tp2=None,
                created_at=order['clock']['available_at'],filled_at=row.get('filled_at'),closed_at=row.get('closed_at'),
                bias_id=None,paper_only=True,cost_note='Zero-cost paper estimate',
                note=row.get('tracking_suspended') or obs.get('censor_reason') or 'Bishop confirmation profile · H4/H3/H2/H1',
                evaluated_at=row.get('evaluated_at'),policy_id=row['policy_id'],source=row['instrument']['source_id'])


def message(row):
    e=public_entry(row)
    lines=[f"Bishop · PAPER | {e['pair']} | {e['tf']} | {e['side']} | {e['model']} | {e['status']}",
           f"Entry {e['entry']}  Stop {e['stop']}  Target {e['tp2']}",
           f"Setup {e['created_at']}"]
    if e['result_r'] is not None:lines.append(f"Paper result {e['result_r']:+.2f}R")
    lines.append(e['note'])
    lines.append('Zero-cost paper estimate · no broker order')
    return '\n'.join(lines)


class Repository:
    """Shared tables always use explicit recipient ownership."""
    def __init__(self,db):self.db=db
    def apply_schema(self):
        for stmt in SCHEMA.split(';'):
            if stmt.strip():self.db.execute(stmt)
    def rows(self,uid,pair=None,active=False):
        sql='SELECT payload FROM bishop_app_entries WHERE user_id=%s';args=[int(uid)]
        if pair:sql+=' AND pair=%s';args.append(pair)
        if active:sql+=" AND status NOT IN ('WIN','LOSS','BREAK_EVEN','EXPIRED','CANCELLED','REPLACED')"
        sql+=' ORDER BY created_at DESC LIMIT 500'
        return [json.loads(r['payload']) for r in self.db.query(sql,args)]
    def states(self,uid):return self.db.query('SELECT pair,activated_at,checked_at,note FROM bishop_app_state WHERE user_id=%s ORDER BY checked_at,pair',(int(uid),))
    def activate(self,uid,pair,stamp):
        self.db.execute('INSERT IGNORE INTO bishop_app_state(user_id,pair,activated_at,checked_at,note) VALUES(%s,%s,%s,0,%s)',(int(uid),pair,stamp,'Activated; waiting for a new completed setup'))
    def note(self,uid,pair,stamp,note):
        self.db.execute('UPDATE bishop_app_state SET checked_at=%s,note=%s WHERE user_id=%s AND pair=%s',(stamp,note[:200],int(uid),pair))
    def persist(self,uid,pair,rows,stamp,alerts=True):
        # Workflow and manual runs share the existing feed lock; writes additionally
        # hold row locks so web reads and delivery never see half-written evidence.
        conn=self.db.connect()
        try:
            conn.begin()
            with conn.cursor() as cur:
                for row in rows:
                    ident=row['order']['id'];status=display_status(row)
                    cur.execute('SELECT payload,status,updated_at FROM bishop_app_entries WHERE user_id=%s AND signal_id=%s FOR UPDATE',(int(uid),ident))
                    found=cur.fetchone()
                    if found:
                        if int(found['updated_at'])>stamp:continue
                        old=json.loads(found['payload'])
                        if old['order']!=row['order'] or old['instrument']!=row['instrument'] or old['costs']!=row['costs']:
                            raise ValueError('Published Bishop geometry/source/costs cannot change')
                        if found['status'] in TERMINAL:continue
                    else:
                        cur.execute("SELECT COUNT(*) AS n FROM bishop_app_entries WHERE user_id=%s AND pair=%s AND status IN ('PENDING','TRIGGERED','UNKNOWN','SUSPENDED')",(int(uid),pair))
                        if int(cur.fetchone()['n'])>=10:continue
                    created=int(datetime.fromisoformat(row['order']['clock']['available_at']).timestamp())
                    cur.execute('INSERT INTO bishop_app_entries(user_id,signal_id,pair,status,created_at,updated_at,payload) VALUES(%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE status=VALUES(status),updated_at=VALUES(updated_at),payload=VALUES(payload)',(int(uid),ident,pair,status,created,stamp,encode(row)))
                    if alerts and (not found or found['status']!=status):
                        event=ident+':'+status
                        cur.execute('INSERT IGNORE INTO bishop_app_outbox(user_id,event_id,payload) VALUES(%s,%s,%s)',(int(uid),event,message(row)))
            conn.commit()
        except Exception:conn.rollback();raise
        finally:conn.close()
    def deliver(self,uid,sender,stamp,deadline=None):
        import secrets
        conn=self.db.connect()
        try:
            for row in self.db.query('SELECT event_id,payload FROM bishop_app_outbox WHERE user_id=%s AND sent_at IS NULL AND lease_until<=%s LIMIT 20',(int(uid),stamp)):
                if deadline is not None and time.monotonic()+25>=deadline:break
                token=secrets.token_hex(16)
                with conn.cursor() as cur:
                    won=cur.execute('UPDATE bishop_app_outbox SET lease_token=%s,lease_until=%s WHERE user_id=%s AND event_id=%s AND sent_at IS NULL AND lease_until<=%s',(token,stamp+600,int(uid),row['event_id'],stamp))
                if not won:continue
                try:ok=sender(row['payload'],chat=int(uid))
                except Exception:ok=False
                if ok:
                    self.db.execute('UPDATE bishop_app_outbox SET sent_at=%s,lease_until=0 WHERE user_id=%s AND event_id=%s AND lease_token=%s',(stamp,int(uid),row['event_id'],token))
        finally:conn.close()


def scan(*,budget=360,timeout=15,now=None,worker=None):
    from slk import db,tenancy,settings
    from slk.live import send_telegram,weekend_paused
    clock=now or datetime.now(UTC);stamp=int(clock.timestamp());deadline=time.monotonic()+budget
    repo=Repository(db);repo.apply_schema()
    users=sorted({tenancy.owner_id(),*(int(r['user_id']) for r in db.query('SELECT user_id FROM app_users'))})
    cursor=int(db.get_setting('bishop_scan_user_cursor','0') or '0')
    users=[u for u in users if u>cursor]+[u for u in users if u<=cursor]
    done=errors=deferred=0
    for uid in users:
        if time.monotonic()+timeout+2>=deadline:break
        with tenancy.scope(uid):vals=settings.load(db.get_settings())
        pairs=vals['pairs'] or (settings.PAIRS if uid==tenancy.owner_id() else tenancy.STARTER['pairs'].split(','))
        preference_selected=set(pairs)
        if weekend_paused(clock) and os.environ.get('GITHUB_EVENT_NAME')=='schedule':
            from slk import instruments
            pairs=[p for p in pairs if instruments.deriv_continuous(p)]
        selected=preference_selected
        # Removing a market stops data acquisition. Show its outstanding paper
        # positions as suspended, rather than manufacturing a close or leaving
        # an apparently current result on the web app.
        active_pairs=[r['pair'] for r in db.query("SELECT DISTINCT pair FROM bishop_app_entries WHERE user_id=%s AND status NOT IN ('WIN','LOSS','BREAK_EVEN','EXPIRED','CANCELLED','REPLACED')",(int(uid),))]
        for removed in set(active_pairs)-selected:
            for row in repo.rows(uid,removed,active=True):
                row['tracking_suspended']='Tracking suspended: this market is no longer selected'
                db.execute('UPDATE bishop_app_entries SET status=%s,payload=%s WHERE user_id=%s AND signal_id=%s',('SUSPENDED',encode(row),int(uid),row['order']['id']))
        if not vals['bishop_paper_entries']:pairs=[p for p in pairs if p in active_pairs]
        states={r['pair']:r for r in repo.states(uid)}
        for pair in pairs:
            if pair not in states:repo.activate(uid,pair,stamp)
        # Previously checked markets rotate behind deferred markets. A persisted
        # account cursor also rotates users when the overall budget is reached.
        pairs=sorted(pairs,key=lambda p:(states.get(p,{}).get('checked_at',0),p))
        for pair in pairs:
            if pair not in states:continue  # activation never backfills old entries
            if time.monotonic()+timeout+2>=deadline:deferred+=1;continue
            existing=repo.rows(uid,pair,active=True)
            since=max(int(states[pair]['activated_at']),stamp-7*86400)
            payload={'pair':pair,'now':iso(stamp),'since':iso(since),'existing':existing,'new_entries':vals['bishop_paper_entries']}
            try:
                if worker:result=worker(payload)
                else:
                    proc=subprocess.run([sys.executable,'-m','slk.bishop_paper','--compute'],input=encode(payload),text=True,capture_output=True,timeout=timeout,check=True)
                    result=json.loads(proc.stdout)
                if 'error' in result:raise ValueError(result['error'])
                repo.persist(uid,pair,result['entries'],stamp,alerts=vals['alert_entry'])
                repo.note(uid,pair,stamp,result['note']);done+=1
            except subprocess.TimeoutExpired:
                repo.note(uid,pair,stamp,'Deferred: Bishop computation reached its time budget');deferred+=1
            except Exception as exc:
                # Only controlled error text is stored; subprocess stderr may
                # contain broker library output and is never echoed.
                note=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
                repo.note(uid,pair,stamp,('Bishop unavailable: '+note)[:200]);errors+=1
        if vals['alert_entry']:repo.deliver(uid,send_telegram,stamp,deadline=deadline)
        db.set_setting('bishop_scan_user_cursor',str(uid))
    db.execute("DELETE FROM bishop_app_outbox WHERE sent_at IS NOT NULL AND sent_at<%s",(stamp-30*86400,))
    db.execute("DELETE FROM bishop_app_entries WHERE status IN ('WIN','LOSS','BREAK_EVEN','EXPIRED','CANCELLED','REPLACED') AND updated_at<%s",(stamp-30*86400,))
    print(encode({'strategy':'Bishop','paper_only':True,'markets_ok':done,'unavailable':errors,'deferred':deferred}),flush=True)
    return 0  # Bishop availability must never turn a successful KK scan red


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compute',action='store_true')
    args=parser.parse_args()
    if args.compute:
        try:print(encode(compute(json.load(sys.stdin))))
        except ValueError as exc:print(encode({'error':str(exc)}))
        return 0
    from slk import db
    from slk.jobs import feed_lock
    with feed_lock(db,wait=0) as acquired:
        if not acquired:
            print('Bishop paper scan deferred: shared scanner is busy');return 0
        return scan()


if __name__=='__main__':raise SystemExit(main())

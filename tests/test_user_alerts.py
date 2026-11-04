import json
from datetime import datetime, timezone
import pandas as pd
import pytest
from slk import user_alerts as A


def frame(rows,start='2026-10-20 00:00Z'):
    return pd.DataFrame(rows,columns=['open','high','low','close'],index=pd.date_range(start,periods=len(rows),freq='h'))


def watch(**kw):
    created=int(pd.Timestamp('2026-10-19 23:59Z').timestamp())
    return dict(id=1,user_id=42,pair='DVR75',condition='close_above',timeframe='H1',side='EITHER',
                level=10.,engulfing=False,created_at=created,last_checked=created,
                expires_at=created+7*86400,note='',**kw)


def test_validation_known_symbols_and_unsupported_lower_data():
    base=dict(pair='DVR75',condition='fourth_man',level=10,timeframe='H4',engulfing=True)
    assert A.validate(base,100)['expires_at']==86500
    for changes in ({'pair':'DVUNKNOWN'},{'timeframe':'M2'},{'level':float('nan')},
                    {'level':True},{'engulfing':'yes'},{'condition':'rejection'},{'expires_hours':1.1},
                    {'chat_id':99},{'condition':[]},{'timeframe':{}},{'side':[]}):
        with pytest.raises(ValueError):A.validate({**base,**changes},100)


def test_candle_close_never_uses_forming_or_precreation_bar():
    h=frame([(9,12,8,11),(11,15,9,14)])
    w=watch()
    assert A.evaluate(w,h,pd.Timestamp('2026-10-20 00:59Z')) is None
    e=A.evaluate(w,h,pd.Timestamp('2026-10-20 01:00Z'))
    assert e['time']==int(pd.Timestamp('2026-10-20 01:00Z').timestamp())
    assert A.evaluate({**w,'created_at':e['time'],'last_checked':e['time']},h.iloc[:1],pd.Timestamp('2026-10-20 03:00Z')) is None


def test_pinbar_preserves_other_extreme_and_mirrors_sell():
    h=frame([(10,14,8,11),(9,13,7,12)])
    w={**watch(),'condition':'fourth_man'}
    assert A.evaluate(w,h,pd.Timestamp('2026-10-20 02:00Z'))['side']=='BUY'
    both=h.copy();both.iloc[1]=[9,15,7,12]
    assert A.evaluate(w,both,pd.Timestamp('2026-10-20 02:00Z')) is None
    mirrored=h.copy()
    mirrored[['open','high','low','close']]=pd.DataFrame({'open':20-h.open,'high':20-h.low,'low':20-h.high,'close':20-h.close},index=h.index)
    assert A.evaluate(w,mirrored,pd.Timestamp('2026-10-20 02:00Z'))['side']=='SELL'



def test_h4_partial_and_gap_rejected():
    h=frame([(9,12,8,11)]*4)
    w={**watch(),'timeframe':'H4'}
    assert A.evaluate(w,h,pd.Timestamp('2026-10-20 03:59Z')) is None
    assert A.evaluate(w,h,pd.Timestamp('2026-10-20 04:00Z'))
    assert A.evaluate(w,h.drop(h.index[1]),pd.Timestamp('2026-10-20 04:00Z')) is None


def test_expiry_and_checked_cutoff():
    h=frame([(9,12,8,11)]*2)
    e=A.evaluate(watch(),h,pd.Timestamp('2026-10-20 02:00Z'))
    assert A.evaluate({**watch(),'expires_at':e['time']-1},h,pd.Timestamp('2026-10-20 02:00Z')) is None
    assert A.evaluate({**watch(),'last_checked':int(pd.Timestamp('2026-10-20 02:00Z').timestamp())},h,pd.Timestamp('2026-10-20 02:00Z')) is None



def test_delivery_claim_is_owned_and_failed_send_can_retry():
    row={**watch(),'status':'TRIGGERED','event_payload':json.dumps({'time':1000,'side':'BUY','close':11,'condition':'close_above','timeframe':'H1'})}
    class Fake(A.Repository):
        def __init__(self):self.calls=[];self.acks=[]
        def execute(self,sql,args):self.calls.append((sql,args));return 1
        def query(self,sql,args):
            self.calls.append((sql,args));return [row]
        def acknowledge(self,current,token,stamp):self.acks.append((current,token,stamp));return True
    repo=Fake()
    assert repo.deliver(row,lambda text,chat:chat==42,2000)
    assert all('user_id=%s' in sql for sql,args in repo.calls)
    assert 'lease_until<=%s' in repo.calls[0][0] and repo.acks[0][0]['user_id']==42
    repo=Fake()
    assert repo.deliver(row,lambda *a,**kw:False,2000) is False
    assert not repo.acks
    assert 'lease_token=%s' in repo.calls[-1][0] and 'retry pending' in repo.calls[-1][0]


def test_quote_crossing_requires_baseline_new_fresh_sample_and_watch_time():
    w={**watch(),'condition':'crossing','level':10.,'last_quote':9.,'quote_time':1000,'created_at':900,'expires_at':2000}
    assert A.quote_event(w,11.,1100,1105)['side']=='BUY'
    assert A.quote_event({**w,'last_quote':None},11.,1100,1105) is None
    assert A.quote_event(w,11.,1000,1105) is None
    assert A.quote_event(w,11.,1100,1300) is None
    assert A.quote_event(w,11.,1106,1105) is None
    assert A.quote_event({**w,'created_at':1101},11.,1100,1105) is None
    assert A.quote_event({**w,'expires_at':1099},11.,1100,1105) is None
    assert A.quote_event({**w,'side':'SELL'},11.,1100,1105) is None


def test_delayed_tick_keeps_preexpiry_candle_event():
    h=frame([(9,12,8,11),(11,12,10,11)])
    end=int(pd.Timestamp('2026-10-20 01:00Z').timestamp())
    w={**watch(),'expires_at':end+1800}
    assert A.evaluate(w,h,pd.Timestamp('2026-10-20 02:35Z'))['time']==end


def test_missing_candles_do_not_become_adjacent_crossing_or_cisd():
    h=frame([(9,12,8,9),(9,12,8,9),(9,13,8,12)]).drop(pd.Timestamp('2026-10-20 01:00Z'))
    w={**watch(),'condition':'closed_crossing'}
    assert A.evaluate(w,h,pd.Timestamp('2026-10-20 03:00Z')) is None


def test_rejection_close_direction_is_not_a_sell_above_level():
    h=frame([(11,12,9,11)])
    assert A.evaluate({**watch(),'condition':'rejection','side':'SELL'},h,pd.Timestamp('2026-10-20 01:00Z')) is None
    assert A.evaluate({**watch(),'condition':'rejection','side':'BUY'},h,pd.Timestamp('2026-10-20 01:00Z'))['side']=='BUY'


def test_minute_alert_waits_for_exact_m5_close_and_rejects_missing_components():
    h=pd.DataFrame([(9,12,8,11)]*5,columns=['open','high','low','close'],index=pd.date_range('2026-10-20 00:00Z',periods=5,freq='min'))
    h.attrs['granularity']=60
    w={**watch(),'timeframe':'M5'}
    assert A.evaluate(w,h,pd.Timestamp('2026-10-20 00:04:59Z')) is None
    assert A.evaluate(w,h,pd.Timestamp('2026-10-20 00:05:00Z'))['time']==int(pd.Timestamp('2026-10-20 00:05Z').timestamp())
    assert A.evaluate(w,h.drop(h.index[2]),pd.Timestamp('2026-10-20 00:05Z')) is None


def test_tick_checks_preexpiry_event_before_expiring_and_uses_valid_partial_data(monkeypatch):
    from slk import alert_data
    h=frame([(9,12,8,11),(11,12,10,11)])
    created=int(pd.Timestamp('2026-10-19 23:59Z').timestamp())
    now=int(pd.Timestamp('2026-10-20 02:35Z').timestamp())
    row={**watch(),'status':'ACTIVE','created_at':created,'expires_at':created+91*60}
    events=[]
    class Fake:
        def __init__(self,db):pass
        def __enter__(self):return self
        def __exit__(self,*exc):pass
        def pending(self,stamp):return [row]
        def attempted(self,*args):pass
        def trigger(self,row,event):events.append(('trigger',event['time']));return True
        def checked(self,*args):events.append(('checked',))
        def expire(self,*args):events.append(('expire',))
        def deliver(self,row,sender,stamp):events.append(('sent',row['user_id']));return True
    monkeypatch.setattr(A,'Repository',Fake)
    monkeypatch.setattr(alert_data,'load',lambda *a,**kw:{'DVR75':{'hourly':h,'error':'M1 unavailable'}})
    result=A.tick(now=now)
    assert result['sent']==1 and result['triggered']==1
    assert events==[('trigger',int(pd.Timestamp('2026-10-20 01:00Z').timestamp())),('sent',42)]


def test_real_mysql_owned_quota_baseline_and_delivery_claims(monkeypatch):
    import os
    import time
    import secrets
    from pathlib import Path
    from concurrent.futures import ThreadPoolExecutor
    from slk import db
    if not os.environ.get('SLK_TEST_MYSQL'):pytest.skip('requires disposable MySQL8')
    monkeypatch.setenv('DATABASE_URL',os.environ['SLK_TEST_MYSQL'])
    uid=int(time.time())*10000+secrets.randbelow(9000)
    with A.Repository(db) as repo:
        for stmt in (Path(__file__).resolve().parents[1]/'db/user_alerts.sql').read_text().split(';'):
            if stmt.strip():repo.execute(stmt)
    now=int(time.time())
    data=A.validate({'pair':'DVR75','condition':'crossing','level':10},now-30)
    monkeypatch.setattr(A,'MAX_ACTIVE',1)
    def create(_):
        try:
            with A.Repository(db) as repo:return repo.create(uid,data)
        except ValueError:return None
    try:
        with ThreadPoolExecutor(2) as pool:created=list(pool.map(create,range(2)))
        rows=[r for r in created if r]
        assert len(rows)==1
        row=rows[0]
        with A.Repository(db) as repo:
            assert repo.list(uid+1)==[]
            assert repo.cancel(uid+1,row['id'],now) is None
            assert repo.observe_quote(row,9,now-10,now) is None
            fired=repo.observe_quote(row,11,now-1,now)
            assert fired['status']=='TRIGGERED'
            assert repo.observe_quote(row,9,now,now) is None
        sent=[]
        def deliver(_):
            with A.Repository(db) as repo:return repo.deliver(fired,lambda text,chat:sent.append(chat) or True,now)
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(deliver,range(2)))
        assert results.count(True)==1 and sent==[uid]
        with A.Repository(db) as repo:assert repo.list(uid)[0]['status']=='FIRED'
    finally:
        with A.Repository(db) as repo:
            repo.execute('DELETE FROM manual_alerts WHERE user_id=%s',(uid,))
            repo.execute('DELETE FROM manual_alert_users WHERE user_id=%s',(uid,))


def _fake_tick_repo(monkeypatch, rows, events):
    class Fake:
        def __init__(self,db):pass
        def __enter__(self):return self
        def __exit__(self,*exc):pass
        def pending(self,stamp):return rows
        def attempted(self,row,stamp,error=None):
            if error:events.append(('error',error))
        def trigger(self,row,event):events.append(('trigger',event['time']));return True
        def checked(self,*args):events.append(('checked',))
        def expire(self,*args):events.append(('expire',))
        def deliver(self,row,sender,stamp):events.append(('sent',row['user_id']));return True
    monkeypatch.setattr(A,'Repository',Fake)


def test_tick_uses_captured_snapshot_when_acquisition_crosses_minute_boundary(monkeypatch):
    from slk import alert_data
    snapshot=int(pd.Timestamp('2026-10-20 00:05Z').timestamp())
    clock={'now':snapshot}
    h=pd.DataFrame([(9,12,8,11)]*5,columns=['open','high','low','close'],index=pd.date_range('2026-10-20 00:00Z',periods=5,freq='min'))
    h.attrs['granularity']=60
    events=[]
    _fake_tick_repo(monkeypatch,[{**watch(),'status':'ACTIVE','timeframe':'M5'}],events)
    def load(*args,**kw):
        clock['now']=snapshot+120
        return {'DVR75':{'frame':h}}
    monkeypatch.setattr(A.time,'time',lambda:clock['now'])
    monkeypatch.setattr(alert_data,'load',load)
    result=A.tick()
    assert result['sent']==1 and ('trigger',snapshot) in events
    assert not any(event[0]=='error' for event in events)


@pytest.mark.parametrize('tf',['H1','W'])
def test_fx_friday_final_close_remains_eligible_during_weekend(monkeypatch,tf):
    from slk import alert_data
    close=pd.Timestamp('2026-10-23 21:00Z')  #17:00 New York
    start=pd.Timestamp('2026-10-18 21:00Z') if tf=='W' else close-pd.Timedelta(hours=1)
    h=pd.DataFrame([(9,12,8,11)]*int((close-start).total_seconds()/3600),columns=['open','high','low','close'],index=pd.date_range(start,close,freq='h',inclusive='left'))
    created=int((start-pd.Timedelta(minutes=1)).timestamp())
    snapshot=int(pd.Timestamp('2026-10-24 02:05Z').timestamp())
    row={**watch(),'pair':'EURUSD','status':'ACTIVE','timeframe':tf,'created_at':created,'last_checked':created,'expires_at':snapshot-3600}
    events=[]
    _fake_tick_repo(monkeypatch,[row],events)
    monkeypatch.setattr(alert_data,'load',lambda *a,**kw:{'EURUSD':{'hourly':h}})
    result=A.tick(now=snapshot)
    assert result['sent']==1 and ('trigger',int(close.timestamp())) in events
    assert not any(event[0] in ('error','expire') for event in events)


@pytest.mark.parametrize('condition,expired_for',[('crossing',60),('close_above',86401)])
def test_expired_unrecoverable_watches_do_not_fetch_or_fill_pending_queue(monkeypatch,condition,expired_for):
    from slk import alert_data
    now=int(pd.Timestamp('2026-10-24 02:05Z').timestamp())
    row={**watch(),'status':'ACTIVE','condition':condition,'expires_at':now-expired_for}
    events=[]
    _fake_tick_repo(monkeypatch,[row],events)
    monkeypatch.setattr(alert_data,'load',lambda *a,**kw:pytest.fail('expired watch must not acquire broker data'))
    result=A.tick(now=now)
    assert events==[('expire',)] and result['sent']==0 and result['failed']==0


def test_candle_expiring_during_acquisition_waits_for_final_snapshot(monkeypatch):
    from slk import alert_data
    snapshot=int(pd.Timestamp('2026-10-20 00:04Z').timestamp())
    clock={'now':snapshot}
    h=pd.DataFrame([(9,12,8,11)]*4,columns=['open','high','low','close'],index=pd.date_range('2026-10-20 00:00Z',periods=4,freq='min'))
    h.attrs['granularity']=60
    row={**watch(),'status':'ACTIVE','timeframe':'M5','expires_at':snapshot+60}
    events=[]
    _fake_tick_repo(monkeypatch,[row],events)
    def load(*args,**kw):clock['now']=snapshot+120;return {'DVR75':{'frame':h}}
    monkeypatch.setattr(A.time,'time',lambda:clock['now'])
    monkeypatch.setattr(alert_data,'load',load)
    result=A.tick()
    assert ('expire',) not in events and result['sent']==0


def test_pending_prunes_only_quotes_and_outside_bounded_candle_window():
    class Fake(A.Repository):
        def __init__(self):self.calls=[]
        def execute(self,sql,args):self.calls.append((sql,args));return 0
        def query(self,sql,args=()):return []
    repo=Fake();repo.pending(200000)
    sql,args=repo.calls[1]
    assert "status='ACTIVE'" in sql and "`condition`='crossing'" in sql
    assert args==(200000,200000-86400)
    assert 'outside retained candle catch-up window' in sql


def test_short_direct_scan_budget_and_requirements_keep_deferred_pair_rotation(monkeypatch):
    from slk import alert_data
    now=int(pd.Timestamp('2026-10-20 08:00Z').timestamp())
    pairs=['EURUSD','DVR25','DVR75','DV1HZ100V','GBPUSD']
    rows=[{**watch(),'id':i+1,'pair':pair,'status':'ACTIVE','last_attempt':0,'condition':'crossing'} for i,pair in enumerate(pairs)]
    rows.insert(1,{**watch(),'id':99,'pair':'EURUSD','status':'ACTIVE','condition':'fourth_man','timeframe':'H4','engulfing':True,'last_attempt':0})
    captured=[]
    class Fake:
        def __init__(self,db):pass
        def __enter__(self):return self
        def __exit__(self,*exc):pass
        def pending(self,stamp):return sorted(rows,key=lambda row:(row['last_attempt'],row['id']))
        def attempted(self,row,stamp,error=None):row['last_attempt']=stamp
    monkeypatch.setattr(A,'Repository',Fake)
    def load(selected,clock,**kw):captured.append((selected,kw));return {}
    monkeypatch.setattr(alert_data,'load',load)
    result=A.tick(now=now,budget_seconds=40,max_pairs=4)
    selected,options=captured[0]
    assert len(selected)==4 and 'GBPUSD' not in selected and result['deferred']==1
    assert options['max_pairs']==4 and options['deadline']>A.time.monotonic()
    assert options['requirements']['EURUSD']=={'timeframes':['H2','H4'],'primary_timeframes':['H4'],'quote':True}
    assert options['requirements']['DVR25']=={'timeframes':[],'primary_timeframes':[],'quote':True}
    A.tick(now=now+60,budget_seconds=40,max_pairs=4)
    assert 'GBPUSD' in captured[1][0]  # unattempted pair moves ahead of already scanned pairs


@pytest.mark.parametrize('kwargs',[{'budget_seconds':0},{'budget_seconds':float('nan')},{'budget_seconds':True},{'max_pairs':0},{'max_pairs':9},{'max_pairs':1.5}])
def test_direct_scan_bounds_fail_before_opening_database(kwargs,monkeypatch):
    monkeypatch.setattr(A,'Repository',lambda db:pytest.fail('invalid scan bounds must not open database'))
    with pytest.raises(ValueError):A.tick(**kwargs)


def _confirmation_rows(condition, engulfing=True):
    # Normalized geometry of Bishop's drawings, not claimed broker OHLC.
    if condition == 'fourth_man':
        # H2 reference; bearish BUY sweep. H1 two bearish OC candles then invalidation.
        rows=[(12,17,11,16),(16,17,12,16),(16,18,10,14),(14,17,11,12),
              (12,17,9,15),(15,16,10,11)]
    elif condition == 'engulfing':
        rows=[(15,16,12,13),(13,14,11,12),(12,13,8,10),(10,11,8,9),
              (9,11,8,10.5),(10.5,13,9,12.5)]
    else:
        rows=[(11,12,10,11),(11,12,10,11),(11,15,10,14),(14,15,12,14),
              (14,15,10,12),(12,13,8,11),(11,12,9,10),(10,16,9,15)]
    if not engulfing:
        # Preserve parent candle OHLC, remove the lower two-bearish OC sequence.
        if condition=='fourth_man':
            rows[2]=(13,18,10,14);rows[3]=(14,17,11,12)
        elif condition=='engulfing':
            rows[0]=(15,16,10,11);rows[1]=(11,14,10,12)
            rows[2]=(12,13,8,9);rows[3]=(9,11,8,10)
            rows[4]=(10,11,8,11);rows[5]=(11,13,9,12.5)
        else:
            rows[4]=(14,15,10,10);rows[5]=(10,13,8,11)
            rows[6]=(11,12,9,12);rows[7]=(12,16,9,15)
    return rows


@pytest.mark.parametrize('condition',['fourth_man','engulfing','breakout'])
@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('engulfing',[True,False])
def test_confirmation_tick_validated_feed_to_frozen_event_and_delivery(monkeypatch,condition,side,engulfing):
    from slk import alert_data
    rows=_confirmation_rows(condition,engulfing)
    if side=='SELL':rows=[(40-o,40-lo,40-hi,40-c) for o,hi,lo,c in rows]
    h=frame(rows)
    now=h.index[-1]+pd.Timedelta(hours=1)
    valid=alert_data._validated(h,3600,now)
    row={**watch(),'level':10 if side=='BUY' else 30,'side':side,'status':'ACTIVE','condition':condition,'timeframe':'H2','engulfing':True}
    if not engulfing:
        assert A.evaluate({**row,'engulfing':False},valid,now) is not None
    stored=[];sent=[]
    class Fake:
        def __init__(self,db):pass
        def __enter__(self):return self
        def __exit__(self,*exc):pass
        def pending(self,stamp):return [row]
        def attempted(self,*args):pass
        def checked(self,*args):pass
        def trigger(self,current,event):stored.append(event);return True
        def deliver(self,current,sender,stamp):
            assert current['status']=='TRIGGERED'
            return sender(A.message(current,json.loads(current['event_payload'])),chat=current['user_id'])
    monkeypatch.setattr(A,'Repository',Fake)
    monkeypatch.setattr(alert_data,'load',lambda *a,**kw:{'DVR75':{'frame':valid,'hourly':valid}})
    result=A.tick(now=int(now.timestamp()),budget_seconds=40,max_pairs=4,sender=lambda text,chat:sent.append((text,chat)) or True)
    if engulfing:
        assert result['triggered']==result['sent']==1 and result['failed']==0
        assert stored[0]['side']==side and stored[0]['time']==int(now.timestamp())
        assert stored[0]['reference_level'] and stored[0]['stage']=='confirmation; retest pending'
        assert sent[0][1]==42 and 'open-close engulfing confirmed' in sent[0][0]
    else:
        assert result['triggered']==result['sent']==result['failed']==0
        assert stored==sent==[]


def test_data_budget_reserves_delivery_and_rotates_even_when_acquisition_exhausts(monkeypatch):
    from slk import alert_data
    now=int(pd.Timestamp('2026-10-20 01:00Z').timestamp())
    rows=[{**watch(),'id':i+1,'pair':pair,'status':'ACTIVE','last_attempt':0} for i,pair in enumerate(['EURUSD','DVR25','DVR75','DV1HZ100V','GBPUSD'])]
    monotonic={'now':100.}
    records=[]
    h=frame([(9,12,8,11)])
    class Fake:
        def __init__(self,db):pass
        def __enter__(self):return self
        def __exit__(self,*exc):pass
        def pending(self,stamp):return sorted(rows,key=lambda row:(row['last_attempt'],row['id']))
        def attempted(self,row,stamp,error=None):row['last_attempt']=stamp
        def trigger(self,row,event):return True
        def deliver(self,row,sender,stamp):return True
    def load(selected,clock,**kwargs):
        records.append((selected,kwargs['deadline']))
        monotonic['now']=kwargs['deadline']+1  # provider returned late, after its acquisition allowance
        return {'DVR25':{'hourly':h}}
    monkeypatch.setattr(A,'Repository',Fake)
    monkeypatch.setattr(A.time,'monotonic',lambda:monotonic['now'])
    monkeypatch.setattr(alert_data,'load',load)
    result=A.tick(now=now,budget_seconds=40,max_pairs=4)
    assert records[0][1]==128.  # 12 of40seconds are reserved for evaluation/Telegram
    assert result['sent']==1 and result['processed']==4
    assert all(row['last_attempt']==now for row in rows[:4]) and rows[4]['last_attempt']==0
    monotonic['now']=200.
    A.tick(now=now+60,budget_seconds=40,max_pairs=4)
    assert 'GBPUSD' in records[1][0]


def test_telegram_sender_uses_remaining_scan_budget_and_never_starts_after_deadline(monkeypatch):
    import io
    import urllib.request
    calls=[]
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','test-token')
    monkeypatch.setattr(A.time,'monotonic',lambda:100.)
    def urlopen(request,timeout):
        calls.append(timeout)
        assert json.loads(request.data)['chat_id']==42
        return io.BytesIO(b'{"ok":true}')
    monkeypatch.setattr(urllib.request,'urlopen',urlopen)
    assert A.send_with_budget('test',42,103.) is True and calls==[3.]
    assert A.send_with_budget('test',42,100.) is False and calls==[3.]


def test_partial_batch_unloaded_pairs_lead_next_acquisition_not_alphabetical_prefix(monkeypatch):
    from slk import alert_data
    snapshot=int(pd.Timestamp('2026-10-20 01:00Z').timestamp())
    clock={'now':snapshot,'monotonic':100.}
    rows=[{**watch(),'id':i+1,'pair':pair,'status':'ACTIVE','last_attempt':0} for i,pair in enumerate(['EURUSD','DVR25','DVR75','DV1HZ100V'])]
    frames={pair:frame([(9,10,8,9)]) for pair in [row['pair'] for row in rows]}  # no trigger: all remain ACTIVE
    orders=[]
    class Fake:
        def __init__(self,db):pass
        def __enter__(self):return self
        def __exit__(self,*exc):pass
        def pending(self,stamp):return sorted(rows,key=lambda row:(row['last_attempt'],row['id']))
        def attempted(self,row,stamp,error=None):row['last_attempt']=stamp
        def checked(self,*args):pass
    def load(selected,now,**kw):
        orders.append(selected)
        clock['monotonic']=kw['deadline']+1
        clock['now']+=29
        return {pair:{'hourly':frames[pair]} for pair in selected[:2]}
    monkeypatch.setattr(A,'Repository',Fake)
    monkeypatch.setattr(A.time,'time',lambda:clock['now'])
    monkeypatch.setattr(A.time,'monotonic',lambda:clock['monotonic'])
    monkeypatch.setattr(alert_data,'load',load)
    A.tick(budget_seconds=40,max_pairs=4)
    assert orders[0][:2]==['EURUSD','DVR25']
    clock['now']=snapshot+60;clock['monotonic']=200.
    A.tick(budget_seconds=40,max_pairs=4)
    assert orders[1][:2]==['DVR75','DV1HZ100V']

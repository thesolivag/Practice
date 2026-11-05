"""Bishop bridge: primary source, immutable evidence, paper-only and user isolation."""
import copy
import json
import os
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from bishop.v2.types import Instrument,Bar,Order,Clock,jsonable
from bishop.v2.simulation import Costs
from slk import bishop_paper as B

T=datetime(2026,11,2,tzinfo=timezone.utc)


def saved(outcome='OPEN',status='PENDING'):
    inst=Instrument('EURUSD','0.00001','0.0001','fx_ny_v1','ny17_wall_v2','BID','ctrader:EURUSD','IC Markets cTrader')
    order=Order(id='order-test',setup_id='setup-test',instrument='EURUSD',tf='H1',model='confirmation_bo',side='BUY',kind='LIMIT',clock=Clock(T,T,T),entry_ticks=100000,stop_ticks=99900,target_ticks=100200,expires_at=T+timedelta(days=1),details={'story_id':'story-test'})
    return dict(order=jsonable(order),setup={'id':'setup-test'},instrument=jsonable(inst),costs=jsonable(Costs()),calendar='fx_ny_v1',policy_id='frozen',actions=[],observation={'id':'order-test','outcome':outcome,'status':status,'net_r':None},filled_at=None)


def feed(rows=None):
    inst=Instrument(**saved()['instrument'])
    rows=rows or [(100100,100110,100090,100100),(100100,100110,99990,100050),(100050,100210,100020,100200)]
    bars=tuple(Bar('EURUSD','H1',T+timedelta(hours=i),T+timedelta(hours=i+1),*r,source_id=inst.source_id) for i,r in enumerate(rows))
    return {'instrument':inst,'bars':bars,'manifest':{'calendar':'fx_ny_v1','base_tf':'H1'}}


def empty_result():return {'setups':[],'orders':[],'observations':[],'execution_events':[],'story_events':[],'instrument':saved()['instrument'],'costs':jsonable(Costs()),'status':'PARTIAL_UNVALIDATED'}


def test_frozen_order_replays_to_real_paper_win_without_new_setups(monkeypatch):
    from bishop.v2 import engine
    monkeypatch.setattr(B,'feed_from_store',lambda *a:feed())
    monkeypatch.setattr(engine,'run',lambda *a,**kw:empty_result())
    row=B.compute({'pair':'EURUSD','now':(T+timedelta(hours=3)).isoformat(),'since':T.isoformat(),'existing':[saved()],'new_entries':False})['entries'][0]
    assert row['order']==saved()['order']
    assert row['observation']['outcome']=='WIN' and float(row['observation']['net_r'])==2
    view=B.public_entry(row)
    assert view['strategy']=='bishop' and view['paper_only'] and view['id'].startswith('bishop:')
    assert view['tp1'] is None and view['tp2']==1.002 and view['result_r']==2
    assert view['filled_at'] and view['closed_at']
    assert 'Bishop · PAPER' in B.message(row) and 'no broker order' in B.message(row)


def test_revised_execution_history_is_unknown_not_new_fill(monkeypatch):
    from bishop.v2 import engine
    original=feed();order=B.thaw_order(saved()['order'])
    row=saved();row['history_to']=(T+timedelta(hours=2)).isoformat();row['history_hash']=B.history_hash(original['bars'],order,T+timedelta(hours=2))
    changed=feed([(100100,100110,100090,100100),(100100,100110,100080,100100),(100100,100210,100090,100200)])
    monkeypatch.setattr(B,'feed_from_store',lambda *a:changed)
    monkeypatch.setattr(engine,'run',lambda *a,**kw:empty_result())
    new=B.compute({'pair':'EURUSD','now':(T+timedelta(hours=3)).isoformat(),'since':T.isoformat(),'existing':[row]})['entries'][0]
    assert B.display_status(new)=='UNKNOWN' and new['observation']['net_r'] is None
    assert new['history_hash']==row['history_hash']


def test_ambiguous_ohlc_remains_unknown(monkeypatch):
    from bishop.v2 import engine
    f=feed([(100100,100110,100090,100100),(100100,100210,99890,100050)])
    monkeypatch.setattr(B,'feed_from_store',lambda *a:f)
    monkeypatch.setattr(engine,'run',lambda *a,**kw:empty_result())
    row=B.compute({'pair':'EURUSD','now':(T+timedelta(hours=2)).isoformat(),'since':T.isoformat(),'existing':[saved()]})['entries'][0]
    assert B.display_status(row)=='UNKNOWN' and row['observation']['net_r'] is None


def test_source_change_rejected_and_missing_setup_never_cancels(monkeypatch):
    from bishop.v2 import engine
    monkeypatch.setattr(engine,'run',lambda *a,**kw:empty_result())
    f=feed([(100100,100110,100090,100100)])
    monkeypatch.setattr(B,'feed_from_store',lambda *a:f)
    result=B.compute({'pair':'EURUSD','now':(T+timedelta(hours=1)).isoformat(),'since':T.isoformat(),'existing':[saved()]})
    assert result['entries'][0]['observation']['outcome']=='OPEN'
    f['instrument']=Instrument(**{**saved()['instrument'],'source_id':'other'})
    with pytest.raises(ValueError,match='metadata changed'):B.compute({'pair':'EURUSD','now':(T+timedelta(hours=1)).isoformat(),'since':T.isoformat(),'existing':[saved()]})


def test_primary_closed_store_no_fallback_or_subhour(monkeypatch,tmp_path):
    from slk import store,instruments
    monkeypatch.setattr(store,'DIR',str(tmp_path))
    p=store.Pair('EURUSD',source='ctrader');p.sym={'digits':5,'pip_position':4}
    rows=[]
    for i in range(21*24):
        at=T+timedelta(hours=i)
        from bishop.v2.aggregation import is_open
        if is_open(at,'fx_ny_v1'):rows.append((int(at.timestamp()),1.1,1.1001,1.0999,1.1))
    p.put(rows,store.CUR);p.save()
    # Forming H1 must be excluded; source is primary cTrader only.
    now=T+timedelta(hours=21*24-1,minutes=30)
    f=B.feed_from_store('EURUSD',now.isoformat())
    assert all(b.end<=now for b in f['bars']) and {b.tf for b in f['bars']}=={'H1'}
    assert f['instrument'].source_id=='ctrader:EURUSD' and B.ENTRY_TFS==('H4','H3','H2','H1')
    p.src='dukascopy';p.changed=True;p.save()
    with pytest.raises(ValueError,match='primary'):B.feed_from_store('EURUSD',now.isoformat())


def test_real_engine_smoke_uses_bishop_confirmation_profile(monkeypatch):
    import random
    from bishop.v2.types import StrategyPolicy
    inst=Instrument('DVR75','0.01','0.01','24x7_utc_v1','utc_epoch_v1','MID','deriv:DVR75','Deriv')
    rng=random.Random(41);price=10000;bars=[]
    for i in range(240):
        close=price+rng.choice((-12,-8,4,12))
        bars.append(Bar('DVR75','H1',T+timedelta(hours=i),T+timedelta(hours=i+1),price,max(price,close)+3,min(price,close)-3,close,source_id=inst.source_id));price=close
    f={'instrument':inst,'bars':bars,'manifest':{'calendar':'24x7_utc_v1','base_tf':'H1'}}
    monkeypatch.setattr(B,'feed_from_store',lambda *a:f)
    result=B.compute({'pair':'DVR75','now':bars[-1].end.isoformat(),'since':bars[-24].start.isoformat(),'existing':[]})
    policy=StrategyPolicy(source_profile='bishop_confirmation',entry_tfs=B.ENTRY_TFS)
    assert 'H1/H2/H3/H4 only' in result['note']
    assert all(row['policy_id']==policy.id and row['order']['model'] not in ('direct_h4','direct_h2','aggressive_kl_imbalance') for row in result['entries'])


def test_mysql_owned_immutable_entries_delivery_and_retention(monkeypatch):
    if not os.environ.get('SLK_TEST_MYSQL'):pytest.skip('requires disposable MySQL8')
    from slk import db
    monkeypatch.setenv('DATABASE_URL',os.environ['SLK_TEST_MYSQL'])
    class Adapter:
        connect=staticmethod(db.connect)
        @staticmethod
        def query(sql,args=()):
            with db.connect() as c:
                with c.cursor() as cur:cur.execute(sql,args);return list(cur.fetchall())
        @staticmethod
        def execute(sql,args=()):
            with db.connect() as c:
                with c.cursor() as cur:return cur.execute(sql,args)
    repo=B.Repository(Adapter);repo.apply_schema();uid=int(time.time())+12345;stamp=int(time.time())
    try:
        row=saved();repo.persist(uid,'EURUSD',[row],stamp)
        repo.persist(uid,'EURUSD',[row],stamp)
        assert len(repo.rows(uid))==1 and repo.rows(uid+1)==[]
        altered=copy.deepcopy(row);altered['order']['entry_ticks']+=1
        with pytest.raises(ValueError,match='geometry'):repo.persist(uid,'EURUSD',[altered],stamp+1)
        assert repo.rows(uid)[0]['order']['entry_ticks']==100000
        sent=[]
        repo.deliver(uid+1,lambda *a,**kw:pytest.fail('cross-user delivery'),stamp)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:repo.deliver(uid,lambda text,chat:sent.append((text,chat)) or True,stamp),range(2)))
        assert len(sent)==1 and sent[0][1]==uid and 'Bishop' in sent[0][0]
        closed=copy.deepcopy(row);closed['observation'].update(outcome='WIN',status='CLOSED',net_r='2')
        repo.persist(uid,'EURUSD',[closed],stamp+2)
        repo.persist(uid,'EURUSD',[row],stamp+3)
        assert repo.rows(uid)[0]['observation']['outcome']=='WIN'
    finally:
        for table in ('bishop_app_entries','bishop_app_state','bishop_app_outbox'):Adapter.execute('DELETE FROM '+table+' WHERE user_id=%s',(uid,))


def test_mid_quotes_only_allow_explicit_zero_costs():
    from bishop.v2.simulation import simulate
    inst=Instrument('DVX','1','1','24x7_utc_v1','utc_epoch_v1','MID','deriv:DVX')
    assert simulate((),(),inst,Costs(),T)['observations']==[]
    with pytest.raises(ValueError,match='MID'):simulate((),(),inst,Costs(spread_ticks=1),T)


def test_scan_activation_selected_only_disabled_tracking_and_weekend(monkeypatch):
    from slk import db,tenancy
    monkeypatch.setenv('TELEGRAM_CHAT_ID','999')
    monkeypatch.delenv('GITHUB_EVENT_NAME',raising=False)
    values={'pairs':'EURUSD','alert_entry':'off','bishop_paper_entries':'on'}
    events=[];active=[];states=[];updates=[]
    monkeypatch.setattr(db,'get_settings',lambda:values)
    monkeypatch.setattr(db,'get_setting',lambda *a:'999')
    monkeypatch.setattr(db,'set_setting',lambda *a:None)
    monkeypatch.setattr(db,'query',lambda sql,args=None:[{'user_id':111}] if 'app_users' in sql else [{'pair':p} for p in active])
    monkeypatch.setattr(db,'execute',lambda *a:updates.append(a))
    class Repo:
        def __init__(self,db):pass
        def apply_schema(self):pass
        def states(self,uid):events.append(('states',uid));return states
        def activate(self,uid,pair,stamp):events.append(('activate',uid,pair))
        def rows(self,uid,pair=None,active=False):return [saved()]
        def note(self,uid,pair,stamp,note):events.append(('note',uid,pair,note))
        def persist(self,uid,pair,rows,stamp,alerts=True):events.append(('persist',uid,pair))
        def deliver(self,*a):pytest.fail('alerts disabled')
    monkeypatch.setattr(B,'Repository',Repo)
    worker_calls=[]
    def worker(payload):worker_calls.append(payload);return {'entries':[],'note':'computed'}
    B.scan(now=T,worker=worker)
    assert not worker_calls
    assert [e[1] for e in events if e[0]=='states']==[111,999] # fair rotation, owner numerically largest
    assert {e[2] for e in events if e[0]=='activate'}=={'EURUSD'}
    states.append({'pair':'EURUSD','activated_at':int(T.timestamp())-3600,'checked_at':0})
    active.append('EURUSD');values['bishop_paper_entries']='off'
    B.scan(now=T+timedelta(hours=1),worker=worker)
    assert worker_calls and all(p['new_entries'] is False and p['pair']=='EURUSD' for p in worker_calls)
    updates.clear();monkeypatch.setenv('GITHUB_EVENT_NAME','schedule')
    B.scan(now=datetime(2026,11,7,tzinfo=timezone.utc),worker=worker)
    assert not any('SUSPENDED' in str(args) for sql,args in updates)
    monkeypatch.delenv('GITHUB_EVENT_NAME',raising=False)
    active.append('USDJPY');updates.clear()
    B.scan(now=T+timedelta(hours=2),worker=worker)
    assert any('SUSPENDED' in str(args) for sql,args in updates)

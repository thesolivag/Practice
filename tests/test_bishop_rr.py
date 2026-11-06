import copy,json,os,time
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import pytest
from bishop.v2.types import Bar,Instrument,Order,Clock,jsonable
from bishop.v2.simulation import Costs
from slk import bishop_rr as R
T=datetime(2026,11,2,tzinfo=timezone.utc)
I=Instrument('X','1','1','24x7_utc_v1','utc_epoch_v1','BID','test','test')

def bar(i,o,h,l,c):return Bar('X','H1',T+timedelta(hours=i),T+timedelta(hours=i+1),o,h,l,c,source_id='test')

def setup(bars,side='BUY'):
    return {'instrument':'X','tf':'H1','side':side,'model':'confirmation_bo','entry_ticks':100,
      'clock':{'available_at':bars[-1].end.isoformat()},'details':{'study_pattern_bar_ids':[bars[-2].id,bars[-1].id],
      'protected_objects':[[bars[0].id,50,'pattern_wick'],['near',93 if side=='BUY' else 107,'nearby_structure_or_liquidity_OUR_CHOICE']]}}

def test_current_episode_excludes_old_low_retains_nearby_and_future_invariant():
    bs=[bar(0,80,90,50,85),bar(1,98,102,94,99),bar(2,99,104,96,103)]
    s=setup(bs);proof=R.logical_stop(s,bs,I,Decimal('1'))
    assert proof['stop_ticks']==92 and proof['boundary_ticks']==93
    assert bs[0].id not in proof['bar_ids']
    assert R.logical_stop(s,bs+[bar(3,103,120,20,110)],I,Decimal('1'))==proof
    sell=R.logical_stop(setup(bs,'SELL'),bs,I,Decimal('1'));assert sell['stop_ticks']==108

def test_missing_episode_candle_with_identical_segment_is_unresolved():
    bs=[bar(0,98,102,94,99),bar(2,99,104,96,103)]
    assert R.logical_stop(setup(bs),bs,I)['status']=='UNRESOLVED'

def test_missing_anchor_or_unmapped_range_cannot_invent_stop():
    bs=[bar(0,98,102,94,99),bar(1,99,104,96,103)];s=setup(bs)
    s['details']['study_pattern_bar_ids']=['missing']
    assert R.logical_stop(s,bs,I)['status']=='UNRESOLVED'
    s=setup(bs);s['details']['protected_objects'].append(['range',80,'active_range_protected_wick'])
    assert R.logical_stop(s,bs,I)['status']=='UNRESOLVED'

def study():
    o=Order(id='baseline',setup_id='setup',instrument='X',tf='H1',model='confirmation_bo',side='BUY',kind='LIMIT',clock=Clock(T,T,T),entry_ticks=100,stop_ticks=90,target_ticks=102,expires_at=T+timedelta(days=1))
    return {'id':'study','source_order_id':o.id,'version':R.VERSION,'pair':'X','tf':'H1','side':'BUY','model':o.model,'created_at':T.isoformat(),
      'source_order':jsonable(o),'source_baseline_observation':{'outcome':'OPEN'},'instrument':jsonable(I),'calendar':'24x7_utc_v1','costs':jsonable(Costs()),
      'stop_proof':{'status':'READY','stop_ticks':95},'status':'READY','variants':{}}

def test_three_independent_exits_one_win_two_losses_and_original_unchanged():
    bs=[bar(0,100,101,99,100),bar(1,100,106,100,105),bar(2,104,104,94,95)]
    s=study();original=copy.deepcopy(s);f={'bars':bs,'instrument':I}
    early=R.evaluate(s,{'bars':bs[:2],'instrument':I},bs[1].end.isoformat())
    assert early['variants']['1']['observation']['outcome']=='WIN'
    assert early['variants']['2']['observation']['outcome']=='OPEN'
    later=R.evaluate(early,f,bs[-1].end.isoformat())
    assert [later['variants'][k]['observation']['outcome'] for k in ('1','2','3')]==['WIN','LOSS','LOSS']
    assert s==original and later['source_order']==original['source_order']
    stats=R.summary([later]);assert stats['paired_closed']==1
    assert [stats['variants'][k]['total_r'] for k in ('1','2','3')]==[1,-1,-1]

def test_ambiguous_bar_is_unknown_and_not_a_win():
    b=bar(0,100,120,90,100);r=R.evaluate(study(),{'bars':[b],'instrument':I},b.end.isoformat())
    assert all(v['observation']['outcome']=='CENSORED' for v in r['variants'].values())
    stats=R.summary([r]);assert stats['paired_closed']==0
    assert all(v['unknown']==1 and v['closed']==0 and v['total_r']==0 for v in stats['variants'].values())

def test_revised_history_cannot_rewrite_outcome():
    bs=[bar(0,100,101,99,100)];r=R.evaluate(study(),{'bars':bs,'instrument':I},bs[0].end.isoformat())
    revised=[bar(0,100,101,98,100)];new=R.evaluate(r,{'bars':revised,'instrument':I},bs[0].end.isoformat())
    assert new['status']=='UNKNOWN' and R.summary([new])['variants']['1']['unknown']==1

def test_mysql_study_user_isolation_and_stale_write(monkeypatch):
    if not os.environ.get('SLK_TEST_MYSQL'):pytest.skip('requires disposable MySQL')
    from slk import db
    monkeypatch.setenv('DATABASE_URL',os.environ['SLK_TEST_MYSQL'])
    class DB:
        connect=staticmethod(db.connect)
        @staticmethod
        def execute(sql,args=()):
            with db.connect() as c:
                with c.cursor() as cur:return cur.execute(sql,args)
        @staticmethod
        def query(sql,args=()):
            with db.connect() as c:
                with c.cursor() as cur:cur.execute(sql,args);return list(cur.fetchall())
    repo=R.Repository(DB);repo.apply_schema();uid=int(time.time())+67899
    try:
        s=study();repo.persist(uid,[s],20);assert repo.rows(uid+1,'X')==[]
        stale={**s,'status':'STALE'};repo.persist(uid,[stale],10)
        assert repo.rows(uid,'X')[0]['status']=='READY'
        stats,latest=R.report(DB,uid);assert stats['cohort']==1 and len(latest)==1
        assert R.report(DB,uid+1)[0]['cohort']==0
        changed=copy.deepcopy(s);changed['stop_proof']['stop_ticks']=96
        with pytest.raises(ValueError,match='Frozen'):repo.persist(uid,[changed],21)
        assert repo.rows(uid,'X')[0]['stop_proof']['stop_ticks']==95
    finally:DB.execute('DELETE FROM bishop_rr_studies WHERE user_id=%s',(uid,))

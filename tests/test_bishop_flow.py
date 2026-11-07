from datetime import datetime,timedelta,timezone
from dataclasses import replace
from unittest.mock import patch
from bishop.v2.types import Bar,Level,Event,Clock,StrategyPolicy,Liquidity,Instrument
from bishop.v2.structure import StructureResult
from slk import bishop_flow as F
T=datetime(2026,11,2,tzinfo=timezone.utc)
def at(h):return T+timedelta(hours=h)
def bar(h,tf='H1',o=102,hi=105,lo=101,c=103):
 return Bar('X',tf,at(h),at(h+int(tf[1:])),o,hi,lo,c,source_id='test')
def fixture():
 b=bar(0,'H4',98,105,97,104)
 broken=Level(id='A',instrument='X',tf='H4',kind='A',price_ticks=100,side='SELL',formed_at=at(-8),available_at=at(-4))
 kl=Level(id='KL',instrument='X',tf='H4',kind='V',price_ticks=100,side='BUY',formed_at=at(-8),available_at=at(-4))
 e=Event(id='break',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(at(4),at(4),at(4)),side='BUY',reference_id='A',price_ticks=100,bar_ids=(b.id,))
 flip=Event(id='flip',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='H4',clock=e.clock,side='BUY',reference_id='A')
 h4=StructureResult((),(broken,kl),(),(e,flip),())
 poolbar=bar(12,'H4',103,105,102,104)
 pool=Liquidity(id='pool',instrument='X',tf='H4',kind='LOW',price_ticks=102,formed_at=at(16),available_at=at(16),form='BAR',bar_ids=(poolbar.id,),details={'parent_break_id':'break','reaction_level_id':'KL','breakout_id':'break'})
 bs=[bar(16,lo=101),bar(17,lo=99,c=102),bar(18,c=104)]
 frames={'H4':[b,bar(4,'H4'),bar(8,'H4'),poolbar],'H1':bs}
 bias=[{'id':1,'pair':'X','side':'BUY','confirmed_at':at(0).isoformat()}]
 return frames,h4,pool,bias

def run(h=19,mutate=None,setups=()):
 frames,h4,pool,bias=fixture()
 if mutate:frames,h4,pool,bias=mutate(frames,h4,pool,bias)
 def pools(bars,levels,events,*args):return (pool,) if pool.available_at<=at(h) else ()
 with patch('bishop.v2.liquidity_forms.later_kl_irl',side_effect=pools):
  return F.recognize(frames,h4,bias,StrategyPolicy(research_later_kl_irl=True),at(h),at(0),setups,'24x7_utc_v1',Instrument('X','1','1','24x7_utc_v1','utc_epoch_v1','BID','test','test'))

def h1(result):return next(r for r in result['flows'] if r['tf']=='H1')

def test_candidates_exist_before_sweep_and_delayed_stages_are_causal():
 assert run(15)['flows'][0]['status']=='WAIT_LIQUIDITY'
 assert h1(run(16))['status']=='WAIT_TAKE'
 assert h1(run(17))['status']=='WAIT_REACTION'
 assert h1(run(18))['status']=='WAIT_CONFIRMATION'
 assert h1(run(19))['timeline'][:3]==h1(run(16))['timeline']

def test_unfinished_or_wick_only_break_cannot_admit_pool():
 def bad(fr,st,p,b):
  old=fr['H4'][0];new=replace(old,close_ticks=99);fr['H4'][0]=new
  st=replace(st,events=(replace(st.events[0],bar_ids=(new.id,)),st.events[1]));return fr,st,p,b
 r=run(mutate=bad);assert not r['flows'];assert 'CLOSE_NOT_BEYOND' in r['rejected_breaks'][0]['reason']
 def unfinished(fr,st,p,b):fr['H4'][0]=replace(fr['H4'][0],complete=False);return fr,st,p,b
 assert not run(mutate=unfinished)['flows']

def test_conflicting_bias_blocks_and_future_bias_cannot_backdate():
 def conflict(fr,st,p,b):return fr,st,p,b+[dict(b[0],id=2,side='SELL')]
 assert not run(mutate=conflict)['flows']
 def late(fr,st,p,b):return fr,st,p,[dict(b[0],confirmed_at=at(5).isoformat())]
 assert not run(mutate=late)['flows']

def test_gap_and_level_role_loss_invalidate_before_confirmation():
 def gap(fr,st,p,b):fr['H1']=fr['H1'][1:];return fr,st,p,b
 assert h1(run(mutate=gap))['reason']=='DATA_GAP'
 def lost(fr,st,p,b):return fr,replace(st,events=st.events+(Event(id='lost',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='H4',clock=Clock(at(17),at(17),at(17)),side='SELL',reference_id='KL'),)),p,b
 assert h1(run(mutate=lost))['status']=='INVALIDATED'

def test_confirmation_needs_exact_pool_parent_reaction_and_closed_clock():
 frames,st,pool,bias=fixture();reaction=frames['H1'][1];confirmation=frames['H1'][2]
 s={'id':'setup','instrument':'X','tf':'H1','side':'BUY','model':'confirmation_bo','status':'ELIGIBLE','clock':{'available_at':at(19).isoformat()},'entry_ticks':103,'target_ticks':110,'liquidity_ids':['pool'],'evidence_ids':['break','KL',reaction.id],'details':{'study_pattern_bar_ids':[reaction.id,confirmation.id]}}
 assert h1(run(18,setups=[s]))['plans']==[]
 r=h1(run(19,setups=[s]));assert r['status']=='CONFIRMED_PLAN' and set(r['plans'][0]['targets'])=={'1','2','3'}
 assert h1(run(19,setups=[dict(s,liquidity_ids=['other'])]))['plans']==[]

def test_merge_keeps_old_evidence_on_revision_and_completed_plan():
 a=run(17);b=run(19);assert F.merge(a,b)['flows']
 b['flows'][0]['timeline'][0]['evidence_id']='changed'
 assert h1(F.merge(a,b))['status']=='EVIDENCE_CHANGED'
 old=run(19);old['flows'][0]['plans']=[{'frozen':True}]
 assert h1(F.merge(old,run(19)))['plans']==[{'frozen':True}]


def test_sell_is_mirrored_and_future_appended_candles_do_not_change_prefix():
 def mirror(fr,st,p,bias):
  mapping={}
  for tf,bs in fr.items():
   out=[]
   for b in bs:
    z=replace(b,open_ticks=200-b.open_ticks,high_ticks=200-b.low_ticks,low_ticks=200-b.high_ticks,close_ticks=200-b.close_ticks)
    mapping[b.id]=z.id;out.append(z)
   fr[tf]=out
  levels=tuple(replace(l,kind={'A':'V','V':'A'}.get(l.kind,l.kind),price_ticks=200-l.price_ticks,side='BUY' if l.side=='SELL' else 'SELL') for l in st.levels)
  events=tuple(replace(e,side='SELL',price_ticks=200-e.price_ticks if e.price_ticks is not None else None,bar_ids=tuple(mapping.get(i,i) for i in e.bar_ids)) for e in st.events)
  p=replace(p,kind='HIGH',price_ticks=200-p.price_ticks,bar_ids=tuple(mapping.get(i,i) for i in p.bar_ids))
  return fr,replace(st,levels=levels,events=events),p,[dict(bias[0],side='SELL')]
 assert h1(run(mutate=mirror))['status']=='WAIT_CONFIRMATION'
 def future(fr,st,p,bias):fr['H1'].append(bar(99,lo=1,c=2));return fr,st,p,bias
 assert run(17,mutate=future)==run(17)


def test_mysql_recognition_table_isolates_users(monkeypatch):
 import os,time,pytest,json
 if not os.environ.get('SLK_TEST_MYSQL'):pytest.skip('requires disposable MySQL')
 from slk import db
 monkeypatch.setenv('DATABASE_URL',os.environ['SLK_TEST_MYSQL'])
 uid=int(time.time())+98765
 with db.connect() as conn:
  with conn.cursor() as cur:
   cur.execute(F.SCHEMA)
   try:
    cur.execute('INSERT INTO bishop_flow_state(user_id,pair,activated_at,payload) VALUES(%s,%s,%s,%s)',(uid,'TEST',1,json.dumps(run(19))))
    cur.execute('SELECT payload FROM bishop_flow_state WHERE user_id=%s',(uid+1,));assert not cur.fetchall()
    cur.execute('SELECT payload FROM bishop_flow_state WHERE user_id=%s',(uid,));assert json.loads(cur.fetchone()['payload'])['flows']
   finally:cur.execute('DELETE FROM bishop_flow_state WHERE user_id=%s',(uid,))


def test_timeframe_local_segment_counters_do_not_invalidate_contiguous_evidence():
 def different_segments(fr,st,p,b):
  fr['H1']=[replace(c,segment_id='9') for c in fr['H1']]
  return fr,st,p,b
 assert h1(run(mutate=different_segments))['status']=='WAIT_CONFIRMATION'

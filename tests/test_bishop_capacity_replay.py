from datetime import datetime,timedelta,timezone
from dataclasses import replace
from types import SimpleNamespace
import pytest
from bishop.v2.types import Bar,Instrument,Setup,Order,Clock,StrategyPolicy,jsonable
from slk import bishop_capacity_replay as Y
T=datetime(2026,1,2,tzinfo=timezone.utc)
I=Instrument('X','1','1','24x7_utc_v1','utc_epoch_v1','BID','test','test')
def bar(h,o=100,hi=102,lo=98,c=100):return Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),o,hi,lo,c,source_id='test')
def setup(ident='s',stop=95,target=110):
 return Setup(id=ident,instrument='X',tf='H1',model='confirmation_bo',side='BUY',story_id='story',clock=Clock(T,T,T),entry_ticks=100,stop_ticks=stop,target_ticks=target,risk_profile='test',level_id='level')
def order():
 return Order(id='order',setup_id='s',instrument='X',tf='H1',model='confirmation_bo',side='BUY',kind='MARKET',clock=Clock(T,T,T),entry_ticks=100,stop_ticks=95,target_ticks=110,details={'story_id':'story'})


def test_detector_gets_physical_prefix_and_current_clock_only(monkeypatch):
 import bishop.v2.engine as E
 seen=[]
 def engine(feed,**kw):
  seen.append(feed)
  assert kw['as_of']==T+timedelta(hours=1) and kw['scan_start']==kw['as_of']
  assert all(b.available_at<=kw['as_of'] for b in feed['bars'])
  return {'safe':True}
 monkeypatch.setattr(E,'run',engine)
 feed={'instrument':I,'bars':(bar(0),bar(1,o=100000,hi=200000,lo=1,c=150000)),'manifest':{}}
 a,_=Y.detect(feed,T+timedelta(hours=1))
 b,_=Y.detect({**feed,'bars':feed['bars'][:1]},T+timedelta(hours=1))
 assert a==b and seen[0]['bars']==seen[1]['bars']


def test_unfinished_and_future_bars_are_excluded():
 feed={'bars':(bar(0),replace(bar(1),complete=False),bar(2))}
 assert Y.prefix(feed,T+timedelta(hours=2))['bars']==(bar(0),)


def test_selection_conflicts_are_not_resolved_by_future_wins():
 stories=[{'id':'story','details':{}}];policy=StrategyPolicy(entry_tfs=('H1',))
 orders,rejected=Y.select([setup(),setup('different',stop=94)],stories,policy,'standalone')
 assert not orders and rejected['AMBIGUOUS_PLAN_OR_LEVEL']==2
 orders,_=Y.select([setup(),setup('alias')],stories,policy,'standalone')
 assert len(orders)==1
 orders,rejected=Y.select([setup()],stories,policy,'standalone',active=10)
 assert not orders and rejected['EXPOSURE_CAP']==1


def test_frozen_order_cannot_use_confirmation_bar_or_future_execution():
 book={};o=order();Y.add_order(book,o,setup(),'standalone')
 # A huge move on the confirmation candle happened BEFORE submission.
 before=bar(-1,hi=200,lo=1)
 Y.advance(book,(before,),T,I,[],{})
 assert book[o.id]['observation']['status']=='PENDING'
 Y.advance(book,(before,bar(0,hi=105,lo=98)),T+timedelta(hours=1),I,[],{})
 assert book[o.id]['observation']['outcome']=='OPEN'
 frozen=book[o.id]['order']
 Y.advance(book,(before,bar(0,hi=105,lo=98),bar(1,hi=111,lo=98)),T+timedelta(hours=2),I,[],{})
 assert book[o.id]['observation']['outcome']=='WIN' and book[o.id]['order']==frozen


def test_same_bar_stop_and_target_remain_unknown():
 book={};o=order();Y.add_order(book,o,setup(),'standalone')
 Y.advance(book,(bar(0,hi=115,lo=90),),T+timedelta(hours=1),I,[],{})
 assert book[o.id]['observation']['outcome']=='CENSORED'
 s=Y.summarize(list(book.values()));assert s['resolved']==0 and s['total_R']==0


def test_late_discovered_cancellation_is_not_backdated():
 book={};o=replace(order(),kind='LIMIT');Y.add_order(book,o,setup(),'standalone')
 now=T+timedelta(hours=2)
 events={'standalone':[{'reference_id':'story','kind':'STORY_INVALIDATED','clock':{'available_at':T.isoformat()}}]}
 Y.advance(book,(bar(0,o=105,hi=107,lo=104,c=105),bar(1,o=105,hi=107,lo=104,c=105)),now,I,[],events)
 assert book[o.id]['actions'][0]['available_at']==now.isoformat()


def test_checkpoint_roundtrip_keeps_orders_and_feed_identity(tmp_path):
 state=Y.new_state();Y.add_order(state['book'],order(),setup(),'standalone');state['seen_flows'].add('seen')
 p=tmp_path/'state.json.gz';Y.dump(p,state);restored=Y.thaw_state(Y.load(p))
 assert restored['book']['order']['order']==order() and restored['seen_flows']=={'seen'}
 p=tmp_path/'feed.json.gz';Y.dump(p,{'instrument':I,'bars':[bar(0)],'manifest':{}})
 assert Y.feed_file(p)['bars']==(bar(0),)


def test_report_paired_exits_excludes_unresolved_member():
 state=Y.new_state()
 for rr in (1,2,3):
  o=replace(order(),id=f'o{rr}',target_ticks=100+5*rr)
  Y.add_order(state['book'],o,setup(),f'kk_aligned_{rr}R',source='source')
  state['book'][o.id]['observation']={'outcome':'WIN' if rr<3 else 'OPEN','net_r':str(rr) if rr<3 else None}
 result=Y.report(state,{'instrument':I},'TEST',T,T)
 assert result['paired']['kk_aligned']['all_exits_resolved']==0
 assert result['paired']['kk_aligned']['total_R']['1R']==0


def test_feed_lock_uses_nonblocking_retry_and_releases(monkeypatch):
 from contextlib import contextmanager
 from slk import jobs,bishop_year_jobs as J
 calls=[];released=[]
 @contextmanager
 def lock(db,wait):
  calls.append(wait)
  try:yield len(calls)>1
  finally:released.append(True)
 monkeypatch.setattr(jobs,'feed_lock',lock)
 monkeypatch.setattr(J.time,'sleep',lambda _:None)
 with J.research_feed_lock(None):assert calls==[0,0]
 assert len(released)==2


def test_monthly_snapshot_reuse_checks_hashes_and_keeps_cutoff(tmp_path,monkeypatch):
 import hashlib
 from slk import bishop_year_jobs as J
 path=tmp_path/'X.json.gz';Y.dump(path,{'frozen':True})
 meta={'commit':'original','end':'2026-11-07T11:00:00+00:00','pairs':['X'],'markets':{'X':{'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}}
 Y.dump(tmp_path/'manifest.json',meta)
 monkeypatch.setenv('GITHUB_SHA','runner');monkeypatch.setenv('GITHUB_OUTPUT',str(tmp_path/'output'))
 J.reuse_snapshot(tmp_path);m=Y.load(tmp_path/'manifest.json')
 assert m['source_snapshot_commit']=='original' and len(m['segment_ends'])==12
 assert m['segment_ends'][0]=='2026-02-01T00:00:00+00:00' and m['segment_ends'][-1]==meta['end']
 path.write_bytes(b'changed')
 with pytest.raises(ValueError,match='checksum'):J.reuse_snapshot(tmp_path)


def test_prior_passed_pilot_can_use_smaller_sections_but_failed_causal_audit_cannot(tmp_path):
 from slk import bishop_year_jobs as J
 p={'status':'PASS','physical_prefix_equal':True,'poisoned_future_equal':True,'hours':24,'seconds_per_hour':15}
 Y.dump(tmp_path/'pilot.json',p);J.reuse_pilot(tmp_path,tmp_path/'out')
 assert Y.load(tmp_path/'out/pilot.json')['estimated_31day_segment_minutes']==186
 p['poisoned_future_equal']=False;Y.dump(tmp_path/'pilot.json',p)
 with pytest.raises(ValueError,match='did not pass'):J.reuse_pilot(tmp_path,tmp_path/'out')


def test_comparison_uses_same_eligible_markets_and_marks_missing_warmup(tmp_path):
 from slk import bishop_year_jobs as J
 inputs=tmp_path/'inputs';results=tmp_path/'results';end=T+timedelta(hours=1)
 Y.dump(inputs/'manifest.json',{'commit':'test','start':T.isoformat(),'end':end.isoformat(),'pairs':['X','Y'],
  'markets':{p:{'status':'READY','kk_full_warmup':p=='X','missing_ytd_hours':0} for p in ['X','Y']}})
 Y.dump(inputs/'config.json',{'avoid_pairs':[]})
 for pair in ['X','Y']:
  Y.dump(inputs/(pair+'.json.gz'),{'instrument':replace(I,symbol=pair),'bars':[replace(bar(0),instrument=pair)],'manifest':{}})
  state=Y.new_state();state['audit']=[{'at':end.isoformat()}]
  Y.dump(results/f'year-1-{pair}'/'checkpoint.json.gz',state)
 J.collect(inputs,results,tmp_path/'out');r=Y.load(tmp_path/'out/REPORT.json')
 assert r['matched_comparison_markets']==['X']
 y=next(x for x in r['markets'] if x['pair']=='Y')
 assert y['models']['kk_aligned']['availability'].startswith('UNAVAILABLE')


def test_no_bias_skips_ineligible_research_detection_but_advances_existing_orders(monkeypatch):
 called=[]
 monkeypatch.setattr(Y,'historical_bias',lambda *args:[])
 def detect(feed,now,later=False):
  called.append(later)
  return {'diagnostics':{'structures':{}},'story_events':[],'setups':[],'stories':[],'input':{'prefix':'test'}},StrategyPolicy(entry_tfs=('H1',))
 monkeypatch.setattr(Y,'detect',detect)
 state=Y.new_state();Y.add_order(state['book'],order(),setup(),'standalone')
 f={'instrument':I,'bars':(bar(0,hi=111,lo=98),),'manifest':{}}
 Y.decision(f,None,T+timedelta(hours=1),T,{},state,{})
 assert called==[False] and state['book']['order']['observation']['outcome']=='WIN'

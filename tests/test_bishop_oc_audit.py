from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from copy import deepcopy
from bishop.v2.types import Bar
from slk.bishop_oc_audit import immediate_oc,freeze_reference,touches
from slk.bishop_entry_reference import metadata

START=datetime(2026,1,5,0,tzinfo=timezone.utc)
def bar(i,o,h,l,c):return Bar('TEST','H1',START+timedelta(hours=i),START+timedelta(hours=i+1),o,h,l,c,source_id='test')
def pattern():return [bar(0,110,112,104,105),bar(1,105,107,98,100),bar(2,100,111,99,110)]
def case():
    bars=pattern();now=bars[-1].end;ids=[b.id for b in bars[1:]]
    s={'id':'av','story_id':'story','level_id':'v','status':'ELIGIBLE','tf':'H1','side':'BUY','entry_ticks':100,'model':'engulf_av_retest','clock':{'available_at':now.isoformat()},'details':{'confirmation_protection_bar_ids':ids}}
    o={'id':'av-order','setup_id':'av','model':'engulf_av_retest','instrument':'TEST','entry_ticks':100,'tf':'H1','side':'BUY','clock':s['clock']}
    row={'setup':s,'order':o,'mode':'recognition_1R'}
    oc={**s,'id':'oc','level_id':'junction','entry_ticks':105,'stop_ticks':97,'target_ticks':113,'model':'oc_break_retest'}
    level={'id':'junction','kind':'OC','bar_ids':[b.id for b in bars[:2]],'available_at':bars[1].end.isoformat()}
    result={'setups':[s,oc],'diagnostics':{'structures':{'H1':{'levels':[level]}}}}
    return row,result,bars,SimpleNamespace(oc_gap_ticks=0)

def test_immediate_oc_closed_prefix_and_mirror():
    b=pattern();now=b[-1].end;ids=[x.id for x in b[1:]]
    assert immediate_oc(b,ids,'BUY',now)['price_ticks']==105
    assert immediate_oc(b+[bar(3,110,999,1,200)],ids,'BUY',now)==immediate_oc(b,ids,'BUY',now)
    assert immediate_oc(b,ids,'BUY',now-timedelta(seconds=1))['status']=='PATTERN_BARS_UNAVAILABLE'
    sell=[Bar(x.instrument,x.tf,x.start,x.end,300-x.open_ticks,300-x.low_ticks,300-x.high_ticks,300-x.close_ticks,source_id='test') for x in b]
    assert immediate_oc(sell,[x.id for x in sell[1:]],'SELL',now)['price_ticks']==195

def test_exact_junction_not_any_old_oc_or_different_story():
    row,result,bars,policy=case();now=bars[-1].end
    frozen=freeze_reference(row,result,bars,policy);assert frozen['status']=='ENGINE_ELIGIBLE_OC';assert frozen['junction']['price_ticks']==105
    result['diagnostics']['structures']['H1']['levels'][0]['bar_ids']=['older','unrelated']
    assert freeze_reference(row,result,bars,policy)['status']=='OC_NOT_ENGINE_ELIGIBLE'
    row,result,bars,policy=case();result['setups'][1]['story_id']='other'
    assert freeze_reference(row,result,bars,policy)['status']=='OC_NOT_ENGINE_ELIGIBLE'
    row,result,bars,policy=case();result['setups'][1]['clock']={'available_at':(now+timedelta(hours=1)).isoformat()}
    assert freeze_reference(row,result,bars,policy)['status']=='OC_NOT_ENGINE_ELIGIBLE'

def test_no_reproduction_no_eligibility_claim():
    row,result,bars,policy=case();result['setups']=result['setups'][1:]
    assert freeze_reference(row,result,bars,policy)['status']=='BASELINE_NOT_REPRODUCED'

def test_touch_not_profit_and_gaps_unknown():
    now=START+timedelta(hours=3);end=now+timedelta(hours=1)
    assert touches([bar(3,110,112,104,111)],now,end,105,100,'fx_ny_v1')['status']=='OC_ONLY_PRICE_TOUCH'
    assert touches([bar(3,110,112,99,111)],now,end,105,100,'fx_ny_v1')['status']=='BOTH_SAME_H1_ORDER_UNKNOWN'
    assert touches([],now,end,105,100,'fx_ny_v1')['status']=='INCOMPLETE_WINDOW'
    assert touches([bar(2,110,112,99,111)],now,end,105,100,'fx_ny_v1')['status']=='INCOMPLETE_WINDOW'

def test_recorded_alternatives_same_episode_no_future_or_outcomes():
    row,result,bars,policy=case();oc={'setup':result['setups'][1],'order':{**row['order'],'id':'oc-order','model':'oc_break_retest','entry_ticks':105},'mode':row['mode']}
    book={'av':row,'oc':oc};m=metadata(book,.01)['av-order'];assert {a['kind'] for a in m['alternatives']}=={'OC','AV'}
    assert m['confirmation']=='engulfing'
    future=deepcopy(oc);future['order']['clock']['available_at']='2026-02-01T00:00:00+00:00';future['order']['id']='future'
    m=metadata({'av':row,'future':future},.01)['av-order'];assert {a['kind'] for a in m['alternatives']}=={'AV'}
    assert 'result' not in str(m)


def test_one_tick_oc_gap_is_excluded_not_silently_tolerated():
    b=pattern();b[0]=bar(0,110,112,104,106)
    result=immediate_oc(b,[x.id for x in b[1:]],'BUY',b[-1].end)
    assert result['status']=='OC_JUNCTION_GAP'
    assert result['gap_ticks']==-1 and result['allowed_gap_ticks']==0
    assert result['price_ticks']==106

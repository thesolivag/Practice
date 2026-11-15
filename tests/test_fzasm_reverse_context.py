import json
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import pandas as pd
from fzasm.types import Candle
from fzasm.reverse_context import context_features,partition,summarize,candidates

T=datetime(2026,5,1,3,tzinfo=timezone.utc)

def test_context_ignores_future_and_does_not_need_outcomes():
    daily=[Candle(T-timedelta(days=5-i),100,110,90,105,timeframe='D1') for i in range(3)]
    h=[Candle(T-timedelta(hours=2),100,110,90,105,timeframe='H1'),Candle(T-timedelta(hours=1),105,112,95,100,timeframe='H1')]
    series={'D1':daily,'H1':h,'H2':[],'H4':[]}
    s=dict(timestamp=T.isoformat(),entry_price=105,stop_price=115,entry_evidence=json.dumps({'sweep_extreme':112}))
    a=context_features(s,series,.01)
    assert a['sweep_match_count']==1
    poisoned={tf:bars+[Candle(T+timedelta(days=1),100,999,1,800,timeframe=tf)] for tf,bars in series.items()}
    assert context_features(s,poisoned,.01)==a
    assert context_features(dict(s,result_r=99,status='WIN'),series,.01)==a


def test_ambiguous_sweep_does_not_guess_htf_touch():
    s=dict(timestamp=T.isoformat(),entry_price=105,stop_price=115,entry_evidence='{}')
    a=context_features(s,{'D1':[],'H1':[],'H2':[],'H4':[]},.01)
    assert a['htf_touch'] is None and not a['context_valid']


def test_split_and_discovery_exit_purge():
    assert partition('2026-06-25T03:00Z')=='discovery'
    assert partition('2026-06-30T03:00Z')=='embargo'
    assert partition('2026-07-06T03:00Z')=='validation'
    x=pd.DataFrame([dict(phase='discovery',status='CLOSED',result_r=3,exit_time='2026-07-02T00:00Z',signal_id='a',timestamp='2026-06-25T03:00Z')])
    r=summarize(x);assert r['resolved']==0 and r['boundary_excluded']==1 and r['net_r'] is None


def test_candidate_selection_never_uses_validation_profit():
    common=dict(symbol='EURUSD',entry_policy='h1_av',target='2R',feature='h4_touch',resolved=40,resolved_months=4)
    rows=[dict(common,phase='discovery',present=True,mean_net_r=.2),dict(common,phase='discovery',present=False,mean_net_r=-.1)]
    a=candidates(pd.DataFrame(rows));assert len(a)==1
    rows.append(dict(common,phase='validation',present=True,mean_net_r=-999))
    assert candidates(pd.DataFrame(rows))==a

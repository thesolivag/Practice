from dataclasses import replace
from datetime import timedelta
import pandas as pd
import pytest
from test_fzasm_repaired import setup,bar,AT
from fzasm.execution import TradeOutcome
from fzasm.study import variants,replay
from fzasm.types import BiasDirection

@pytest.mark.parametrize('short',[False,True])
def test_pending_fill_stop_target_collision_is_not_a_proven_loss(short):
 s=setup();c=bar(105,115,85,100)
 if short:
  s=replace(s,bias=BiasDirection.BEARISH,stop_loss=110,take_profit_1=90,take_profit_2=80)
  c=replace(c,open=95,high=115,low=85)
 t=TradeOutcome(s,0);t.evaluate_bar(c,0)
 assert t.status['r1_result_r']=='UNKNOWN'
 assert t.reasons['r1_result_r']=='ENTRY_STOP_TARGET_ORDER'


def test_same_signal_exact_and_three_pip_stops():
 s=setup();vs=list(variants(s))
 assert [v.stop_variant for v,_ in vs]==['sweep_exact','sweep_plus_3p']
 assert vs[0][0].stop_loss==90
 assert vs[1][0].stop_loss==pytest.approx(89.9997)
 assert all(v.entry_price==s.entry_price and v.timestamp==s.timestamp for v,_ in vs)
 invalid=replace(s,h1_sweep=replace(s.h1_sweep,sweep_price=100))
 assert list(variants(invalid))[0][1] is False


def test_frozen_asian_target_independent_of_fixed_r():
 t=TradeOutcome(setup(),0,asian_target=105,include_asian=True)
 t.evaluate_bar(bar(101,102,99,101),0)
 t.evaluate_bar(bar(101,106,100.5,105,AT+timedelta(minutes=1)),1)
 assert t.asian_result_r==.5 and t.r1_result_r is None
 assert TradeOutcome(setup(),0,asian_target=95,include_asian=True).status['asian_result_r']=='UNAVAILABLE'


def test_replay_preserves_month_crossing_and_freezes_session(tmp_path):
 idx=pd.date_range('2026-01-31', '2026-02-01 00:10',freq='min',tz='UTC')
 df=pd.DataFrame(dict(open=104.,high=105.,low=103.,close=104.),index=idx)
 signal=pd.Timestamp('2026-01-31T05:05:00Z')
 df.loc[signal:]=[101.,102.,100.5,101.]
 df.loc[signal]=[104.,105.,99.,101.]
 df.loc[pd.Timestamp('2026-02-01T00:05:00Z')]=[101.,111.,100.5,110.]
 s=replace(setup(),timestamp=signal)
 class Engine:
  def __init__(self,**kwargs):self.done=False
  def scan_asset(self,pair,slices,current_time):
   if current_time==signal and not self.done:
    self.done=True;return s
   return None
 trades=replay('EURUSD',df,tmp_path,policies=('h1_av',),engine_factory=Engine)
 assert len(trades)==2
 assert trades[0][1].r1_result_r==1
 assert trades[0][1].exit_times['r1_result_r'].month==2
 assert all(t.asian_target==105 for _,t in trades)
 rows=pd.read_csv(tmp_path/'monthly.csv')
 assert set(rows.loc[rows.setups>0,'month'])=={'2026-01'}
 # Later session extremes cannot change the frozen order target or stop.
 changed=df.copy();changed.loc[signal+timedelta(minutes=10),'high']=150
 again=replay('EURUSD',changed,tmp_path/'perturbed',policies=('h1_av',),engine_factory=Engine)
 assert [(t.asian_target,t.stop_loss) for _,t in again]==[(t.asian_target,t.stop_loss) for _,t in trades]
 # Buffer-only replay must reproduce the same buffered scenario, not widen twice.
 only=replay('EURUSD',df,tmp_path/'buffer_only',policies=('h1_av',),engine_factory=Engine,
             stop_variants=('sweep_plus_3p',))
 assert len(only)==1
 assert only[0][1].stop_loss==trades[1][1].stop_loss
 assert only[0][1].r1_result_r==trades[1][1].r1_result_r
 import json
 assert json.loads((tmp_path/'buffer_only/progress.json').read_text())['signals']==1
 assert json.loads((tmp_path/'buffer_only/manifest.json').read_text())['stops']==['sweep_plus_3p']

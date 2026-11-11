from dataclasses import replace
from datetime import timedelta
import json
import pandas as pd
import pytest
from test_fzasm_repaired import setup, bar, AT
from fzasm.entry import EntryModelEvaluator
from fzasm.execution import TradeOutcome
from fzasm.backtest import stop_study_setups, generate_report, backtest_pair
from fzasm.types import BiasDirection, KeyLevel, LevelType


def signal(short=False, poi=None):
    s=setup()
    values=[(102,104,101,103),(103,105,102,104),(104,105,101,102),(102,106,102,105),(106,109,106,108)]
    candles=[bar(*v,AT+timedelta(minutes=i*5),'M5') for i,v in enumerate(values)]
    if short:
        candles=[replace(c,open=200-c.open,high=200-c.low,low=200-c.high,close=200-c.close) for c in candles]
        sweep=replace(s.h1_sweep,direction=BiasDirection.BEARISH,sweep_price=110)
        daily=replace(s.daily_map,bias=BiasDirection.BEARISH,equilibrium_50=90,target_level=80)
    else:
        sweep,daily=s.h1_sweep,s.daily_map
    return EntryModelEvaluator.evaluate_entry('EURUSD',candles,sweep,daily,poi,require_shift=True)


@pytest.mark.parametrize('short',[False,True])
def test_two_stops_share_signal_but_have_independent_targets(short):
    s=signal(short)
    variants=list(stop_study_setups(s,'both'))
    assert len(variants)==2 and all(ok for _,ok in variants)
    a,b=[TradeOutcome(v,0) for v,_ in variants]
    assert a.setup.timestamp==b.setup.timestamp and a.entry_price==b.entry_price
    assert a.stop_loss==pytest.approx(110.0003 if short else 89.9997)
    assert b.stop_loss==pytest.approx(99.0003 if short else 100.9997)
    assert b.unit_risk<a.unit_risk and b.tp_2r!=a.tp_2r
    assert a.setup.entry_evidence['local_stop_origin']==(AT+timedelta(minutes=10)).isoformat()


def test_overlap_key_level_preferred_and_future_level_rejected():
    poi=KeyLevel(LevelType.OPEN_CLOSE,BiasDirection.BULLISH,105.5,105.25,AT,'H4')
    s=signal(poi=poi)
    assert s.entry_price==105.5 and s.entry_evidence['entry_rule']=='fvg_overlapping_key_level'
    assert signal(poi=replace(poi,timestamp=AT+timedelta(days=1))).entry_price==106
    assert signal(poi=replace(poi,mitigated=True)).entry_price==106


def test_no_shift_cannot_use_legacy_inducement_route():
    s=setup();poi=KeyLevel(LevelType.ORDER_BLOCK,s.bias,100,90,AT-timedelta(days=1),'H4')
    values=[(104,108,103,105),(105,108,102,104),(104,107,102,103),(103,105,101,102),(102,104,101.5,103)]
    candles=[bar(*v,AT+timedelta(minutes=i*5),'M5') for i,v in enumerate(values)]
    assert EntryModelEvaluator.evaluate_entry('EURUSD',candles,s.h1_sweep,s.daily_map,poi,require_shift=True) is None


def test_no_local_stop_does_not_invent_a_tighter_stop():
    s=replace(signal(),stop_candidates={'hourly_sweep':89.9997,'ltf_invalidation':None})
    variants=list(stop_study_setups(s,'both'))
    assert variants[0][1] and not variants[1][1]


def test_report_separates_counterfactuals_and_preserves_signal_ids(tmp_path):
    trades=[]
    for s,ok in stop_study_setups(signal(),'both'):
        t=TradeOutcome(s,0);t.end_of_data(s.timestamp);trades.append(t)
    report=generate_report({'EURUSD':trades},2025,str(tmp_path))
    rows=pd.read_csv(tmp_path/'fzasm_trades.csv')
    assert rows.signal_id.nunique()==1 and rows.stop_variant.nunique()==2
    assert 'Do not add scenario returns' in report
    for name in ('hourly_sweep','ltf_invalidation'):
        text=(tmp_path/name/'FZ_ASM_BACKTEST_REPORT.md').read_text()
        assert 'Monthly results' in text and '2025-01' in text
        assert 'Unavailable' in text
    assert json.loads(rows.entry_evidence.iloc[0])['structure_boundary']==106


def test_runner_emits_both_stops_and_causally_marks_missing_local(monkeypatch,tmp_path):
    import fzasm.backtest as bt
    idx=pd.date_range('2025-01-06',periods=360,freq='min',tz='UTC')
    df=pd.DataFrame({'open':107.,'high':108.,'low':106.5,'close':107.},index=idx)
    s=replace(signal(),stop_candidates={'hourly_sweep':89.9997,'ltf_invalidation':None})
    class Engine:
        confirmation_tf='M5'
        def scan_asset(self,pair,bars,current_time):
            if current_time==s.timestamp: return s
    monkeypatch.setattr(bt,'load_minute_df',lambda *a:df)
    trades=backtest_pair('EURUSD',2025,2025,Engine(),stop_mode='both')
    assert len(trades)==2
    assert all(v=='UNAVAILABLE' for v in trades[1].status.values())
    generate_report({'EURUSD':trades},2025,str(tmp_path))
    rows=pd.read_csv(tmp_path/'fzasm_trades.csv')
    missing=rows[rows.stop_variant=='ltf_invalidation'].iloc[0]
    assert pd.isna(missing.stop_loss) and pd.isna(missing.r1_result_r)


def test_same_future_bars_can_stop_local_while_hourly_remains_open():
    variants=[TradeOutcome(s,0) for s,ok in stop_study_setups(signal(),'both')]
    at=variants[0].setup.timestamp
    for t in variants:
        t.evaluate_bar(bar(107,108,105.8,107,at),0)
        t.evaluate_bar(bar(105,105.5,100,102,at+timedelta(minutes=1)),1)
    assert variants[0].status['r1_result_r']=='OPEN'
    assert variants[1].r1_result_r==-1

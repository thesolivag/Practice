"""Pinned audit sentinels for 31ba0d9, not a profitability backtest.

Strict xfails document expected correct behavior that the current implementation
violates. A fix must turn these into ordinary passing tests and update the audit.
"""
from datetime import datetime,timedelta,timezone
import pandas as pd
import pytest
from fzasm.types import Candle,TimeFrame,BiasDirection,TradeSetup,EntryModelType,DailyMapResult,MapType,HourlySweepResult,KeyLevel,LevelType
from fzasm.entry import EntryModelEvaluator
from fzasm.sessions import HourlySweepDetector
from fzasm.backtest import TradeOutcome,backtest_pair

AT=datetime(2025,1,6,1,tzinfo=timezone.utc)
def bar(o=100,h=110,l=95,c=105,hour=0):
    return Candle(AT+timedelta(hours=hour),o,h,l,c,TimeFrame.H1)
def setup():
    b=bar();bias=DailyMapResult(MapType.MAP_2_CANDLE_RANGE_CRT,BiasDirection.BULLISH,90,120,110,.85,'fixture',AT)
    sweep=HourlySweepResult(True,BiasDirection.BULLISH,b,b,95)
    return TradeSetup('EURUSD',AT,BiasDirection.BULLISH,EntryModelType.MODEL_A_CHOCH_RETEST,100,90,110,120,2,bias,sweep)

@pytest.mark.xfail(strict=True,reason='H4 full-period OHLC admitted by opening timestamp, including later H1 prices')
def test_future_h1_cannot_change_visible_h4(monkeypatch):
    import fzasm.backtest as bt
    index=pd.date_range('2025-01-01',periods=240,freq='h',tz='UTC')
    df=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.},index=index)
    df.loc[pd.Timestamp('2025-01-06T03:00:00Z'),'high']=999.
    monkeypatch.setattr(bt,'load_candles_df',lambda *a:df)
    class Spy:
        observed=None
        def scan_asset(self,**kw):
            if kw['current_time']==AT:self.observed=kw['candles_by_tf']['H4'][-1].high
    spy=Spy();backtest_pair('EURUSD',2025,2025,spy)
    assert spy.observed==101.

@pytest.mark.xfail(strict=True,reason='Missing M15 silently substitutes H1 fallback tagged as CHOCH_RETEST')
def test_no_m15_cannot_claim_lower_timeframe_confirmation():
    s=setup()
    assert EntryModelEvaluator.evaluate_entry(s.symbol,[],s.h1_sweep,s.daily_map) is None

@pytest.mark.xfail(strict=True,reason='No pending/fill state: targets can be awarded without a later entry-price touch')
def test_no_entry_fill_no_profit():
    t=TradeOutcome(setup(),0);t.evaluate_bar(bar(125,130,121,128,hour=1),1)
    assert t.r1_result_r is None

@pytest.mark.xfail(strict=True,reason='Initial TP2 branch bypasses 50% TP1 realization when both targets cross in one bar')
def test_two_targets_in_one_bar_must_weight_both_halves():
    t=TradeOutcome(setup(),0);t.evaluate_bar(bar(100,125,100,123,hour=1),1)
    assert t.fz_result_r==1.5  # 0.5*1R + 0.5*2R; both targets crossed, no stop touched.

@pytest.mark.xfail(strict=True,reason='After TP1, simultaneous BE and TP2 touch is awarded TP2 without order evidence')
def test_be_and_tp2_same_bar_cannot_be_proven_win():
    t=TradeOutcome(setup(),0);t.evaluate_bar(bar(100,111,100,110,hour=1),1)
    t.evaluate_bar(bar(110,125,99,110,hour=2),2)
    assert t.fz_result_r is None

@pytest.mark.xfail(strict=True,reason='Fixed-R timeout assigns zero instead of valuing an explicitly closed open position')
def test_timeout_is_not_automatically_break_even():
    t=TradeOutcome(setup(),0);t.evaluate_bar(bar(100,106,99,105,hour=1),1,max_bars=1)
    assert t.r2_result_r==.5

@pytest.mark.xfail(strict=True,reason='Dual sweep is accepted by candle colour despite opposite-boundary-standing description')
def test_dual_sweep_does_not_claim_high_standing():
    previous=bar(100,110,90,105);outside=bar(100,120,80,115,hour=1)
    result=HourlySweepDetector.detect_h1_sweep([previous,outside])
    assert result is None


def test_report_has_no_recorded_lower_timeframe_route():
    from pathlib import Path
    p=Path('reports/fzasm_trades.csv')
    if not p.exists():pytest.skip('Archived trade log not installed')
    rows=pd.read_csv(p)
    assert len(rows)==1389
    assert set(rows.entry_model)=={'MODEL_A_CHOCH_RETEST'}

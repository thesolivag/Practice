from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import pandas as pd
import pytest
from test_fzasm_repaired import setup, bar, AT
from fzasm.execution import TradeOutcome
from fzasm.asian_only import AsianOnlyEngine
from fzasm.data import df_to_candles
from fzasm.types import TimeFrame

@pytest.mark.parametrize('finish', ['gap', 'end'])
def test_observed_unfilled_through_expiry_is_not_unknown(finish):
    start = AT.replace(hour=5, minute=58)
    outcome = TradeOutcome(replace(setup(), timestamp=start), 0)
    for minute in range(2):
        outcome.evaluate_bar(bar(104,105,103,104,start+timedelta(minutes=minute)),minute)
    if finish == 'gap':
        outcome.evaluate_bar(bar(104,105,103,104,start.replace(hour=7,minute=0)),2)
    else:
        outcome.end_of_data(start.replace(hour=6,minute=0))
    assert set(outcome.status.values()) == {'UNFILLED'}
    assert set(outcome.exit_times.values()) == {start.replace(hour=6,minute=0)}

@pytest.mark.parametrize('filled', [False, True])
def test_gap_still_unknown_before_expiry_or_when_filled(filled):
    start = AT.replace(hour=5,minute=58)
    outcome = TradeOutcome(replace(setup(),timestamp=start),0)
    prices = (101,102,99,101) if filled else (104,105,103,104)
    outcome.evaluate_bar(bar(*prices,start),0)
    if filled:
        outcome.evaluate_bar(bar(101,102,99,101,start+timedelta(minutes=1)),1)
    outcome.evaluate_bar(bar(104,105,103,104,start.replace(hour=7,minute=0)),2)
    assert set(outcome.status.values()) == {'UNKNOWN'}
    assert set(outcome.reasons.values()) == {'DATA_GAP'}

def test_real_nzdjpy_dead_direct_context_no_longer_blocks_next_sweep():
    path=Path(__file__).parent/'fixtures'/'asm_nzdjpy_stale_h1.csv'
    frame=pd.read_csv(path,index_col=0,parse_dates=True)
    frame['close_time']=pd.to_datetime(frame['close_time'],utc=True)
    candles=df_to_candles(frame,TimeFrame('H1'))
    engine=AsianOnlyEngine(extra_pairs={'NZDJPY'},entry_policy='h1_av')
    for hour in (1,2,3):
        now=pd.Timestamp(f'2026-05-01 {hour:02}:00',tz='UTC')
        closed={'H1':[c for c in candles if c.available_at<=now]}
        result=engine.scan_asset('NZDJPY',closed,now)
    assert result is not None
    assert result.entry_price == pytest.approx(92.856)
    assert result.h1_sweep.sweep_candle.timestamp == pd.Timestamp('2026-05-01 02:00',tz='UTC')
    assert engine.scan_asset('NZDJPY',closed,now) is None
    assert engine.diagnostics['expired_h1_context'] == 1

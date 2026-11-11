from dataclasses import replace
from datetime import timedelta
from test_fzasm_repaired import setup, bar, AT
from fzasm.types import *
from fzasm.entry import EntryModelEvaluator
from fzasm.engine import FZASMEngine
import pytest


def case(short=False):
    a=bar(104,108,98,100,AT-timedelta(hours=1),'H1')
    b=bar(100,107,95,105,AT,'H1')
    daily=replace(setup().daily_map,equilibrium_50=110,target_level=120)
    if short:
        a,b=[replace(c,open=200-c.open,high=200-c.low,low=200-c.high,close=200-c.close) for c in (a,b)]
        daily=replace(daily,bias=BiasDirection.BEARISH,equilibrium_50=90,target_level=80)
    sweep=HourlySweepResult(True,daily.bias,b,a,b.low if not short else b.high)
    return [a,b],sweep,daily

@pytest.mark.parametrize('short',[False,True])
def test_direct_av_is_pending_at_body_vertex_not_wick(short):
    bars,sweep,daily=case(short)
    s=EntryModelEvaluator.evaluate_h1_av('EURUSD',bars,sweep,daily)
    assert s and s.entry_price==100 and s.timestamp==bars[-1].available_at
    assert s.entry_model==EntryModelType.H1_AV_RETEST and s.timeframe=='H1'
    assert s.stop_loss==pytest.approx(105.0003 if short else 94.9997)
    assert s.stop_candidates['ltf_invalidation'] is None


def test_rejects_gaps_missing_hours_future_map_and_wrong_direction():
    bars,sweep,daily=case()
    for changed in ([bars[0],replace(bars[1],open=101)], [replace(bars[0],timestamp=AT-timedelta(hours=2)),bars[1]]):
        assert EntryModelEvaluator.evaluate_h1_av('EURUSD',changed,sweep,daily) is None
    assert EntryModelEvaluator.evaluate_h1_av('EURUSD',bars,sweep,replace(daily,timestamp=AT+timedelta(days=1))) is None
    assert EntryModelEvaluator.evaluate_h1_av('EURUSD',bars,sweep,replace(daily,bias=BiasDirection.BEARISH)) is None


def test_engine_only_emits_once_after_hourly_close(monkeypatch):
    bars,sweep,daily=case(); e=FZASMEngine(entry_policy='h1_av')
    assert e.confirmation_tf=='H1'
    monkeypatch.setattr(e,'_build_context',lambda *args:(sweep,daily,None))
    assert e.scan_asset('EURUSD',{'H1':bars},AT+timedelta(minutes=59)) is None
    assert e.scan_asset('EURUSD',{'H1':bars},AT+timedelta(hours=1))
    assert e.scan_asset('EURUSD',{'H1':bars},AT+timedelta(hours=1)) is None


def test_h2_not_silently_used_as_direct_h1():
    bars,sweep,daily=case()
    sweep=replace(sweep,sweep_candle=replace(sweep.sweep_candle,timeframe='H2'))
    assert EntryModelEvaluator.evaluate_h1_av('EURUSD',bars,sweep,daily) is None

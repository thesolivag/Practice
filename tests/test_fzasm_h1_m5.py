from dataclasses import replace
import pandas as pd
import pytest
from test_fzasm_reference import reference
from fzasm.entry import EntryModelEvaluator
from fzasm.engine import FZASMEngine
from fzasm.types import DailyMapResult,MapType,BiasDirection


def fixture():
 h,m,s=reference();clock=h[2].available_at
 dm=DailyMapResult(MapType.MAP_1_STRUCTURAL_RANGE,s.direction,89.185,89.012,89.0985,.5,'entry fixture',clock)
 return h,m,s,clock,dm


def test_real_reference_uses_h1_vertex_after_m5_break():
 h,m,s,clock,dm=fixture();closed=[c for c in m if c.available_at<=clock]
 p=EntryModelEvaluator.evaluate_h1_av_m5('NZDJPY',h,closed,s,dm)
 assert p and p.entry_price==89.117 and p.timestamp==clock
 assert p.stop_loss==pytest.approx(89.215)
 assert p.entry_evidence['break_time']=='2026-11-11T02:55:00+00:00'
 assert p.stop_candidates['ltf_invalidation'] is None
 assert EntryModelEvaluator.evaluate_h1_av_m5('NZDJPY',h,closed[:-1],s,dm) is None
 assert EntryModelEvaluator.evaluate_h1_av_m5('NZDJPY',h,[c for c in m if c.available_at<=clock+pd.Timedelta(minutes=5)],s,dm) is None


def test_no_shift_no_order(monkeypatch):
 h,m,s,clock,dm=fixture()
 monkeypatch.setattr('fzasm.recognition.recognize_shift',lambda *args:None)
 assert EntryModelEvaluator.evaluate_h1_av_m5('NZDJPY',h,[c for c in m if c.available_at<=clock],s,dm) is None


def test_engine_filters_future_and_emits_once(monkeypatch):
 h,m,s,clock,dm=fixture();e=FZASMEngine(entry_policy='h1_av_m5',confirmation_tf='M15')
 assert e.confirmation_tf=='M5'
 monkeypatch.setattr(e,'_build_context',lambda *args:(s,dm,None))
 future=[replace(c,high=999,low=1,close=900) if c.available_at>clock else c for c in m]
 p=e.scan_asset('NZDJPY',{'H1':h,'M5':future},clock)
 assert p and p.entry_price==89.117
 assert e.scan_asset('NZDJPY',{'H1':h,'M5':future},clock) is None


def test_mirrored_buy_and_missing_m5():
 h,m,s,clock,dm=fixture()
 def flip(c):return replace(c,open=200-c.open,close=200-c.close,high=200-c.low,low=200-c.high)
 ss=replace(s,direction=BiasDirection.BULLISH,sweep_price=200-s.sweep_price,sweep_candle=flip(s.sweep_candle),swept_candle=flip(s.swept_candle))
 dd=replace(dm,bias=BiasDirection.BULLISH,equilibrium_50=200-dm.equilibrium_50,target_level=200-dm.target_level)
 bars=[flip(c) for c in m if c.available_at<=clock]
 p=EntryModelEvaluator.evaluate_h1_av_m5('NZDJPY',[flip(c) for c in h],bars,ss,dd)
 assert p and p.entry_price==pytest.approx(200-89.117)
 assert EntryModelEvaluator.evaluate_h1_av_m5('NZDJPY',[flip(c) for c in h],bars[:20]+bars[21:],ss,dd) is None

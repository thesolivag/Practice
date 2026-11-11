from pathlib import Path
from dataclasses import replace
import pandas as pd
import pytest
from fzasm.data import resample_ohlc,df_to_candles
from fzasm.types import *
from fzasm.sessions import HourlySweepDetector
from fzasm.recognition import recognize_retests
from fzasm.entry import EntryModelEvaluator


def reference():
 d=pd.read_csv(Path(__file__).parent/'data/nzdjpy_20261111_m1.csv',index_col='time',parse_dates=True)
 h=df_to_candles(resample_ohlc(d,'1h'),TimeFrame.H1)
 m=df_to_candles(resample_ohlc(d,'5min'),TimeFrame.M5)
 s=HourlySweepDetector.detect_h1_sweep(h[:3]);return h,m,s


def test_reference_sweep_and_standing_low():
 h,m,s=reference()
 assert s and s.direction==BiasDirection.BEARISH
 assert h[2].high==89.185 and h[1].high==89.132
 assert h[2].low>h[1].low


def test_intrahour_break_waits_for_h1_close_and_records_local_overlap():
 h,m,s=reference();clock=h[2].available_at
 assert recognize_retests(m,s,clock-pd.Timedelta(minutes=5))==[]
 events=recognize_retests(m,s,clock)
 ob=next(x for x in events if x['route']=='order_block')
 fvg=next(x for x in events if x['route']=='fvg_av_overlap')
 assert ob['break_time']=='2026-11-11T02:55:00+00:00'
 assert ob['formed_at']=='2026-11-11T03:00:00+00:00'
 assert ob['entry']==89.13 and fvg['entry']==89.12
 assert fvg['zone_low']<=fvg['entry']<=fvg['zone_high']
 assert fvg['origin_time']=='2026-11-11T01:30:00+00:00' # different origin from user marking; not a claimed match


def test_future_candle_perturbation_does_not_change_reference_plan():
 h,m,s=reference();clock=h[2].available_at
 expected=recognize_retests(m,s,clock)
 changed=[replace(c,high=999,low=1,close=900) if c.available_at>clock else c for c in m]
 assert recognize_retests(changed,s,clock)==expected


def test_mirrored_reference_and_missing_data_rejection():
 h,m,s=reference();clock=h[2].available_at
 def mirror(c):return replace(c,open=200-c.open,high=200-c.low,low=200-c.high,close=200-c.close)
 flipped=replace(s,direction=BiasDirection.BULLISH,sweep_candle=mirror(s.sweep_candle),swept_candle=mirror(s.swept_candle),sweep_price=200-s.sweep_price)
 got=recognize_retests([mirror(c) for c in m],flipped,clock)
 assert next(x for x in got if x['route']=='order_block')['entry']==pytest.approx(200-89.13)
 assert recognize_retests(m[:20]+m[21:],s,clock)==[]


def test_entry_routes_keep_hourly_stop_and_do_not_claim_targets_from_example():
 h,m,s=reference();clock=h[2].available_at
 # Deliberately supplied test map; this tests the entry module, not daily-map qualification.
 dm=DailyMapResult(MapType.MAP_1_STRUCTURAL_RANGE,s.direction,89.185,89.012,89.0985,.5,'entry module fixture',clock)
 closed=[c for c in m if c.available_at<=clock]
 for route,price in [('order_block',89.13),('fvg_av_overlap',89.12)]:
  plan=EntryModelEvaluator.evaluate_swing_retest('NZDJPY',closed,s,dm,route)
  assert plan and plan.entry_price==price
  assert plan.stop_loss==pytest.approx(89.215) # default three-pip buffer does not match screenshot 89.190

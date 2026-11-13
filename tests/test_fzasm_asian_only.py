from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from fzasm.asian_only import AsianOnlyEngine
from fzasm.types import Candle

def test_asian_context_ignores_daily_and_poi_and_allows_later_session_sweep():
 t=datetime(2026,11,11,3,tzinfo=timezone.utc)
 a=Candle(t,100,105,95,103,timeframe='H1')
 b=Candle(t+timedelta(hours=1),103,106,96,101,timeframe='H1')
 e=AsianOnlyEngine(extra_pairs={'NZDJPY'},entry_policy='h1_av')
 with patch('fzasm.engine.DailyMapEvaluator.evaluate',side_effect=AssertionError('Daily gate called')):
  sweep,context,poi=e._build_context('NZDJPY',{'H1':[a,b]},b.available_at)
 assert context.entry_only and poi is None
 assert context.bias==sweep.direction
 assert e._build_context('NZDJPY',{'H1':[a,b]},t.replace(hour=7)) is None

def test_entry_only_reference_and_future_candles_do_not_change_plan():
 import pandas as pd
 from fzasm.data import df_to_candles,resample_ohlc
 from fzasm.types import TimeFrame
 df=pd.read_csv('tests/data/nzdjpy_20261111_m1.csv',index_col=0,parse_dates=True)
 series={tf:df_to_candles(resample_ohlc(df,rule),TimeFrame(tf)) for tf,rule in {'H1':'1h','M5':'5min'}.items()}
 now=datetime(2026,11,11,3,tzinfo=timezone.utc)
 for policy in ['h1_av','h1_av_m5','swing_ob']:
  def run(data):return AsianOnlyEngine(extra_pairs={'NZDJPY'},entry_policy=policy).scan_asset('NZDJPY',data,now)
  a=run(series);b=run({tf:[c for c in bars if c.available_at<=now] for tf,bars in series.items()})
  assert a is not None and b is not None
  assert a.entry_price==b.entry_price
  assert a.daily_map.entry_only

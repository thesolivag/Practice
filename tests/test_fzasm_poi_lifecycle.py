from datetime import datetime,timedelta,timezone
from dataclasses import replace
import pytest
from fzasm.types import Candle,KeyLevel,LevelType,BiasDirection
from fzasm.poi_lifecycle import apply_lifecycle

@pytest.mark.parametrize('bullish',[True,False])
def test_closed_break_retires_zone_without_resurrection(bullish):
 t=datetime(2026,10,16,tzinfo=timezone.utc)
 c=Candle(t,100,110,99,109,timeframe='H4')
 z=KeyLevel(LevelType.OPEN_CLOSE,BiasDirection.BULLISH,109,100,t,'H4',source_candle=c)
 wick=Candle(t+timedelta(hours=4),103,108,95,100,timeframe='H4')
 br=Candle(t+timedelta(hours=8),100,102,98,99,timeframe='H4')
 recovery=Candle(t+timedelta(hours=12),101,110,100,109,timeframe='H4')
 if not bullish:
  def mirror(c):return replace(c,open=200-c.open,high=200-c.low,low=200-c.high,close=200-c.close)
  c,wick,br,recovery=map(mirror,[c,wick,br,recovery])
  z=replace(z,direction=BiasDirection.BEARISH,price_top=100,price_bottom=91,source_candle=c)
 assert not apply_lifecycle([z],[c,wick])[0].mitigated
 got=apply_lifecycle([z],[c,wick,br,recovery])[0]
 assert got.timestamp==c.available_at
 assert got.mitigated and got.metadata['invalidated_at']==br.available_at.isoformat()
 assert not z.mitigated # baseline object untouched

def test_real_nzdjpy_old_zone_was_broken():
 import pandas as pd
 from fzasm.data import resample_ohlc,df_to_candles
 from fzasm.types import TimeFrame
 # Reproduce the observed October 28 H4 close below 88.871.
 t=datetime(2026,10,28,tzinfo=timezone.utc)
 z=KeyLevel(LevelType.OPEN_CLOSE,BiasDirection.BULLISH,89.260,88.871,t-timedelta(days=12),'H4')
 c=Candle(t,89.736,89.752,88.142,88.688,timeframe='H4')
 got=apply_lifecycle([z],[c])[0]
 assert got.mitigated and got.metadata['invalidating_close']==88.688

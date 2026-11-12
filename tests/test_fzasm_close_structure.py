from dataclasses import replace
from datetime import datetime,timedelta,timezone
import pytest
from fzasm.types import Candle,HourlySweepResult,BiasDirection
from fzasm.recognition import recognize_shift

@pytest.mark.parametrize('bullish',[False,True])
def test_line_chart_level_and_close_break_not_wicks(bullish):
 at=datetime(2026,11,11,tzinfo=timezone.utc)
 bars=[Candle(at+timedelta(minutes=5*i),102,104,101,102,timeframe='M5') for i in range(24)]
 bars[13]=replace(bars[13],close=100,low=95)
 bars[14]=replace(bars[14],close=103)
 bars[15]=replace(bars[15],close=108,high=110)
 bars[16]=replace(bars[16],close=101,low=90) # wick crosses 100, close does not
 previous=Candle(at,102,109,89,102,timeframe='H1')
 sweepbar=Candle(at+timedelta(hours=1),102,110,90,102,timeframe='H1')
 s=HourlySweepResult(True,BiasDirection.BEARISH,sweepbar,previous,110)
 def mirror(c):return replace(c,open=200-c.open,close=200-c.close,high=200-c.low,low=200-c.high)
 if bullish:
  bars=[mirror(c) for c in bars]
  s=replace(s,direction=BiasDirection.BULLISH,sweep_candle=mirror(sweepbar),swept_candle=mirror(previous),sweep_price=90)
 clock=at+timedelta(hours=2)
 assert not recognize_shift(bars,s,clock)
 bars[16]=replace(bars[16],close=100) # touching the level is not a break
 assert not recognize_shift(bars,s,clock)
 bars[17]=replace(bars[17],close=101 if bullish else 99,high=105 if bullish else 104,low=96 if bullish else 98)
 result=recognize_shift(bars,s,clock)
 assert result['common']['structure_boundary']==100
 assert result['common']['break_time']==bars[17].available_at.isoformat()
 assert result['common']['break_basis']=='closed_candle_close'
 # A break known only from a still-open candle cannot be used.
 assert not recognize_shift(bars,s,bars[17].available_at-timedelta(seconds=1))

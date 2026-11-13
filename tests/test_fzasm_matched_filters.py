from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from contextlib import ExitStack
from fzasm.engine import FZASMEngine
from fzasm.types import Candle,KeyLevel,LevelType,BiasDirection


def context(daily,poi_direction=BiasDirection.BEARISH,hour=1):
 t=datetime(2026,11,11,hour,tzinfo=timezone.utc)
 bars=[Candle(t,100,105,95,103,timeframe='H1'),Candle(t+timedelta(hours=1),103,106,96,101,timeframe='H1')]
 poi=KeyLevel(LevelType.OPEN_CLOSE,poi_direction,104,100,t-timedelta(days=1),'H4')
 e=FZASMEngine(extra_pairs={'NZDJPY'},entry_policy='h1_av',daily_filter=daily,entry_only_targets=True)
 with ExitStack() as stack:
  for name,result in [('detect_order_blocks',[poi]),('detect_breaker_blocks',[]),('detect_open_close_levels',[])]:
   stack.enter_context(patch('fzasm.engine.KeyLevelDetector.'+name,return_value=result))
  evaluator=stack.enter_context(patch('fzasm.engine.DailyMapEvaluator.evaluate',return_value=None))
  result=e._build_context('NZDJPY',{'H1':bars,'H4':bars},bars[-1].available_at)
  if not daily:evaluator.assert_not_called()
 return result,e


def test_daily_off_preserves_other_gates():
 result,e=context(False)
 assert result is not None and result[1].entry_only
 result,e=context(True)
 assert result is None and e.diagnostics['no_daily_map']==1
 result,e=context(False,BiasDirection.BULLISH)
 assert result is None and e.diagnostics['poi_sweep_direction_mismatch']==1
 result,e=context(False,hour=3)
 assert result is None and e.diagnostics['outside_prime_sweep_hours']==1

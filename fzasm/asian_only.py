"""Research ablation: Asian H1 sweep and entry only; no daily/ITF gate."""
from .engine import FZASMEngine
from .sessions import HourlySweepDetector
from .types import DailyMapResult, MapType

class AsianOnlyEngine(FZASMEngine):
    def _build_context(self, symbol, candles_by_tf, current_time=None, force_session=False):
        if not self.session_mgr.is_supported_symbol(symbol):return None
        if not self.session_mgr.is_in_asian_session(current_time):return None
        sweep=HourlySweepDetector.detect_h1_sweep(candles_by_tf.get('H1',[]))
        if not sweep:return self._reject_context('no_hourly_sweep')
        # Full Asian session requested; no narrower inherited prime-hour gate.
        if not self.session_mgr.is_in_asian_session(sweep.sweep_candle.timestamp):
            return self._reject_context('sweep_outside_asian_session')
        self.diagnostics['qualified_context']+=1
        # Container only. These zero values are never traded as daily targets.
        context=DailyMapResult(MapType.MAP_1_STRUCTURAL_RANGE,sweep.direction,
            sweep.sweep_price,0.,0.,0.,'ENTRY_ONLY: no daily map or HTF POI',
            sweep.sweep_candle.available_at,entry_only=True)
        return sweep,context,None

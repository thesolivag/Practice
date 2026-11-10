"""
FZ-ASM Unified Strategy Engine.
Orchestrates top-down synchronization:
Daily Maps -> ITF Key Levels -> Asian Session Window -> H1 Sweep -> M15 Execution.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from datetime import datetime, timezone
from .types import (
    Candle,
    DailyMapResult,
    KeyLevel,
    HourlySweepResult,
    TradeSetup,
    SessionWindow,
    BiasDirection,
)
from .maps import DailyMapEvaluator
from .levels import KeyLevelDetector
from .sessions import AsianSessionManager, HourlySweepDetector
from .entry import EntryModelEvaluator


class FZASMEngine:
    """End-to-end evaluation engine for the FZ-ASM trading strategy."""

    def __init__(self, session_window: Optional[SessionWindow] = None, extra_pairs: Optional[Set[str]] = None):
        self.session_mgr = AsianSessionManager(session_window, extra_pairs=extra_pairs)

    def scan_asset(
        self,
        symbol: str,
        candles_by_tf: Dict[str, List[Candle]],
        current_time: Optional[datetime] = None,
        force_session: bool = False
    ) -> Optional[TradeSetup]:
        """
        Runs the full top-down FZ-ASM evaluation for a given symbol:
        1. Validates supported asset class (JPY crosses or Gold).
        2. Validates Asian Session window (unless force_session=True for backtests).
        3. Evaluates Daily candles for the active Daily Map (HTF Directional Bias).
        4. Detects ITF (H4/H2) Key Levels (Order Blocks, Breakers, Open/Close levels).
        5. Validates H1 (or H2) hourly candle sweep at the active Key Level.
        6. Evaluates M15 candles for Model A (CHOCH) or Model B (Inducement) execution.
        """
        # Step 1: Symbol validation
        if not self.session_mgr.is_supported_symbol(symbol):
            return None

        # Step 2: Session timing validation
        m15_candles = candles_by_tf.get("M15", [])
        h1_candles = candles_by_tf.get("H1", [])
        now = current_time or (
            m15_candles[-1].timestamp if m15_candles
            else (h1_candles[-1].timestamp if h1_candles else datetime.now(timezone.utc))
        )
        if not force_session and not self.session_mgr.is_in_asian_session(now):
            return None

        # Step 3: ITF Key Level Detection (H4 / H2)
        itf_tf = "H4" if "H4" in candles_by_tf else ("H2" if "H2" in candles_by_tf else None)
        itf_candles = candles_by_tf.get(itf_tf, []) if itf_tf else []
        itf_obs = KeyLevelDetector.detect_order_blocks(itf_candles, timeframe=itf_tf or "H4") if itf_candles else []
        itf_breakers = KeyLevelDetector.detect_breaker_blocks(itf_candles, itf_obs) if itf_candles else []
        itf_levels = KeyLevelDetector.detect_open_close_levels(itf_candles, timeframe=itf_tf or "H4") if itf_candles else []
        all_pois = itf_obs + itf_breakers + itf_levels

        # Pick the active POI currently tested by the sweeping candle
        active_poi = None
        if all_pois:
            latest_candle = h1_candles[-1] if h1_candles else (m15_candles[-1] if m15_candles else None)
            active_pois = [p for p in all_pois if not p.mitigated]
            if active_pois and latest_candle:
                tested = [p for p in active_pois if p.is_tested_by(latest_candle)]
                if tested:
                    active_poi = min(tested, key=lambda p: abs(p.mid_price - latest_candle.close))

        # A valid FZ-ASM setup strictly requires an active Key Level / POI interaction
        if not active_poi:
            return None

        # Step 4: HTF Daily Map Evaluation
        d1_candles = candles_by_tf.get("D1", [])
        daily_map = DailyMapEvaluator.evaluate(d1_candles, structural_poi=active_poi)
        if not daily_map or daily_map.bias == BiasDirection.NEUTRAL:
            return None

        # Step 5: Hourly Candle Sweep Detection (H1 / H2)
        h1_candles = candles_by_tf.get("H1", [])
        h1_sweep = HourlySweepDetector.detect_h1_sweep(h1_candles, poi=active_poi)

        # Fallback to H2 sweep if H1 is inconclusive
        if not h1_sweep and "H2" in candles_by_tf:
            h2_candles = candles_by_tf["H2"]
            h1_sweep = HourlySweepDetector.detect_h2_sweep_fallback(h2_candles, poi=active_poi)

        if not h1_sweep or not h1_sweep.swept:
            return None

        # Ensure sweep direction aligns with Daily Map bias
        if h1_sweep.direction != daily_map.bias:
            return None

        # Step 6: Lower Timeframe Execution (M15)
        m15_candles = candles_by_tf.get("M15", [])
        setup = EntryModelEvaluator.evaluate_entry(
            symbol=symbol,
            m15_candles=m15_candles,
            h1_sweep=h1_sweep,
            daily_map=daily_map,
            poi=active_poi
        )

        return setup


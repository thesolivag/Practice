"""
FZ-ASM Asian Session & Time and Price Mechanics.
Handles Asian Session window verification (00:00 - 06:00 UTC) and H1/H2 candle sweep detection.
"""

from __future__ import annotations

from typing import List, Optional
from datetime import datetime
from .types import Candle, HourlySweepResult, SessionWindow, BiasDirection, KeyLevel


SUPPORTED_PAIRS = {
    "USDJPY", "AUDJPY", "GBPJPY", "CADJPY", "EURJPY", "CHFJPY",
    "XAUUSD", "GOLD", "JP225"
}


class AsianSessionManager:
    """Manages Asian Session timing rules and asset verification."""

    def __init__(self, window: Optional[SessionWindow] = None, extra_pairs: Optional[Set[str]] = None):
        self.window = window or SessionWindow()
        self.supported_pairs = set(SUPPORTED_PAIRS)
        if extra_pairs:
            for p in extra_pairs:
                self.supported_pairs.add(p.upper().strip())

    def is_supported_symbol(self, symbol: str) -> bool:
        if not symbol or not isinstance(symbol, str):
            return False
        clean = symbol.upper().replace("/", "").replace("_", "").replace("-", "").strip()
        return any(clean.startswith(pair) or pair in clean for pair in self.supported_pairs)

    def is_in_asian_session(self, dt: datetime) -> bool:
        """Asian Session: 1:00 AM - 7:00 AM Nigeria (WAT / UTC+1) == 00:00 - 06:00 UTC."""
        if not dt:
            return False
        return self.window.is_in_session(dt)

    def is_in_prime_asian_window(self, dt: datetime) -> bool:
        """Prime Execution: 1:00 AM - 3:00 AM Nigeria == 00:00 - 02:00 UTC."""
        if not dt:
            return False
        return self.window.is_in_prime_window(dt)


class HourlySweepDetector:
    """Detects H1 (or H2 fallback) candle liquidity sweeps at Key Levels."""

    @staticmethod
    def detect_h1_sweep(candles: List[Candle], poi: Optional[KeyLevel] = None) -> Optional[HourlySweepResult]:
        """
        Inspects the latest completed H1 candle against the previous H1 candle:
        - Bullish Sweep: Current candle pierces below previous candle low with a wick,
          then closes back above previous low (rejection wick).
        - Bearish Sweep: Current candle pierces above previous candle high with a wick,
          then closes back below previous high (rejection wick).
        - Confluence: Confirms if the sweep tested the active KeyLevel/POI.
        - Resolves dual-sweep ambiguity on outside bars via close direction.
        """
        if len(candles) < 2:
            return None

        prev = candles[-2]
        curr = candles[-1]

        swept_low = curr.low < prev.low and curr.close > prev.low
        swept_high = curr.high > prev.high and curr.close < prev.high

        # Direction resolution for dual sweeps (outside bar sweeping both sides)
        if swept_low and swept_high:
            if curr.is_bullish:
                swept_high = False
            elif curr.is_bearish:
                swept_low = False
            else:
                return None  # Doji outside bar is ambiguous

        # Bullish Sweep of previous low
        if swept_low:
            tested_poi = poi.is_tested_by(curr) if poi else True
            if tested_poi:
                return HourlySweepResult(
                    swept=True,
                    direction=BiasDirection.BULLISH,
                    sweep_candle=curr,
                    swept_candle=prev,
                    sweep_price=curr.low,
                    key_level_tested=poi,
                    notes=f"Bullish H1 sweep: Pierced prior low {prev.low:.5f} with wick, rejected and closed at {curr.close:.5f}."
                )

        # Bearish Sweep of previous high
        if swept_high:
            tested_poi = poi.is_tested_by(curr) if poi else True
            if tested_poi:
                return HourlySweepResult(
                    swept=True,
                    direction=BiasDirection.BEARISH,
                    sweep_candle=curr,
                    swept_candle=prev,
                    sweep_price=curr.high,
                    key_level_tested=poi,
                    notes=f"Bearish H1 sweep: Pierced prior high {prev.high:.5f} with wick, rejected and closed at {curr.close:.5f}."
                )

        return None

    @staticmethod
    def detect_h2_sweep_fallback(h2_candles: List[Candle], poi: Optional[KeyLevel] = None) -> Optional[HourlySweepResult]:
        """
        FZ Fallback Rule: If H1 is ambiguous or did not sweep, inspect H2 candles.
        """
        return HourlySweepDetector.detect_h1_sweep(h2_candles, poi)


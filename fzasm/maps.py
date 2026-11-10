"""
The 5 Daily Maps of FZ-ASM.
Determines Higher Timeframe (D1 / 2D / 3D) Directional Bias ("FROM where TO where").
"""

from __future__ import annotations

from typing import List, Optional
from datetime import datetime
from .types import Candle, DailyMapResult, MapType, BiasDirection, KeyLevel


class DailyMapEvaluator:
    """Evaluates Daily candles to identify the active FZ Daily Map."""

    @staticmethod
    def evaluate(candles: List[Candle], structural_poi: Optional[KeyLevel] = None) -> Optional[DailyMapResult]:
        """
        Evaluates the latest completed daily candles (ordered oldest to newest).
        Returns the highest-priority qualifying Daily Map.
        """
        if len(candles) < 3:
            return None

        # Priority 1: Map 4 (Confluence of Candle Range CRT within Structural POI)
        m4 = DailyMapEvaluator._check_map_4(candles, structural_poi)
        if m4:
            return m4

        # Priority 2: Map 3 (Consecutive Uninterrupted Run with Sweep)
        m3 = DailyMapEvaluator._check_map_3(candles)
        if m3:
            return m3

        # Priority 3: Map 2 (Candle Range CRT)
        m2 = DailyMapEvaluator._check_map_2(candles)
        if m2:
            return m2

        # Priority 4: Map 5B (Sweep Invalidation) / Map 5A (Pure Rejection)
        m5 = DailyMapEvaluator._check_map_5(candles, structural_poi)
        if m5:
            return m5

        # Priority 5: Map 1 (Structural Range & Order Transfer)
        m1 = DailyMapEvaluator._check_map_1(candles)
        if m1:
            return m1

        return None

    @staticmethod
    def _check_map_2(candles: List[Candle]) -> Optional[DailyMapResult]:
        """
        Map 2: Candle Range (CRT).
        Checks if the latest candle (or yesterday's candle establishing today's bias)
        swept the high/low of the prior candle range and closed back inside.
        """
        for i in [-1, -2]:
            if abs(i) >= len(candles):
                continue
            curr = candles[i]
            prior = candles[i - 1]

            # Bullish CRT: Swept prior low, closed above prior low
            if curr.low < prior.low and curr.close > prior.low:
                # If checking prior candle (i == -2), ensure latest candle hasn't broken or finished it
                if i == -2:
                    latest = candles[-1]
                    if latest.low < curr.low or latest.high >= prior.high:
                        continue
                return DailyMapResult(
                    map_type=MapType.MAP_2_CANDLE_RANGE_CRT,
                    bias=BiasDirection.BULLISH,
                    origin_level=curr.low,
                    target_level=prior.high,
                    equilibrium_50=(curr.low + prior.high) / 2.0,
                    confidence=0.85,
                    notes=f"CRT: Swept prior daily low ({prior.low:.5f}) with rejection. Target prior daily high ({prior.high:.5f}).",
                    timestamp=curr.timestamp,
                    reference_candles=[prior, curr]
                )

            # Bearish CRT: Swept prior high, closed below prior high
            if curr.high > prior.high and curr.close < prior.high:
                # If checking prior candle (i == -2), ensure latest candle hasn't broken or finished it
                if i == -2:
                    latest = candles[-1]
                    if latest.high > curr.high or latest.low <= prior.low:
                        continue
                return DailyMapResult(
                    map_type=MapType.MAP_2_CANDLE_RANGE_CRT,
                    bias=BiasDirection.BEARISH,
                    origin_level=curr.high,
                    target_level=prior.low,
                    equilibrium_50=(curr.high + prior.low) / 2.0,
                    confidence=0.85,
                    notes=f"CRT: Swept prior daily high ({prior.high:.5f}) with rejection. Target prior daily low ({prior.low:.5f}).",
                    timestamp=curr.timestamp,
                    reference_candles=[prior, curr]
                )

        return None

    @staticmethod
    def _check_map_3(candles: List[Candle]) -> Optional[DailyMapResult]:
        """
        Map 3: Consecutive Uninterrupted Candles + Sweep.
        Detects consecutive directional candles (>=3) where the extreme is swept by a reversal candle.
        """
        curr = candles[-1]
        
        # Check consecutive bearish run swept by current candle
        bearish_run: List[Candle] = []
        for c in reversed(candles[:-1]):
            if c.is_bearish:
                bearish_run.append(c)
            else:
                break
        
        if len(bearish_run) >= 2:
            origin_high = max(c.high for c in bearish_run)
            lowest_low = min(c.low for c in bearish_run)
            # Did current candle sweep the lowest low of the run and close bullish/inside?
            if curr.low < lowest_low and curr.close > lowest_low:
                return DailyMapResult(
                    map_type=MapType.MAP_3_CONSECUTIVE_LEG_SWEEP,
                    bias=BiasDirection.BULLISH,
                    origin_level=curr.low,
                    target_level=origin_high,
                    equilibrium_50=(curr.low + origin_high) / 2.0,
                    confidence=0.90,
                    notes=f"Consecutive {len(bearish_run)} bearish candles swept at {lowest_low:.5f}. Target leg origin high ({origin_high:.5f}).",
                    timestamp=curr.timestamp,
                    reference_candles=list(reversed(bearish_run)) + [curr]
                )

        # Check consecutive bullish run swept by current candle
        bullish_run: List[Candle] = []
        for c in reversed(candles[:-1]):
            if c.is_bullish:
                bullish_run.append(c)
            else:
                break

        if len(bullish_run) >= 2:
            origin_low = min(c.low for c in bullish_run)
            highest_high = max(c.high for c in bullish_run)
            # Did current candle sweep the highest high of the run and close bearish/inside?
            if curr.high > highest_high and curr.close < highest_high:
                return DailyMapResult(
                    map_type=MapType.MAP_3_CONSECUTIVE_LEG_SWEEP,
                    bias=BiasDirection.BEARISH,
                    origin_level=curr.high,
                    target_level=origin_low,
                    equilibrium_50=(curr.high + origin_low) / 2.0,
                    confidence=0.90,
                    notes=f"Consecutive {len(bullish_run)} bullish candles swept at {highest_high:.5f}. Target leg origin low ({origin_low:.5f}).",
                    timestamp=curr.timestamp,
                    reference_candles=list(reversed(bullish_run)) + [curr]
                )

        return None

    @staticmethod
    def _check_map_4(candles: List[Candle], poi: Optional[KeyLevel]) -> Optional[DailyMapResult]:
        """
        Map 4: Candle Range (CRT) conforming inside a Structural POI / Discounted zone.
        """
        if not poi:
            return None

        m2 = DailyMapEvaluator._check_map_2(candles)
        if not m2:
            return None

        curr = candles[-1]
        tested = poi.is_tested_by(curr) or any(poi.is_tested_by(c) for c in m2.reference_candles)
        if tested:
            return DailyMapResult(
                map_type=MapType.MAP_4_CRT_POI_CONFLUENCE,
                bias=m2.bias,
                origin_level=m2.origin_level,
                target_level=m2.target_level,
                equilibrium_50=m2.equilibrium_50,
                confidence=0.95,
                notes=f"High confluence: CRT sweep inside {poi.level_type.value} ({poi.price_bottom:.5f}-{poi.price_top:.5f}).",
                timestamp=curr.timestamp,
                reference_candles=m2.reference_candles
            )
        return None

    @staticmethod
    def _check_map_5(candles: List[Candle], poi: Optional[KeyLevel]) -> Optional[DailyMapResult]:
        """
        Map 5: Rejection (5A) or Sweep Invalidation (5B) at Key Level.
        """
        if not poi:
            return None

        curr = candles[-1]
        if not poi.is_tested_by(curr):
            return None

        # 5B: Pierced level with wick, closed back outside/inside the POI boundaries
        if poi.direction == BiasDirection.BULLISH:
            if curr.low < poi.price_bottom and curr.close >= poi.price_bottom:
                return DailyMapResult(
                    map_type=MapType.MAP_5B_SWEEP_INVALIDATION,
                    bias=BiasDirection.BULLISH,
                    origin_level=curr.low,
                    target_level=poi.price_top + (poi.price_top - poi.price_bottom) * 3,
                    equilibrium_50=(curr.low + poi.price_top) / 2.0,
                    confidence=0.88,
                    notes="Map 5B: Bullish sweep invalidation below support POI with strong wick rejection.",
                    timestamp=curr.timestamp,
                    reference_candles=[curr]
                )
            # 5A: Pure rejection off top of support POI without penetration below
            if curr.low >= poi.price_bottom and curr.is_bullish and curr.lower_wick > curr.body_size * 0.5:
                return DailyMapResult(
                    map_type=MapType.MAP_5A_REJECTION,
                    bias=BiasDirection.BULLISH,
                    origin_level=curr.low,
                    target_level=poi.price_top + (poi.price_top - poi.price_bottom) * 3,
                    equilibrium_50=(curr.low + poi.price_top) / 2.0,
                    confidence=0.82,
                    notes="Map 5A: Pure bullish rejection off support POI without sweep.",
                    timestamp=curr.timestamp,
                    reference_candles=[curr]
                )

        if poi.direction == BiasDirection.BEARISH:
            if curr.high > poi.price_top and curr.close <= poi.price_top:
                return DailyMapResult(
                    map_type=MapType.MAP_5B_SWEEP_INVALIDATION,
                    bias=BiasDirection.BEARISH,
                    origin_level=curr.high,
                    target_level=poi.price_bottom - (poi.price_top - poi.price_bottom) * 3,
                    equilibrium_50=(curr.high + poi.price_bottom) / 2.0,
                    confidence=0.88,
                    notes="Map 5B: Bearish sweep invalidation above resistance POI with strong wick rejection.",
                    timestamp=curr.timestamp,
                    reference_candles=[curr]
                )
            # 5A: Pure rejection off bottom of resistance POI
            if curr.high <= poi.price_top and curr.is_bearish and curr.upper_wick > curr.body_size * 0.5:
                return DailyMapResult(
                    map_type=MapType.MAP_5A_REJECTION,
                    bias=BiasDirection.BEARISH,
                    origin_level=curr.high,
                    target_level=poi.price_bottom - (poi.price_top - poi.price_bottom) * 3,
                    equilibrium_50=(curr.high + poi.price_bottom) / 2.0,
                    confidence=0.82,
                    notes="Map 5A: Pure bearish rejection off resistance POI without sweep.",
                    timestamp=curr.timestamp,
                    reference_candles=[curr]
                )

        return None

    @staticmethod
    def _check_map_1(candles: List[Candle]) -> Optional[DailyMapResult]:
        """
        Map 1: Structural Range (Pro-Trend BOS & Order Transfer).
        """
        curr = candles[-1]
        prior = candles[-2]
        oldest = candles[-5] if len(candles) >= 5 else candles[0]

        range_high = max(c.high for c in candles[-5:])
        range_low = min(c.low for c in candles[-5:])
        eq = (range_high + range_low) / 2.0

        if curr.close > prior.high and curr.close > eq:
            return DailyMapResult(
                map_type=MapType.MAP_1_STRUCTURAL_RANGE,
                bias=BiasDirection.BULLISH,
                origin_level=range_low,
                target_level=range_high,
                equilibrium_50=eq,
                confidence=0.75,
                notes=f"Structural expansion: Bullish order transfer targeting range high ({range_high:.5f}).",
                timestamp=curr.timestamp,
                reference_candles=candles[-5:]
            )

        if curr.close < prior.low and curr.close < eq:
            return DailyMapResult(
                map_type=MapType.MAP_1_STRUCTURAL_RANGE,
                bias=BiasDirection.BEARISH,
                origin_level=range_high,
                target_level=range_low,
                equilibrium_50=eq,
                confidence=0.75,
                notes=f"Structural expansion: Bearish order transfer targeting range low ({range_low:.5f}).",
                timestamp=curr.timestamp,
                reference_candles=candles[-5:]
            )

        return None

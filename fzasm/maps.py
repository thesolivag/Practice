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
    def evaluate(candles: List[Candle], structural_poi: Optional[KeyLevel] = None, range_target: Optional[Candle] = None) -> Optional[DailyMapResult]:
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
        m5 = DailyMapEvaluator._check_map_5(candles, structural_poi, range_target)
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
        if len(candles) < 2:
            return None

        # Check i = -1 (latest completed candle is fresh CRT)
        curr = candles[-1]
        prior = candles[-2]

        # Bullish CRT: Swept prior low, closed back inside prior range
        if curr.low < prior.low and curr.close > prior.low and curr.high < prior.high:
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

        # Bearish CRT: Swept prior high, closed back inside prior range
        if curr.high > prior.high and curr.close < prior.high and curr.low > prior.low:
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

        # Check i = -2 (yesterday was CRT, today is trading toward the CRT target)
        if len(candles) >= 3:
            curr = candles[-2]
            prior = candles[-3]
            latest = candles[-1]

            # Yesterday Bullish CRT
            if curr.low < prior.low and curr.close > prior.low and curr.high < prior.high:
                # Latest candle must not have invalidated origin (broken curr.low),
                # must not have completed target (prior.high),
                # and must not have broken down below prior.low
                if latest.low >= curr.low and latest.high < prior.high and latest.close >= prior.low:
                    return DailyMapResult(
                        map_type=MapType.MAP_2_CANDLE_RANGE_CRT,
                        bias=BiasDirection.BULLISH,
                        origin_level=curr.low,
                        target_level=prior.high,
                        equilibrium_50=(curr.low + prior.high) / 2.0,
                        confidence=0.85,
                        notes=f"CRT: Active Bullish CRT from prior low sweep ({curr.low:.5f}). Target prior daily high ({prior.high:.5f}).",
                        timestamp=latest.timestamp,
                        reference_candles=[prior, curr]
                    )

            # Yesterday Bearish CRT
            if curr.high > prior.high and curr.close < prior.high and curr.low > prior.low:
                # Latest candle must not have invalidated origin (broken curr.high),
                # must not have completed target (prior.low),
                # and must not have broken out above prior.high
                if latest.high <= curr.high and latest.low > prior.low and latest.close <= prior.high:
                    return DailyMapResult(
                        map_type=MapType.MAP_2_CANDLE_RANGE_CRT,
                        bias=BiasDirection.BEARISH,
                        origin_level=curr.high,
                        target_level=prior.low,
                        equilibrium_50=(curr.high + prior.low) / 2.0,
                        confidence=0.85,
                        notes=f"CRT: Active Bearish CRT from prior high sweep ({curr.high:.5f}). Target prior daily low ({prior.low:.5f}).",
                        timestamp=latest.timestamp,
                        reference_candles=[prior, curr]
                    )

        return None

    @staticmethod
    def _check_map_3(candles: List[Candle]) -> Optional[DailyMapResult]:
        """
        Map 3: Consecutive Uninterrupted Candles + Sweep.
        Detects consecutive directional candles (>=2) where the extreme is swept by a reversal candle.
        """
        if len(candles) < 3:
            return None

        # Check i = -1 (latest candle is sweep candle)
        curr = candles[-1]
        bearish_run: List[Candle] = []
        for c in reversed(candles[:-1]):
            if c.is_bearish:
                bearish_run.append(c)
            else:
                break

        if len(bearish_run) >= 2:
            origin_high = max(c.high for c in bearish_run)
            lowest_low = min(c.low for c in bearish_run)
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

        bullish_run: List[Candle] = []
        for c in reversed(candles[:-1]):
            if c.is_bullish:
                bullish_run.append(c)
            else:
                break

        if len(bullish_run) >= 2:
            origin_low = min(c.low for c in bullish_run)
            highest_high = max(c.high for c in bullish_run)
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

        # Check i = -2 (sweep candle was yesterday, actively trading toward target)
        if len(candles) >= 4:
            curr = candles[-2]
            latest = candles[-1]
            prior_candles = candles[:-2]

            bearish_run_prev: List[Candle] = []
            for c in reversed(prior_candles):
                if c.is_bearish:
                    bearish_run_prev.append(c)
                else:
                    break

            if len(bearish_run_prev) >= 2:
                origin_high = max(c.high for c in bearish_run_prev)
                lowest_low = min(c.low for c in bearish_run_prev)
                if curr.low < lowest_low and curr.close > lowest_low:
                    if latest.low >= curr.low and latest.high < origin_high:
                        return DailyMapResult(
                            map_type=MapType.MAP_3_CONSECUTIVE_LEG_SWEEP,
                            bias=BiasDirection.BULLISH,
                            origin_level=curr.low,
                            target_level=origin_high,
                            equilibrium_50=(curr.low + origin_high) / 2.0,
                            confidence=0.90,
                            notes=f"Consecutive {len(bearish_run_prev)} bearish candles swept at {lowest_low:.5f} (active). Target leg origin high ({origin_high:.5f}).",
                            timestamp=latest.timestamp,
                            reference_candles=list(reversed(bearish_run_prev)) + [curr]
                        )

            bullish_run_prev: List[Candle] = []
            for c in reversed(prior_candles):
                if c.is_bullish:
                    bullish_run_prev.append(c)
                else:
                    break

            if len(bullish_run_prev) >= 2:
                origin_low = min(c.low for c in bullish_run_prev)
                highest_high = max(c.high for c in bullish_run_prev)
                if curr.high > highest_high and curr.close < highest_high:
                    if latest.high <= curr.high and latest.low > origin_low:
                        return DailyMapResult(
                            map_type=MapType.MAP_3_CONSECUTIVE_LEG_SWEEP,
                            bias=BiasDirection.BEARISH,
                            origin_level=curr.high,
                            target_level=origin_low,
                            equilibrium_50=(curr.high + origin_low) / 2.0,
                            confidence=0.90,
                            notes=f"Consecutive {len(bullish_run_prev)} bullish candles swept at {highest_high:.5f} (active). Target leg origin low ({origin_low:.5f}).",
                            timestamp=latest.timestamp,
                            reference_candles=list(reversed(bullish_run_prev)) + [curr]
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

        sweep_candle = m2.reference_candles[-1] if m2.reference_candles else candles[-1]
        curr = candles[-1]

        # Check if the CRT sweep candle or current candle tested the POI
        if poi.is_tested_by(sweep_candle) or poi.is_tested_by(curr):
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
    def _check_map_5(candles: List[Candle], poi: Optional[KeyLevel], range_target: Optional[Candle] = None) -> Optional[DailyMapResult]:
        """
        Map 5: Rejection (5A) or Sweep Invalidation (5B) at Key Level.
        """
        if not poi or len(candles) < 1:
            return None

        curr = candles[-1]
        if not poi.is_tested_by(curr):
            return None

        # A rejection does not identify its destination. Require an explicitly
        # selected, already-closed range boundary. Never synthesize 3*zone height.
        if range_target is None or range_target.available_at > curr.timestamp:
            return None
        target = range_target.high if poi.direction == BiasDirection.BULLISH else range_target.low
        if (poi.direction == BiasDirection.BULLISH and target <= curr.high) or (poi.direction == BiasDirection.BEARISH and target >= curr.low):
            return None

        # 5B: Pierced level with wick, closed back outside/inside the POI boundaries
        if poi.direction == BiasDirection.BULLISH:
            if curr.low < poi.price_bottom and curr.close >= poi.price_bottom:
                return DailyMapResult(
                    map_type=MapType.MAP_5B_SWEEP_INVALIDATION,
                    bias=BiasDirection.BULLISH,
                    origin_level=curr.low,
                    target_level=target,
                    equilibrium_50=(curr.low + target) / 2.0,
                    confidence=0.88,
                    notes="Map 5B: Bullish sweep invalidation below support POI with strong wick rejection.",
                    timestamp=curr.timestamp,
                    reference_candles=[range_target, curr]
                )
            # 5A: Pure rejection off top of support POI without penetration below
            if curr.low >= poi.price_bottom and curr.is_bullish and curr.lower_wick > curr.body_size * 0.5:
                return DailyMapResult(
                    map_type=MapType.MAP_5A_REJECTION,
                    bias=BiasDirection.BULLISH,
                    origin_level=curr.low,
                    target_level=target,
                    equilibrium_50=(curr.low + target) / 2.0,
                    confidence=0.82,
                    notes="Map 5A: Pure bullish rejection off support POI without sweep.",
                    timestamp=curr.timestamp,
                    reference_candles=[range_target, curr]
                )

        if poi.direction == BiasDirection.BEARISH:
            if curr.high > poi.price_top and curr.close <= poi.price_top:
                return DailyMapResult(
                    map_type=MapType.MAP_5B_SWEEP_INVALIDATION,
                    bias=BiasDirection.BEARISH,
                    origin_level=curr.high,
                    target_level=target,
                    equilibrium_50=(curr.high + target) / 2.0,
                    confidence=0.88,
                    notes="Map 5B: Bearish sweep invalidation above resistance POI with strong wick rejection.",
                    timestamp=curr.timestamp,
                    reference_candles=[range_target, curr]
                )
            # 5A: Pure rejection off bottom of resistance POI
            if curr.high <= poi.price_top and curr.is_bearish and curr.upper_wick > curr.body_size * 0.5:
                return DailyMapResult(
                    map_type=MapType.MAP_5A_REJECTION,
                    bias=BiasDirection.BEARISH,
                    origin_level=curr.high,
                    target_level=target,
                    equilibrium_50=(curr.high + target) / 2.0,
                    confidence=0.82,
                    notes="Map 5A: Pure bearish rejection off resistance POI without sweep.",
                    timestamp=curr.timestamp,
                    reference_candles=[range_target, curr]
                )

        return None

    @staticmethod
    def _check_map_1(candles: List[Candle]) -> Optional[DailyMapResult]:
        """
        Map 1: Structural Range (Pro-Trend BOS & Order Transfer).
        """
        if len(candles) < 2:
            return None

        curr = candles[-1]
        prior = candles[-2]
        window = candles[-5:] if len(candles) >= 5 else candles

        range_high = max(c.high for c in window)
        range_low = min(c.low for c in window)
        eq = (range_high + range_low) / 2.0

        if curr.close > prior.high and curr.close > eq:
            prior_high = max(c.high for c in window[:-1])
            target = range_high if curr.close < range_high else curr.close + max(curr.total_range, range_high - range_low)
            return DailyMapResult(
                map_type=MapType.MAP_1_STRUCTURAL_RANGE,
                bias=BiasDirection.BULLISH,
                origin_level=range_low,
                target_level=target,
                equilibrium_50=eq,
                confidence=0.75,
                notes=f"Structural expansion: Bullish order transfer targeting {target:.5f}.",
                timestamp=curr.timestamp,
                reference_candles=window
            )

        if curr.close < prior.low and curr.close < eq:
            prior_low = min(c.low for c in window[:-1])
            target = range_low if curr.close > range_low else curr.close - max(curr.total_range, range_high - range_low)
            return DailyMapResult(
                map_type=MapType.MAP_1_STRUCTURAL_RANGE,
                bias=BiasDirection.BEARISH,
                origin_level=range_high,
                target_level=target,
                equilibrium_50=eq,
                confidence=0.75,
                notes=f"Structural expansion: Bearish order transfer targeting {target:.5f}.",
                timestamp=curr.timestamp,
                reference_candles=window
            )

        return None
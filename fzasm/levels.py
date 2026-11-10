"""
FZ-ASM Key Levels & POI Detectors.
Detects Order Blocks, Breaker Blocks, Open-Close levels, and Engulfing Candle Power Units.
"""

from __future__ import annotations

from typing import List, Optional
from datetime import datetime
from .types import Candle, KeyLevel, LevelType, BiasDirection


class KeyLevelDetector:
    """Detects and tracks key levels across HTF and ITF timeframes."""

    @staticmethod
    def detect_order_blocks(candles: List[Candle], timeframe: str = "H4") -> List[KeyLevel]:
        """
        Detects Order Blocks requiring FVG validation:
        - Bullish OB: Last bearish candle prior to a bullish rally that leaves a Fair Value Gap (FVG).
        - Bearish OB: Last bullish candle prior to a bearish drop that leaves an FVG.
        """
        order_blocks: List[KeyLevel] = []
        if len(candles) < 3:
            return order_blocks

        for i in range(len(candles) - 2):
            c1 = candles[i]
            c2 = candles[i + 1]
            c3 = candles[i + 2]

            # Bullish Order Block candidate: c1 is bearish, c2/c3 expand upward
            if c1.is_bearish and c2.is_bullish:
                # FVG check: c3.low > c1.high creates a true imbalance
                has_fvg = c3.low > c1.high
                if has_fvg or (c2.body_size > c1.body_size * 1.5 and c2.close > c1.high):
                    # Check if c1 swept prior candle low (makes OB higher probability per FZ)
                    swept_liq = candles[i - 1].low > c1.low if i > 0 else False
                    ob = KeyLevel(
                        level_type=LevelType.ORDER_BLOCK,
                        direction=BiasDirection.BULLISH,
                        price_top=c1.body_high,
                        price_bottom=c1.low,
                        timestamp=c1.timestamp,
                        timeframe=timeframe,
                        source_candle=c1,
                        metadata={
                            "swept_liquidity": swept_liq,
                            "fvg_gap": max(0.0, c3.low - c1.high)
                        }
                    )
                    order_blocks.append(ob)

            # Bearish Order Block candidate: c1 is bullish, c2/c3 expand downward
            if c1.is_bullish and c2.is_bearish:
                has_fvg = c3.high < c1.low
                if has_fvg or (c2.body_size > c1.body_size * 1.5 and c2.close < c1.low):
                    swept_liq = candles[i - 1].high < c1.high if i > 0 else False
                    ob = KeyLevel(
                        level_type=LevelType.ORDER_BLOCK,
                        direction=BiasDirection.BEARISH,
                        price_top=c1.high,
                        price_bottom=c1.body_low,
                        timestamp=c1.timestamp,
                        timeframe=timeframe,
                        source_candle=c1,
                        metadata={
                            "swept_liquidity": swept_liq,
                            "fvg_gap": max(0.0, c1.low - c3.high)
                        }
                    )
                    order_blocks.append(ob)

        return order_blocks

    @staticmethod
    def detect_breaker_blocks(candles: List[Candle], order_blocks: List[KeyLevel]) -> List[KeyLevel]:
        """
        Detects Breaker Blocks:
        An Order Block that was disrespected and broken through with a candle BODY close.
        Flips from Bullish OB -> Bearish Breaker, or Bearish OB -> Bullish Breaker.
        """
        breakers: List[KeyLevel] = []
        for ob in order_blocks:
            # Find candles that occurred after the OB
            subsequent = [c for c in candles if c.timestamp > ob.timestamp]
            for c in subsequent:
                # Bullish OB broken downward with body close below its bottom -> Bearish Breaker
                if ob.direction == BiasDirection.BULLISH and c.close < ob.price_bottom:
                    breaker = KeyLevel(
                        level_type=LevelType.BREAKER_BLOCK,
                        direction=BiasDirection.BEARISH,
                        price_top=ob.price_top,
                        price_bottom=ob.price_bottom,
                        timestamp=c.timestamp,
                        timeframe=ob.timeframe,
                        source_candle=ob.source_candle,
                        metadata={"original_ob_timestamp": ob.timestamp.isoformat()}
                    )
                    breakers.append(breaker)
                    ob.mitigated = True
                    break

                # Bearish OB broken upward with body close above its top -> Bullish Breaker
                if ob.direction == BiasDirection.BEARISH and c.close > ob.price_top:
                    breaker = KeyLevel(
                        level_type=LevelType.BREAKER_BLOCK,
                        direction=BiasDirection.BULLISH,
                        price_top=ob.price_top,
                        price_bottom=ob.price_bottom,
                        timestamp=c.timestamp,
                        timeframe=ob.timeframe,
                        source_candle=ob.source_candle,
                        metadata={"original_ob_timestamp": ob.timestamp.isoformat()}
                    )
                    breakers.append(breaker)
                    ob.mitigated = True
                    break

        return breakers

    @staticmethod
    def detect_open_close_levels(candles: List[Candle], timeframe: str = "H1") -> List[KeyLevel]:
        """
        Detects Open-Close Key Levels:
        Horizontal levels at candle open/close body edges of major expansion candles.
        """
        levels: List[KeyLevel] = []
        if len(candles) < 2:
            return levels

        # Identify candles with body size in the top quartile of the dataset
        avg_body = sum(c.body_size for c in candles) / len(candles)
        if avg_body <= 0.0:
            return levels
        for c in candles:
            if c.body_size >= avg_body * 1.5:
                # Open-close zone
                direction = BiasDirection.BULLISH if c.is_bullish else BiasDirection.BEARISH
                lvl = KeyLevel(
                    level_type=LevelType.OPEN_CLOSE,
                    direction=direction,
                    price_top=c.body_high,
                    price_bottom=c.body_low,
                    timestamp=c.timestamp,
                    timeframe=timeframe,
                    source_candle=c
                )
                levels.append(lvl)

        return levels

    @staticmethod
    def detect_power_unit_engulfing(candles: List[Candle], poi: Optional[KeyLevel] = None) -> Optional[Candle]:
        """
        FZ's Power Unit:
        Detects if the latest candle is an Engulfing Candle confirming institutional volume,
        especially when interacting with an active POI.
        """
        if len(candles) < 2:
            return None

        curr = candles[-1]
        prev = candles[-2]

        if curr.is_engulfing(prev):
            if poi is None or poi.is_tested_by(curr):
                return curr

        return None


"""Closed M5/M10/M15 confirmation and pending retest orders.

The four-bar minor-structure proxy remains explicit and requires further chart
validation. No H1 substitution, market-at-shift entry, or invented target.
"""
from typing import List, Optional
from .types import Candle, TradeSetup, EntryModelType, BiasDirection, KeyLevel, LevelType
from . import instruments


class EntryModelEvaluator:
    @staticmethod
    def evaluate_entry(symbol, m15_candles, h1_sweep, daily_map, poi=None,
                       buffer_pips=None) -> Optional[TradeSetup]:
        candles = m15_candles  # retained argument name for API compatibility
        if len(candles) < 5 or not h1_sweep or daily_map.bias != h1_sweep.direction:
            return None
        curr = candles[-1]
        if curr.timeframe not in ("M5", "M10", "M15"):
            return None
        if any(c.timeframe != curr.timeframe for c in candles):
            return None
        if any(a.available_at != b.timestamp for a,b in zip(candles[-5:-1],candles[-4:])):
            return None
        # Only a confirmation formed after the completed sweep can place an order.
        if curr.timestamp < h1_sweep.sweep_candle.available_at:
            return None
        long = daily_map.bias == BiasDirection.BULLISH
        buf = buffer_pips if buffer_pips is not None else 3 * instruments.pip(symbol)
        previous = candles[-5:-1]
        boundary = max(c.high for c in previous) if long else min(c.low for c in previous)
        shifted = curr.close > boundary if long else curr.close < boundary
        entry = level = None
        model = None
        if shifted:
            # A confirmed three-candle FVG from this displacement is known now.
            left = candles[-3]
            if long and curr.low > left.high:
                level = KeyLevel(LevelType.FAIR_VALUE_GAP, daily_map.bias, curr.low,
                                 left.high, curr.available_at, curr.timeframe)
            elif not long and curr.high < left.low:
                level = KeyLevel(LevelType.FAIR_VALUE_GAP, daily_map.bias, left.low,
                                 curr.high, curr.available_at, curr.timeframe)
            else:
                # Last opposing candle of the displacement is the retest zone.
                opposing = [c for c in previous if c.is_bearish] if long else [c for c in previous if c.is_bullish]
                if opposing:
                    origin = opposing[-1]
                    level = KeyLevel(LevelType.ORDER_BLOCK, daily_map.bias,
                                     origin.body_high if long else origin.high,
                                     origin.low if long else origin.body_low,
                                     curr.available_at, curr.timeframe, source_candle=origin)
            if level:
                entry = level.price_top if long else level.price_bottom
                model = EntryModelType.MODEL_A_CHOCH_RETEST
        elif poi and poi.direction == daily_map.bias and not poi.mitigated:
            # Candidate stands short of an untouched level; confirm rejection away.
            candidate = candles[-2]
            if candidate.timestamp < h1_sweep.sweep_candle.available_at:
                return None
            tolerance = max(candidate.total_range * .5, buf * 5)
            gap = candidate.low - poi.price_top if long else poi.price_bottom - candidate.high
            rejects = (curr.low >= candidate.low and curr.close > candidate.close) if long else (curr.high <= candidate.high and curr.close < candidate.close)
            if 0 < gap <= tolerance and rejects:
                level = poi
                entry = poi.price_top if long else poi.price_bottom
                model = EntryModelType.MODEL_B_INDUCEMENT_LIMIT
        if entry is None:
            return None
        stop = min(h1_sweep.sweep_price, level.price_bottom) - buf if long else max(h1_sweep.sweep_price, level.price_top) + buf
        tp1, tp2 = daily_map.equilibrium_50, daily_map.target_level
        valid = stop < entry < tp1 < tp2 and entry < curr.close if long else stop > entry > tp1 > tp2 and entry > curr.close
        if not valid:
            return None
        return TradeSetup(symbol, curr.available_at, daily_map.bias, model,
                          entry, stop, tp1, tp2, abs(tp2-entry)/abs(entry-stop),
                          daily_map, h1_sweep, timeframe=curr.timeframe, key_level=level,
                          notes="Pending limit: requires subsequent retest/fill. Four-bar shift proxy; targets from frozen map.")

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
                       buffer_pips=None, require_shift=False) -> Optional[TradeSetup]:
        candles = m15_candles  # retained argument name for API compatibility
        if len(candles) < 5 or not h1_sweep or not h1_sweep.swept or daily_map.bias != h1_sweep.direction:
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
        local_stop = None
        evidence = {"structure_rule": "closed_break_of_previous_four_bars",
                    "structure_boundary": boundary, "stop_buffer_price": buf}
        if shifted:
            opposing = [c for c in previous if c.is_bearish] if long else [c for c in previous if c.is_bullish]
            # Freeze the last opposing launch candle and its departure leg now.
            # This is an explicit research invalidation rule, never chosen by outcome.
            if opposing:
                origin = opposing[-1]
                leg = [c for c in candles if origin.timestamp <= c.timestamp <= curr.timestamp]
                local_extreme = min(c.low for c in leg) if long else max(c.high for c in leg)
                local_stop = local_extreme - buf if long else local_extreme + buf
                evidence.update(local_stop_origin=origin.timestamp.isoformat(),
                                local_stop_extreme=local_extreme,
                                local_stop_rule="last_opposing_candle_and_departure_leg")
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
                evidence["entry_rule"] = "fvg_surface" if level.level_type == LevelType.FAIR_VALUE_GAP else "order_block_retest"
                if level.level_type == LevelType.FAIR_VALUE_GAP:
                    # Prefer a pre-existing, direction-aligned POI boundary inside
                    # the gap. Its formation time must predate this displacement.
                    overlaps = []
                    if poi and not poi.mitigated and poi.direction == daily_map.bias and poi.timestamp <= curr.timestamp:
                        overlaps = [v for v in (poi.price_bottom, poi.price_top) if level.contains(v)]
                    if overlaps:
                        entry = max(overlaps) if long else min(overlaps)
                        evidence.update(entry_rule="fvg_overlapping_key_level",
                                        overlap_level_time=poi.timestamp.isoformat(),
                                        overlap_level_type=poi.level_type.value)
                model = EntryModelType.MODEL_A_CHOCH_RETEST
        elif not require_shift and poi and poi.direction == daily_map.bias and not poi.mitigated:
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
        stop = h1_sweep.sweep_price - buf if long else h1_sweep.sweep_price + buf
        if local_stop is not None and not (local_stop < entry if long else local_stop > entry):
            local_stop = None
        evidence.update(confirmation_close=curr.available_at.isoformat(),
                        sweep_timeframe=h1_sweep.sweep_candle.timeframe,
                        sweep_extreme=h1_sweep.sweep_price,
                        local_stop_available=local_stop is not None)
        tp1, tp2 = daily_map.equilibrium_50, daily_map.target_level
        valid = stop < entry < tp1 < tp2 and entry < curr.close if long else stop > entry > tp1 > tp2 and entry > curr.close
        if not valid:
            return None
        return TradeSetup(symbol, curr.available_at, daily_map.bias, model,
                          entry, stop, tp1, tp2, abs(tp2-entry)/abs(entry-stop),
                          daily_map, h1_sweep, timeframe=curr.timeframe, key_level=level,
                          notes="Pending limit: requires subsequent retest/fill. Four-bar shift proxy; targets from frozen map.",
                          stop_candidates={"hourly_sweep": stop, "ltf_invalidation": local_stop},
                          entry_evidence=evidence)

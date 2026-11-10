"""
FZ-ASM Lower Timeframe Execution Models (M15 / M10 / M5).
Implements Model A (Market Shift / CHOCH) and Model B (Candlestick Liquidity Inducement).
"""

from __future__ import annotations

from typing import List, Optional
from datetime import datetime
from .types import (
    Candle,
    TradeSetup,
    EntryModelType,
    BiasDirection,
    HourlySweepResult,
    DailyMapResult,
    KeyLevel,
    LevelType,
)


class EntryModelEvaluator:
    """Evaluates M15 / M10 / M5 candles following an H1/H2 sweep to construct TradeSetups."""

    @staticmethod
    def evaluate_entry(
        symbol: str,
        m15_candles: List[Candle],
        h1_sweep: HourlySweepResult,
        daily_map: DailyMapResult,
        poi: Optional[KeyLevel] = None,
        buffer_pips: float = 0.0003  # default 3 pips buffer for stop loss
    ) -> Optional[TradeSetup]:
        """
        Evaluates M15 candles after an H1 sweep:
        Tries Model A (CHOCH) first, then Model B (Inducement limit).
        """
        if len(m15_candles) < 3:
            return None

        # Check Model A: CHOCH on M15
        setup_a = EntryModelEvaluator._check_model_a_choch(
            symbol, m15_candles, h1_sweep, daily_map, poi, buffer_pips
        )
        if setup_a:
            return setup_a

        # Check Model B: Candlestick Liquidity Inducement
        setup_b = EntryModelEvaluator._check_model_b_inducement(
            symbol, m15_candles, h1_sweep, daily_map, poi, buffer_pips
        )
        if setup_b:
            return setup_b

        return None

    @staticmethod
    def _check_model_a_choch(
        symbol: str,
        candles: List[Candle],
        h1_sweep: HourlySweepResult,
        daily_map: DailyMapResult,
        poi: Optional[KeyLevel],
        buffer_pips: float
    ) -> Optional[TradeSetup]:
        """
        Model A: Market Shift / CHOCH on M15.
        - After a Bullish H1 Sweep: Look for M15 candle closing with body above the recent swing high.
        - After a Bearish H1 Sweep: Look for M15 candle closing with body below the recent swing low.
        """
        curr = candles[-1]
        prior_candles = candles[:-1]

        if h1_sweep.direction == BiasDirection.BULLISH:
            minor_high = max(c.high for c in prior_candles[-4:])
            # CHOCH confirmation: current candle body closes above minor high
            if curr.close > minor_high:
                # Retest entry at M15 discount / FVG (or current close as market entry)
                entry_price = curr.close
                stop_loss = h1_sweep.sweep_candle.low - buffer_pips
                tp1 = daily_map.equilibrium_50
                tp2 = daily_map.target_level
                risk = abs(entry_price - stop_loss)
                reward = abs(tp2 - entry_price)
                rr = reward / risk if risk > 0 else 0.0

                return TradeSetup(
                    symbol=symbol,
                    timestamp=curr.timestamp,
                    bias=BiasDirection.BULLISH,
                    entry_model=EntryModelType.MODEL_A_CHOCH_RETEST,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit_1=tp1,
                    take_profit_2=tp2,
                    risk_reward=round(rr, 2),
                    daily_map=daily_map,
                    h1_sweep=h1_sweep,
                    timeframe="M15",
                    key_level=poi,
                    notes=f"Model A Bullish CHOCH: M15 closed above minor high ({minor_high:.5f}). SL under H1 sweep low ({stop_loss:.5f})."
                )

        if h1_sweep.direction == BiasDirection.BEARISH:
            minor_low = min(c.low for c in prior_candles[-4:])
            # CHOCH confirmation: current candle body closes below minor low
            if curr.close < minor_low:
                entry_price = curr.close
                stop_loss = h1_sweep.sweep_candle.high + buffer_pips
                tp1 = daily_map.equilibrium_50
                tp2 = daily_map.target_level
                risk = abs(stop_loss - entry_price)
                reward = abs(entry_price - tp2)
                rr = reward / risk if risk > 0 else 0.0

                return TradeSetup(
                    symbol=symbol,
                    timestamp=curr.timestamp,
                    bias=BiasDirection.BEARISH,
                    entry_model=EntryModelType.MODEL_A_CHOCH_RETEST,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit_1=tp1,
                    take_profit_2=tp2,
                    risk_reward=round(rr, 2),
                    daily_map=daily_map,
                    h1_sweep=h1_sweep,
                    timeframe="M15",
                    key_level=poi,
                    notes=f"Model A Bearish CHOCH: M15 closed below minor low ({minor_low:.5f}). SL above H1 sweep high ({stop_loss:.5f})."
                )

        return None

    @staticmethod
    def _check_model_b_inducement(
        symbol: str,
        candles: List[Candle],
        h1_sweep: HourlySweepResult,
        daily_map: DailyMapResult,
        poi: Optional[KeyLevel],
        buffer_pips: float
    ) -> Optional[TradeSetup]:
        """
        Model B: Candlestick Liquidity Inducement.
        Detects an inducement candle that approaches the key level but falls short by a few pips,
        leaving liquidity. Sets a limit order on the POI right behind the inducement.
        """
        if not poi:
            return None

        curr = candles[-1]
        prev = candles[-2]

        if h1_sweep.direction == BiasDirection.BULLISH:
            # Prev candle pulled down near POI but did not touch POI top (inducement)
            if prev.low > poi.price_top and (prev.low - poi.price_top) <= (curr.body_size * 0.8):
                entry_price = poi.price_top
                stop_loss = poi.price_bottom - buffer_pips
                tp1 = daily_map.equilibrium_50
                tp2 = daily_map.target_level
                risk = abs(entry_price - stop_loss)
                reward = abs(tp2 - entry_price)
                rr = reward / risk if risk > 0 else 0.0

                return TradeSetup(
                    symbol=symbol,
                    timestamp=curr.timestamp,
                    bias=BiasDirection.BULLISH,
                    entry_model=EntryModelType.MODEL_B_INDUCEMENT_LIMIT,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit_1=tp1,
                    take_profit_2=tp2,
                    risk_reward=round(rr, 2),
                    daily_map=daily_map,
                    h1_sweep=h1_sweep,
                    timeframe="M15",
                    key_level=poi,
                    notes=f"Model B Bullish Inducement: Inducement low at {prev.low:.5f}. Limit order set on support POI top ({entry_price:.5f})."
                )

        if h1_sweep.direction == BiasDirection.BEARISH:
            # Prev candle pushed up near POI but did not touch POI bottom (inducement)
            if prev.high < poi.price_bottom and (poi.price_bottom - prev.high) <= (curr.body_size * 0.8):
                entry_price = poi.price_bottom
                stop_loss = poi.price_top + buffer_pips
                tp1 = daily_map.equilibrium_50
                tp2 = daily_map.target_level
                risk = abs(stop_loss - entry_price)
                reward = abs(entry_price - tp2)
                rr = reward / risk if risk > 0 else 0.0

                return TradeSetup(
                    symbol=symbol,
                    timestamp=curr.timestamp,
                    bias=BiasDirection.BEARISH,
                    entry_model=EntryModelType.MODEL_B_INDUCEMENT_LIMIT,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit_1=tp1,
                    take_profit_2=tp2,
                    risk_reward=round(rr, 2),
                    daily_map=daily_map,
                    h1_sweep=h1_sweep,
                    timeframe="M15",
                    key_level=poi,
                    notes=f"Model B Bearish Inducement: Inducement high at {prev.high:.5f}. Limit order set on resistance POI bottom ({entry_price:.5f})."
                )

        return None


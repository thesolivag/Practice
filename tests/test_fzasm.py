"""
Unit tests for the FZ-ASM trading strategy engine.
Tests all components: types, levels, maps, session management, entry models, and the unified engine.
"""

import pytest
from datetime import datetime, timezone
from fzasm.types import (
    Candle,
    BiasDirection,
    MapType,
    LevelType,
    EntryModelType,
    KeyLevel,
)
from fzasm.levels import KeyLevelDetector
from fzasm.maps import DailyMapEvaluator
from fzasm.sessions import AsianSessionManager, HourlySweepDetector
from fzasm.entry import EntryModelEvaluator
from fzasm.engine import FZASMEngine


def make_candle(dt_hour: int, o: float, h: float, l: float, c: float, tf: str = "H1", day: int = 1) -> Candle:
    dt = datetime(2026, 11, day, dt_hour, 0, tzinfo=timezone.utc)
    return Candle(timestamp=dt, open=o, high=h, low=l, close=c, timeframe=tf)


class TestCandleAndPowerUnit:
    def test_candle_basics(self):
        c_bull = make_candle(1, 100.0, 105.0, 99.0, 104.0)
        assert c_bull.is_bullish
        assert not c_bull.is_bearish
        assert c_bull.body_high == 104.0
        assert c_bull.body_low == 100.0
        assert c_bull.upper_wick == 1.0
        assert c_bull.lower_wick == 1.0

        c_bear = make_candle(2, 104.0, 106.0, 98.0, 99.0)
        assert c_bear.is_bearish
        assert c_bear.body_high == 104.0
        assert c_bear.body_low == 99.0

    def test_power_unit_engulfing(self):
        # Prev small candle
        c_prev = make_candle(1, 100.0, 102.0, 99.0, 101.0)
        # Bearish engulfing power unit
        c_engulf = make_candle(2, 103.0, 104.0, 97.0, 98.0)
        assert c_engulf.is_engulfing(c_prev)

        # Bullish engulfing power unit
        c_small_bear = make_candle(3, 100.0, 101.0, 98.0, 99.0)
        c_bull_engulf = make_candle(4, 98.0, 105.0, 97.0, 104.0)
        assert c_bull_engulf.is_engulfing(c_small_bear)


class TestKeyLevels:
    def test_detect_order_blocks_with_fvg(self):
        # 3 candles forming bullish OB:
        # c1: bearish candle
        # c2: strong bullish impulse
        # c3: continuing higher, c3.low > c1.high (creates FVG)
        c1 = make_candle(1, 102.0, 103.0, 99.0, 100.0)
        c2 = make_candle(2, 100.0, 106.0, 100.0, 105.0)
        c3 = make_candle(3, 105.0, 110.0, 104.0, 109.0)

        obs = KeyLevelDetector.detect_order_blocks([c1, c2, c3], timeframe="H4")
        assert len(obs) == 1
        ob = obs[0]
        assert ob.level_type == LevelType.ORDER_BLOCK
        assert ob.direction == BiasDirection.BULLISH
        assert ob.price_top == 102.0
        assert ob.price_bottom == 99.0
        assert ob.metadata["fvg_gap"] == 1.0  # 104.0 - 103.0

    def test_detect_breaker_blocks(self):
        # Bullish OB that gets broken downward
        ob = KeyLevel(
            level_type=LevelType.ORDER_BLOCK,
            direction=BiasDirection.BULLISH,
            price_top=100.0,
            price_bottom=95.0,
            timestamp=datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc),
            timeframe="H4"
        )
        # Candle closing below 95.0
        c_break = make_candle(5, 98.0, 99.0, 92.0, 93.0)
        breakers = KeyLevelDetector.detect_breaker_blocks([c_break], [ob])
        assert len(breakers) == 1
        bb = breakers[0]
        assert bb.level_type == LevelType.BREAKER_BLOCK
        assert bb.direction == BiasDirection.BEARISH
        assert ob.mitigated is True


class TestDailyMaps:
    def test_map_2_candle_range_crt_bullish(self):
        d1 = make_candle(0, 100.0, 110.0, 95.0, 105.0, tf="D1", day=1)
        # d2 sweeps d1 low (95.0) down to 93.0 and closes at 102.0 back inside
        d2 = make_candle(0, 105.0, 106.0, 93.0, 102.0, tf="D1", day=2)
        d3 = make_candle(0, 102.0, 104.0, 101.0, 103.0, tf="D1", day=3)

        res = DailyMapEvaluator.evaluate([d1, d2, d3])
        assert res is not None
        assert res.map_type == MapType.MAP_2_CANDLE_RANGE_CRT
        assert res.bias == BiasDirection.BULLISH
        assert res.origin_level == 93.0
        assert res.target_level == 110.0

    def test_map_3_consecutive_leg_sweep(self):
        # 3 consecutive bearish candles
        d1 = make_candle(0, 115.0, 116.0, 110.0, 111.0, tf="D1", day=1)
        d2 = make_candle(0, 111.0, 112.0, 105.0, 106.0, tf="D1", day=2)
        d3 = make_candle(0, 106.0, 107.0, 100.0, 101.0, tf="D1", day=3)
        # Reversal candle sweeps low (100.0) to 98.0 and closes at 104.0
        d4 = make_candle(0, 101.0, 105.0, 98.0, 104.0, tf="D1", day=4)

        res = DailyMapEvaluator.evaluate([d1, d2, d3, d4])
        assert res is not None
        assert res.map_type == MapType.MAP_3_CONSECUTIVE_LEG_SWEEP
        assert res.bias == BiasDirection.BULLISH
        assert res.target_level == 116.0  # Origin high of the consecutive run


class TestSessionsAndSweeps:
    def test_asian_session_manager(self):
        mgr = AsianSessionManager()
        assert mgr.is_supported_symbol("USDJPY")
        assert mgr.is_supported_symbol("AUDJPY")
        assert mgr.is_supported_symbol("XAUUSD")
        assert not mgr.is_supported_symbol("EURUSD")

        # 01:00 UTC is inside Asian session and inside Prime window
        dt_prime = datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)
        assert mgr.is_in_asian_session(dt_prime)
        assert mgr.is_in_prime_asian_window(dt_prime)

        # 08:00 UTC is London session (outside Asian)
        dt_london = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
        assert not mgr.is_in_asian_session(dt_london)

    def test_hourly_candle_sweep(self):
        # 12:00 AM candle (23:00 UTC)
        c_12am = make_candle(23, 150.0, 152.0, 148.0, 151.0, day=1)
        # 1:00 AM candle (00:00 UTC) sweeps 148.0 to 147.0, closes at 150.5
        c_1am = make_candle(0, 151.0, 151.5, 147.0, 150.5, day=2)

        sweep = HourlySweepDetector.detect_h1_sweep([c_12am, c_1am])
        assert sweep is not None
        assert sweep.swept is True
        assert sweep.direction == BiasDirection.BULLISH
        assert sweep.sweep_price == 147.0


class TestEntryModels:
    def test_model_a_choch_retest(self):
        c_12am = make_candle(23, 150.0, 152.0, 148.0, 151.0, day=1)
        c_1am = make_candle(0, 151.0, 151.5, 147.0, 150.5, day=2)
        sweep = HourlySweepDetector.detect_h1_sweep([c_12am, c_1am])

        daily_map = DailyMapEvaluator.evaluate([
            make_candle(0, 148.0, 155.0, 145.0, 152.0, tf="D1", day=1),
            make_candle(0, 152.0, 153.0, 143.0, 150.0, tf="D1", day=2),
            make_candle(0, 150.0, 152.0, 149.0, 151.0, tf="D1", day=3),
        ])

        # M15 candles: minor high at 151.0, current M15 closes at 151.5 (CHOCH)
        m1 = make_candle(1, 149.0, 151.0, 148.0, 149.5, tf="M15")
        m2 = make_candle(2, 149.5, 150.5, 149.0, 150.0, tf="M15")
        m3 = make_candle(3, 150.0, 152.0, 149.8, 151.5, tf="M15")

        setup = EntryModelEvaluator.evaluate_entry("USDJPY", [m1, m2, m3], sweep, daily_map)
        assert setup is not None
        assert setup.entry_model == EntryModelType.MODEL_A_CHOCH_RETEST
        assert setup.bias == BiasDirection.BULLISH
        assert setup.stop_loss < 147.0
        assert setup.risk_reward > 0.0


class TestUnifiedEngine:
    def test_end_to_end_scan(self):
        engine = FZASMEngine()

        # Build multi-timeframe candles
        d1 = [
            make_candle(0, 140.0, 155.0, 138.0, 152.0, tf="D1", day=1),
            make_candle(0, 152.0, 153.0, 146.0, 150.0, tf="D1", day=2),
            make_candle(0, 150.0, 152.0, 149.0, 151.0, tf="D1", day=3),
        ]
        h4 = [
            make_candle(0, 146.0, 151.0, 145.0, 150.0, tf="H4"),
            make_candle(4, 150.0, 152.0, 149.0, 151.0, tf="H4")
        ]
        h1 = [
            make_candle(23, 150.0, 152.0, 148.0, 151.0, tf="H1", day=1),
            make_candle(0, 151.0, 151.5, 147.0, 150.5, tf="H1", day=2)
        ]
        m15 = [
            make_candle(1, 149.0, 151.0, 148.0, 149.5, tf="M15"),
            make_candle(2, 149.5, 150.5, 149.0, 150.0, tf="M15"),
            make_candle(3, 150.0, 152.0, 149.8, 151.5, tf="M15")
        ]

        setup = engine.scan_asset(
            symbol="USDJPY",
            candles_by_tf={"D1": d1, "H4": h4, "H1": h1, "M15": m15},
            force_session=True
        )
        assert setup is not None
        assert setup.symbol == "USDJPY"
        assert setup.bias == BiasDirection.BULLISH
        assert setup.entry_model == EntryModelType.MODEL_A_CHOCH_RETEST

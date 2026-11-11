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

    def test_open_close_levels(self):
        c1 = make_candle(1, 100.0, 101.0, 99.8, 100.2)  # small body 0.2
        c2 = make_candle(2, 100.2, 101.0, 100.0, 100.4) # small body 0.2
        c3 = make_candle(3, 100.4, 110.0, 100.0, 109.0) # large expansion body 8.6
        levels = KeyLevelDetector.detect_open_close_levels([c1, c2, c3], timeframe="H1")
        assert len(levels) >= 1
        assert levels[-1].level_type == LevelType.OPEN_CLOSE
        assert levels[-1].price_top == 109.0
        assert levels[-1].price_bottom == 100.4


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

    def test_map_1_structural_range(self):
        # 5 candles showing structural expansion
        c1 = make_candle(0, 100.0, 105.0, 99.0, 102.0, tf="D1", day=1)
        c2 = make_candle(0, 102.0, 106.0, 101.0, 104.0, tf="D1", day=2)
        c3 = make_candle(0, 104.0, 107.0, 103.0, 105.0, tf="D1", day=3)
        c4 = make_candle(0, 105.0, 108.0, 104.0, 106.0, tf="D1", day=4)
        c5 = make_candle(0, 106.0, 112.0, 105.0, 111.0, tf="D1", day=5)
        res = DailyMapEvaluator.evaluate([c1, c2, c3, c4, c5])
        assert res is not None
        assert res.map_type == MapType.MAP_1_STRUCTURAL_RANGE
        assert res.bias == BiasDirection.BULLISH

    def test_map_4_crt_poi_confluence(self):
        poi = KeyLevel(
            level_type=LevelType.ORDER_BLOCK,
            direction=BiasDirection.BULLISH,
            price_top=96.0,
            price_bottom=92.0,
            timestamp=datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
            timeframe="D1"
        )
        d1 = make_candle(0, 100.0, 110.0, 95.0, 105.0, tf="D1", day=1)
        # d2 sweeps d1 low into POI (tested between 92 and 96) and closes at 101.0 back inside
        d2 = make_candle(0, 105.0, 106.0, 93.0, 101.0, tf="D1", day=2)
        d3 = make_candle(0, 101.0, 103.0, 100.0, 102.0, tf="D1", day=3)
        res = DailyMapEvaluator.evaluate([d1, d2, d3], structural_poi=poi)
        assert res is not None
        assert res.map_type == MapType.MAP_4_CRT_POI_CONFLUENCE
        assert res.bias == BiasDirection.BULLISH

    def test_map_5a_rejection(self):
        poi = KeyLevel(
            level_type=LevelType.ORDER_BLOCK,
            direction=BiasDirection.BULLISH,
            price_top=100.0,
            price_bottom=95.0,
            timestamp=datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
            timeframe="D1"
        )
        d1 = make_candle(0, 105.0, 108.0, 102.0, 104.0, tf="D1", day=1)
        d2 = make_candle(0, 104.0, 105.0, 101.0, 102.0, tf="D1", day=2)
        # d3 enters POI, doesn't sweep below 95.0, closes bullish with large lower wick
        # open=97.0, low=96.0, high=101.0, close=100.0 -> body=3.0, lower_wick=1.0. We need lower_wick > body*0.5
        d3 = make_candle(0, 98.0, 101.0, 95.5, 99.0, tf="D1", day=3) # body=1.0, lower_wick=2.5 > 0.5
        res = DailyMapEvaluator.evaluate([d1, d2, d3], structural_poi=poi)
        assert res is not None
        assert res.map_type == MapType.MAP_5A_REJECTION
        assert res.bias == BiasDirection.BULLISH

    def test_map_5b_sweep_invalidation(self):
        poi = KeyLevel(
            level_type=LevelType.ORDER_BLOCK,
            direction=BiasDirection.BULLISH,
            price_top=100.0,
            price_bottom=95.0,
            timestamp=datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
            timeframe="D1"
        )
        d1 = make_candle(0, 105.0, 108.0, 102.0, 104.0, tf="D1", day=1)
        d2 = make_candle(0, 104.0, 105.0, 101.0, 103.0, tf="D1", day=2)
        # d3 pierces below 95.0 to 93.0, closes at 96.0 back above 95.0
        d3 = make_candle(0, 103.0, 104.0, 93.0, 96.0, tf="D1", day=3)
        res = DailyMapEvaluator.evaluate([d1, d2, d3], structural_poi=poi)
        assert res is not None
        assert res.map_type == MapType.MAP_5B_SWEEP_INVALIDATION
        assert res.bias == BiasDirection.BULLISH


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

    def test_h2_fallback_sweep(self):
        # 2-hour candles
        c_h2_prev = make_candle(22, 150.0, 152.0, 148.0, 151.0, tf="H2", day=1)
        c_h2_curr = make_candle(0, 151.0, 151.5, 147.0, 150.5, tf="H2", day=2)
        sweep = HourlySweepDetector.detect_h2_sweep_fallback([c_h2_prev, c_h2_curr])
        assert sweep is not None
        assert sweep.swept is True
        assert sweep.direction == BiasDirection.BULLISH


class TestEdgeCasesAndSafety:
    def test_edge_cases_empty_and_short_arrays(self):
        assert DailyMapEvaluator.evaluate([]) is None
        c1 = make_candle(0, 100.0, 105.0, 99.0, 102.0)
        assert DailyMapEvaluator.evaluate([c1]) is None

        assert KeyLevelDetector.detect_order_blocks([]) == []
        assert KeyLevelDetector.detect_order_blocks([c1]) == []
        assert KeyLevelDetector.detect_breaker_blocks([], []) == []
        assert KeyLevelDetector.detect_open_close_levels([]) == []
        assert KeyLevelDetector.detect_open_close_levels([c1]) == []
        assert KeyLevelDetector.detect_power_unit_engulfing([]) is None
        assert KeyLevelDetector.detect_power_unit_engulfing([c1]) is None

        assert HourlySweepDetector.detect_h1_sweep([]) is None
        assert HourlySweepDetector.detect_h1_sweep([c1]) is None

        engine = FZASMEngine()
        assert engine.scan_asset("USDJPY", {}) is None
        assert engine.scan_asset("EURUSD", {"D1": [c1]}) is None

    def test_edge_cases_flat_and_zero_body_candles(self):
        c_flat1 = make_candle(1, 100.0, 100.0, 100.0, 100.0)
        c_flat2 = make_candle(2, 100.0, 100.0, 100.0, 100.0)
        assert c_flat1.is_doji
        assert c_flat1.body_size == 0.0
        assert c_flat1.total_range == 0.0

        # Should safely return empty list without ZeroDivisionError
        levels = KeyLevelDetector.detect_open_close_levels([c_flat1, c_flat2])
        assert levels == []

    def test_edge_cases_dual_sweep_direction_resolution(self):
        # Prev candle: high 150.0, low 148.0
        prev = make_candle(23, 149.0, 150.0, 148.0, 149.5, day=1)

        # Bullish outside candle: sweeps low to 147.0 and high to 151.0, but closes near top at 150.8 (bullish)
        c_bull = make_candle(0, 148.5, 151.0, 147.0, 150.8, day=2)
        res_bull = HourlySweepDetector.detect_h1_sweep([prev, c_bull])
        assert res_bull is None

        # Bearish outside candle: sweeps low to 147.0 and high to 151.0, but closes near bottom at 147.5 (bearish)
        c_bear = make_candle(0, 150.5, 151.0, 147.0, 147.5, day=2)
        res_bear = HourlySweepDetector.detect_h1_sweep([prev, c_bear])
        assert res_bear is None

        # Ambiguous outside doji: closes at open
        c_doji = make_candle(0, 149.0, 151.0, 147.0, 149.0, day=2)
        res_doji = HourlySweepDetector.detect_h1_sweep([prev, c_doji])
        assert res_doji is None

    def test_edge_cases_symbol_parsing_variations(self):
        mgr = AsianSessionManager()
        assert mgr.is_supported_symbol("USDJPY")
        assert mgr.is_supported_symbol("usdjpy")
        assert mgr.is_supported_symbol("USD/JPY")
        assert mgr.is_supported_symbol("GBPJPY.pro")
        assert mgr.is_supported_symbol("XAUUSD-raw")
        assert mgr.is_supported_symbol("gold")
        assert mgr.is_supported_symbol("JP225")

        assert not mgr.is_supported_symbol("EURUSD")
        assert not mgr.is_supported_symbol("BTCUSD")
        assert not mgr.is_supported_symbol("")
        assert not mgr.is_supported_symbol(None)

    def test_edge_cases_key_level_inverted_bounds(self):
        # Inverted price bounds should be auto-corrected in __post_init__
        lvl = KeyLevel(
            level_type=LevelType.ORDER_BLOCK,
            direction=BiasDirection.BULLISH,
            price_top=90.0,
            price_bottom=100.0,
            timestamp=datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
            timeframe="H4"
        )
        assert lvl.price_bottom == 90.0
        assert lvl.price_top == 100.0
        assert lvl.contains(95.0)

    def test_edge_cases_session_boundaries(self):
        mgr = AsianSessionManager()
        # 23:59 UTC: outside
        dt_before = datetime(2026, 11, 1, 23, 59, tzinfo=timezone.utc)
        assert not mgr.is_in_asian_session(dt_before)

        # 00:00 UTC (1:00 AM WAT): in Asian session & Prime window
        dt_open = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)
        assert mgr.is_in_asian_session(dt_open)
        assert mgr.is_in_prime_asian_window(dt_open)

        # 01:59 UTC: inside Asian session & Prime window
        dt_prime = datetime(2026, 11, 2, 1, 59, tzinfo=timezone.utc)
        assert mgr.is_in_asian_session(dt_prime)
        assert mgr.is_in_prime_asian_window(dt_prime)

        # 05:59 UTC: inside Asian session
        dt_late = datetime(2026, 11, 2, 5, 59, tzinfo=timezone.utc)
        assert mgr.is_in_asian_session(dt_late)

        # 06:00 UTC: outside Asian session
        dt_close = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
        assert not mgr.is_in_asian_session(dt_close)

    def test_edge_cases_breaker_mitigation_lifecycle(self):
        ob = KeyLevel(
            level_type=LevelType.ORDER_BLOCK,
            direction=BiasDirection.BULLISH,
            price_top=100.0,
            price_bottom=95.0,
            timestamp=datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc),
            timeframe="H4"
        )
        c_break = make_candle(5, 98.0, 99.0, 92.0, 93.0)
        c_later = make_candle(6, 93.0, 94.0, 90.0, 91.0)

        # Breaking candle should flip OB to breaker and mark OB mitigated
        breakers = KeyLevelDetector.detect_breaker_blocks([c_break, c_later], [ob])
        assert len(breakers) == 1
        assert ob.mitigated is True

"""
FZ-ASM Data Types and Core Domain Models.
Strictly typed dataclasses representing candles, swings, key levels, maps, and trade setups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Tuple


class TimeFrame(str, Enum):
    W1 = "W1"
    D1 = "D1"
    H4 = "H4"
    H2 = "H2"
    H1 = "H1"
    M15 = "M15"
    M10 = "M10"
    M5 = "M5"
    M1 = "M1"


class BiasDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class MapType(str, Enum):
    MAP_1_STRUCTURAL_RANGE = "MAP_1_STRUCTURAL_RANGE"
    MAP_2_CANDLE_RANGE_CRT = "MAP_2_CANDLE_RANGE_CRT"
    MAP_3_CONSECUTIVE_LEG_SWEEP = "MAP_3_CONSECUTIVE_LEG_SWEEP"
    MAP_4_CRT_POI_CONFLUENCE = "MAP_4_CRT_POI_CONFLUENCE"
    MAP_5A_REJECTION = "MAP_5A_REJECTION"
    MAP_5B_SWEEP_INVALIDATION = "MAP_5B_SWEEP_INVALIDATION"


class LevelType(str, Enum):
    ORDER_BLOCK = "ORDER_BLOCK"
    BREAKER_BLOCK = "BREAKER_BLOCK"
    OPEN_CLOSE = "OPEN_CLOSE"
    FAIR_VALUE_GAP = "FAIR_VALUE_GAP"
    INDUCEMENT = "INDUCEMENT"


class EntryModelType(str, Enum):
    MODEL_A_CHOCH_RETEST = "MODEL_A_CHOCH_RETEST"
    MODEL_B_INDUCEMENT_LIMIT = "MODEL_B_INDUCEMENT_LIMIT"


@dataclass(frozen=True)
class Candle:
    """Represents a discrete OHLC bar."""
    timestamp: datetime  # UTC timestamp of bar open
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    timeframe: str = "H1"
    close_time: Optional[datetime] = None

    @property
    def available_at(self) -> datetime:
        if self.close_time is not None:
            return self.close_time
        minutes = {"M1": 1, "M5": 5, "M10": 10, "M15": 15,
                   "H1": 60, "H2": 120, "H4": 240, "D1": 1440, "W1": 10080}
        return self.timestamp + timedelta(minutes=minutes[self.timeframe])

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def is_doji(self) -> bool:
        return self.close == self.open

    @property
    def body_high(self) -> float:
        return max(self.open, self.close)

    @property
    def body_low(self) -> float:
        return min(self.open, self.close)

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def total_range(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        return self.high - self.body_high

    @property
    def lower_wick(self) -> float:
        return self.body_low - self.low

    def is_engulfing(self, previous: Candle) -> bool:
        """
        FZ's Power Unit:
        Bullish engulfing: current candle body engulfs previous candle body and is bullish.
        Bearish engulfing: current candle body engulfs previous candle body and is bearish.
        """
        if self.is_bullish:
            return self.body_low <= previous.body_low and self.body_high >= previous.body_high and self.close > previous.high
        elif self.is_bearish:
            return self.body_high >= previous.body_high and self.body_low <= previous.body_low and self.close < previous.low
        return False


@dataclass
class KeyLevel:
    """Represents a structural or candlestick price level of interest (POI)."""
    level_type: LevelType
    direction: BiasDirection  # BULLISH (support) or BEARISH (resistance)
    price_top: float
    price_bottom: float
    timestamp: datetime
    timeframe: str
    mitigated: bool = False
    source_candle: Optional[Candle] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        # Guarantee price_bottom <= price_top
        if self.price_bottom > self.price_top:
            self.price_bottom, self.price_top = self.price_top, self.price_bottom

    @property
    def mid_price(self) -> float:
        return (self.price_top + self.price_bottom) / 2.0

    def contains(self, price: float) -> bool:
        return self.price_bottom <= price <= self.price_top

    def is_tested_by(self, candle: Candle) -> bool:
        """Checks if a candle penetrates or touches the zone."""
        return not (candle.low > self.price_top or candle.high < self.price_bottom)


@dataclass
class DailyMapResult:
    """The HTF Directional Bias output from the 5 Daily Maps."""
    map_type: MapType
    bias: BiasDirection
    origin_level: float   # Where market is coming FROM
    target_level: float   # Where market is going TO
    equilibrium_50: float
    confidence: float
    notes: str
    timestamp: datetime
    reference_candles: List[Candle] = field(default_factory=list)


@dataclass
class SessionWindow:
    """Defines time windows for trading sessions in UTC."""
    name: str = "Asian"
    start_hour_utc: int = 0   # 00:00 UTC (1:00 AM Nigeria/WAT)
    end_hour_utc: int = 6     # 06:00 UTC (7:00 AM Nigeria/WAT)
    prime_start_hour_utc: int = 0 # 00:00 UTC
    prime_end_hour_utc: int = 2   # 02:00 UTC (3:00 AM Nigeria/WAT)

    def is_in_session(self, dt: datetime) -> bool:
        return self.start_hour_utc <= dt.hour < self.end_hour_utc

    def is_in_prime_window(self, dt: datetime) -> bool:
        return self.prime_start_hour_utc <= dt.hour <= self.prime_end_hour_utc


@dataclass
class HourlySweepResult:
    """Details of an H1 / H2 session candle sweep."""
    swept: bool
    direction: BiasDirection  # BULLISH (swept low, rejected upward) or BEARISH (swept high, rejected downward)
    sweep_candle: Candle
    swept_candle: Candle
    sweep_price: float
    key_level_tested: Optional[KeyLevel] = None
    notes: str = ""


@dataclass
class TradeSetup:
    """Complete quantified trade setup ready for execution or notification."""
    symbol: str
    timestamp: datetime
    bias: BiasDirection
    entry_model: EntryModelType
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward: float
    daily_map: DailyMapResult
    h1_sweep: HourlySweepResult
    timeframe: str = "M15"
    key_level: Optional[KeyLevel] = None
    notes: str = ""

    stop_variant: str = "hourly_sweep"
    stop_candidates: dict = field(default_factory=dict)
    entry_evidence: dict = field(default_factory=dict)

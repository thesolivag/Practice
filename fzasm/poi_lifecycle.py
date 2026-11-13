"""Opt-in research lifecycle: closed-bar availability and terminal invalidation.

A close beyond the far zone edge retires it; a wick or equality does not.
No automatic polarity flip/reclaim is invented for open-close zones.
"""
from dataclasses import replace
from .types import BiasDirection,LevelType


def apply_lifecycle(levels,candles):
    result=[]
    for level in levels:
        known=level.timestamp
        if level.level_type==LevelType.OPEN_CLOSE and level.source_candle:
            known=max(known,level.source_candle.available_at)
        elif level.level_type==LevelType.BREAKER_BLOCK:
            # Legacy detector stores the breaking candle's open timestamp.
            origin=next((c for c in candles if c.timestamp==level.timestamp),None)
            if origin:known=origin.available_at
        broken=next((c for c in candles if c.timestamp>=known and
            (c.close<level.price_bottom if level.direction==BiasDirection.BULLISH
             else c.close>level.price_top)),None)
        metadata=dict(level.metadata,available_at=known.isoformat(),
            lifecycle_rule='closed_bar_beyond_far_edge',
            invalidated_at=broken.available_at.isoformat() if broken else None,
            invalidating_close=broken.close if broken else None)
        result.append(replace(level,timestamp=known,mitigated=level.mitigated or broken is not None,metadata=metadata))
    return result

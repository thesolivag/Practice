"""Review all opposing departure candles; never select using later outcomes.

These are order-block CANDIDATES, not a validated violation-block classifier.
Only a close beyond the candidate's full range validates a departure here.
"""
from .types import BiasDirection


def block_candidates(candles, sweep, now):
    from .recognition import recognize_retests
    events = recognize_retests(candles, sweep, now)
    if not events:
        return []
    context = events[0]
    bars = sorted((c for c in candles if c.available_at <= now), key=lambda c: c.timestamp)
    long = sweep.direction == BiasDirection.BULLISH
    start = context['sweep_extreme_time']
    end = context['break_time']
    leg = [c for c in bars if c.timestamp.isoformat() >= start and c.available_at.isoformat() <= end]
    result = []
    for index, c in enumerate(leg):
        if not (c.is_bearish if long else c.is_bullish):
            continue
        departure = next((b for b in leg[index + 1:] if (b.close > c.high if long else b.close < c.low)), None)
        if departure is None:
            continue
        result.append(dict(origin_time=c.timestamp.isoformat(),
                           departure_confirmed_at=departure.available_at.isoformat(),
                           actionable_at=context['context_available_at'],
                           role='sweep_origin_candidate' if c.timestamp.isoformat() == start else 'secondary_candidate',
                           classification='unvalidated_order_block_candidate',
                           zone_low=c.low if long else c.body_low,
                           zone_high=c.body_high if long else c.high,
                           entry=c.body_high if long else c.body_low))
    return result

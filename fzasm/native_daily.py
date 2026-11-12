"""Broker-native D1 bars with conservative, explicit availability.

Native OHLC is never reconstructed or gap-filled from M1. In the absence of a
provider's explicit ``closed_at``, a D1 candle is usable only at the next native
D1 open. Expected weekend adjacencies (at most 74h, Thu/Fri to Sun/Mon)
remain available only at that next open, deliberately delaying Friday data.
Other gaps over 26h are omitted and flagged for consumers to reject.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from .types import Candle


def _utc(value, label):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError(f'{label} must be an aware UTC timestamp')
    return stamp.tz_convert('UTC')


def candles_from_native_daily(df: pd.DataFrame, as_of):
    """Return ``(closed_candles, audit)`` for validated native D1 OHLC.

    ``df`` needs an ordered, unique UTC DatetimeIndex and open/high/low/close.
    Optional per-row ``closed_at`` must be a provider-supplied UTC close time,
    not a timestamp invented by the caller. A last candle without it is omitted.
    The returned Candle.close_time always explicitly records availability.
    Consumers must reject nonempty audit['missing_weekday_gaps'] rather than
    treating omitted weekdays as adjacent daily candles. Expected weekends are
    retained but conservatively delayed until the next native open.
    """
    cutoff = _utc(as_of, 'as_of')
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
        raise ValueError('Native D1 index must be an aware UTC DatetimeIndex')
    if df.index.hasnans or df.index.has_duplicates or not df.index.is_monotonic_increasing:
        raise ValueError('Native D1 opens must be finite, unique and ordered')
    if any(t.utcoffset().total_seconds() != 0 for t in df.index):
        raise ValueError('Native D1 index must use UTC timestamps')
    required = ('open', 'high', 'low', 'close')
    if not set(required).issubset(df.columns):
        raise ValueError('Native D1 requires open/high/low/close')
    try:
        values = df.loc[:, required].astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError('Native D1 OHLC must be numeric') from exc
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError('Native D1 OHLC must be finite')
    if ((values.low > values.min(axis=1)) | (values.high < values.max(axis=1))).any():
        raise ValueError('Native D1 OHLC bounds are invalid')

    candles = []
    audit = dict(source='broker_native_D1', as_of=cutoff.isoformat(), rows=len(df),
                 availability='explicit provider closed_at or next native D1 open; no assumed 24h',
                 omitted_future_or_unclosed=0, omitted_last_without_close=0,
                 omitted_gap_rows=0, gaps=[], missing_weekday_gaps=[],
                 weekend_delayed_rows=0, admitted=0)
    opens = df.index.tz_convert('UTC')
    for i, opened in enumerate(opens):
        following = opens[i + 1] if i + 1 < len(opens) else None
        raw_closed = df.iloc[i].get('closed_at', None)
        explicit = raw_closed is not None and not pd.isna(raw_closed)
        gap_hours = (following - opened).total_seconds() / 3600 if following is not None else None
        weekend_gap = bool(gap_hours is not None and 26 < gap_hours <= 74
                           and opened.weekday() in (3, 4)
                           and following.weekday() in (6, 0))
        if gap_hours is not None and gap_hours > 26:
            gap = dict(open=opened.isoformat(), next_open=following.isoformat(),
                gap_hours=gap_hours, spans_utc_weekend=any(t.weekday() >= 5 for t in
                    pd.date_range(opened.floor('D'), following.floor('D'), freq='D')),
                classification='expected_weekend' if weekend_gap else 'missing_weekday_or_unverified_gap',
                omitted=not explicit and not weekend_gap)
            audit['gaps'].append(gap)
            if not weekend_gap:
                audit['missing_weekday_gaps'].append(gap.copy())
        if explicit:
            available = _utc(raw_closed, 'closed_at')
            if available <= opened or (following is not None and available > following):
                raise ValueError('Native D1 closed_at must follow open and not overlap next open')
        elif following is None:
            audit['omitted_last_without_close'] += 1
            continue
        elif gap_hours > 26 and not weekend_gap:
            audit['omitted_gap_rows'] += 1
            continue
        else:
            available = following
        if available > cutoff:
            audit['omitted_future_or_unclosed'] += 1
            continue
        if weekend_gap and not explicit:
            audit['weekend_delayed_rows'] += 1
        row = values.iloc[i]
        candles.append(Candle(timestamp=opened.to_pydatetime(),
                              open=float(row.open), high=float(row.high),
                              low=float(row.low), close=float(row.close),
                              timeframe='D1', close_time=available.to_pydatetime()))
    audit['admitted'] = len(candles)
    return candles, audit

"""Bounded broker data for manually requested alert watches.

Provider connections are shared only inside a single scanner invocation. Minute
bars are ephemeral; existing hourly files remain incremental and provider tagged.
"""
from contextlib import ExitStack
import math
import time

import numpy as np
import pandas as pd
from . import candles, instruments, store

COLS = ['open', 'high', 'low', 'close']
TF_MINUTES = {'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30, 'M45': 45,
              'H1': 60, 'H2': 120, 'H3': 180, 'H4': 240}
MAX_PAIRS = 8
_HOURLY_CHECKS = {}  # bounded process-local refresh marker, not a durable candle store


def _empty(grain=60):
    frame = pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([], tz='UTC', name='t'))
    frame.attrs['granularity'] = grain
    return frame


def _validated(frame, grain, now, lo=None):
    if frame is None or frame.empty:
        return _empty(grain)
    frame = frame[COLS].copy()
    # pandas3 preserves/infer seconds or microseconds; integer epoch arithmetic
    # below must use a declared unit, independent of the provider/index factory.
    frame.index = pd.to_datetime(frame.index, utc=True).as_unit("ns")
    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep='last')]
    closed = (frame.index.asi8 % (grain * 10**9) == 0) & (frame.index + pd.Timedelta(seconds=grain) <= now)
    if lo is not None:
        closed &= frame.index >= lo
    frame = frame[closed].astype(float)
    if not frame.empty:
        values = frame.to_numpy()
        valid = np.isfinite(values).all() and (values > 0).all()
        valid = valid and (frame.low <= frame[['open', 'close']].min(axis=1)).all()
        valid = valid and (frame.high >= frame[['open', 'close']].max(axis=1)).all()
        if not valid:
            raise ValueError('Invalid broker candle values')
    frame.attrs['granularity'] = grain
    return frame


def _utc_wall(value, deriv):
    if deriv:
        return value.tz_localize('UTC')
    return (value - pd.Timedelta(hours=7)).tz_localize('America/New_York', ambiguous='raise', nonexistent='raise').tz_convert('UTC')


def complete_bars(frame, tf, pair, now):
    """Only complete, gap-free bars using the provider's nominal calendar edges.

    H1 source may aggregate to H1/H2/H3/H4/D/W, but never fabricate minutes.
    A missing component invalidates its entire aggregate, including leading and
    trailing partial bars. This intentionally favors missed alerts over false ones.
    """
    if tf not in TF_MINUTES and tf not in ('D', 'W'):
        raise ValueError('Unsupported alert timeframe')
    result_cols = COLS + ['start', 'end']
    if frame is None or frame.empty:
        return pd.DataFrame(columns=result_cols)
    grain = int(frame.attrs.get('granularity', 3600))
    if grain not in (60, 3600):
        raise ValueError('Unsupported source candle interval')
    if tf in TF_MINUTES and TF_MINUTES[tf] * 60 < grain:
        raise ValueError('Finer source candles are required')
    now = store._utc(now)
    source = _validated(frame, grain, now)
    if source.empty:
        return pd.DataFrame(columns=result_cols)
    dv = instruments.is_deriv(pair)
    with candles.market(pair):
        local = candles.wall_time(source.index)
    if tf == 'D':
        keys = local.floor('D')
    elif tf == 'W':
        days = local.floor('D')
        keys = days - pd.to_timedelta(days.dayofweek, unit='D')
    else:
        keys = local.floor(f'{TF_MINUTES[tf]}min')
    rows = []
    for key, group in source.groupby(keys):
        try:
            start = _utc_wall(key, dv)
            delta = pd.Timedelta(days=(7 if dv else 5) if tf == 'W' else 1) if tf in ('D', 'W') else pd.Timedelta(minutes=TF_MINUTES[tf])
            end = _utc_wall(key + delta, dv)
        except Exception:
            # pandas timezone backends use differing ambiguity exception classes.
            # OHLC validation happens above; only nominal-edge conversion is skipped.
            continue
        if end > now or start >= end:
            continue
        group = group[(group.index >= start) & (group.index < end)]
        expected = pd.date_range(start, end, freq=pd.Timedelta(seconds=grain), inclusive='left').as_unit('ns')
        if len(group) != len(expected) or not group.index.equals(expected):
            continue
        rows.append(dict(open=float(group.open.iat[0]), high=float(group.high.max()),
                         low=float(group.low.min()), close=float(group.close.iat[-1]), start=start, end=end))
    return pd.DataFrame(rows, columns=result_cols)


def _open_ctrader():
    # Use the established strict token persistence and broker connection path.
    return store._open_client()


def _budget(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError('Alert data budget elapsed')


def _deriv_minutes(feed, pair, now, deadline, minutes=24 * 60):
    end = int(now.floor('min').timestamp())
    begin = end - int(minutes) * 60
    rows = []
    for start in range(begin, end, 720 * 60):
        _budget(deadline)
        hi = min(end, start + 720 * 60)
        reply = feed.request({'ticks_history': feed.info(pair)['symbol'], 'start': start,
                              'end': str(hi - 1), 'style': 'candles', 'granularity': 60,
                              'count': (hi - start) // 60})
        values = reply.get('candles')
        if not isinstance(values, list) or len(values) > 5000:
            raise ValueError('Invalid Deriv minute response')
        for item in values:
            epoch = int(item['epoch'])
            if start <= epoch < hi:
                rows.append((epoch, *(float(item[k]) for k in COLS)))
    if not rows:
        return _empty()
    frame = pd.DataFrame(rows, columns=['epoch', *COLS]).set_index('epoch')
    frame.index = pd.to_datetime(frame.index, unit='s', utc=True)
    return _validated(frame, 60, now, pd.Timestamp(begin, unit='s', tz='UTC'))


def _deriv_quote(feed, pair):
    reply = feed.request({'ticks_history': feed.info(pair)['symbol'], 'end': 'latest', 'count': 1, 'style': 'ticks'})
    history = reply.get('history') or {}
    prices, times = history.get('prices') or [], history.get('times') or []
    if not prices or len(prices) != len(times):
        return None, None
    price, stamp = float(prices[-1]), int(times[-1])
    if not math.isfinite(price) or price <= 0:
        raise ValueError('Invalid Deriv quote')
    return price, stamp


def _requested(pair, requirements):
    if requirements is None:
        return dict(hourly=True, minutes=24 * 60, quote=True, days=30)
    raw = requirements.get(pair, {})
    tfs = set(raw.get('primary_timeframes', raw.get('timeframes', [])))
    if tfs - (set(TF_MINUTES) | {'D', 'W'}):
        raise ValueError('Unsupported requested alert timeframe')
    intraday = tfs & set(TF_MINUTES)
    # Ten full bars bound confirmation context and provide completed swing neighbours.
    # One extra parent interval covers a partial first/last bar at fetch time.
    minutes = max((TF_MINUTES[tf] * 11 for tf in intraday), default=0)
    return dict(hourly=bool(tfs & {'D', 'W'}), minutes=minutes,
                quote=bool(raw.get('quote', False)), days=80 if 'W' in tfs else 30)


def _cached_hours(pair, kind, now, days):
    cached = store.Pair(pair)
    if cached.src != kind:
        return _empty(3600)
    return _validated(cached.frame(lo=int((now - pd.Timedelta(days=days + 5)).timestamp())), 3600, now)


def _hours_ready(frame, now, days):
    if frame.empty:
        return False
    return (frame.index[-1] + pd.Timedelta(hours=1) >= now.floor('h')
            and frame.index[0] <= now - pd.Timedelta(days=days))


def load(pairs, now, deadline=None, requirements=None, max_pairs=None):
    """Fetch exactly the watch requirements, using shared provider connections.

    Without requirements the historical full-probe behavior is retained. Minute
    checks may pass a short deadline and pair cap. Quote-only watches never read
    or download historical candles. D/W use incremental H1 files and one refresh
    attempt per source/hour; intraday models request only their bounded context.
    No provider fallback is permitted. In-flight SDK calls retain their timeout.
    """
    now = store._utc(now)
    deadline = deadline if deadline is not None else time.monotonic() + 180
    limit = MAX_PAIRS if max_pairs is None else max(1, min(MAX_PAIRS, int(max_pairs)))
    selected = list(dict.fromkeys(str(p).upper() for p in pairs))
    out = {p: dict(frame=_empty(), hourly=_empty(3600), quote=None, quote_time=None, error=None) for p in selected}
    connections, failures = {}, {}
    with ExitStack() as stack:
        for position, pair in enumerate(selected):
            result = out[pair]
            if position >= limit or time.monotonic() >= deadline:
                result['error'] = 'Alert data budget reached; deferred until next scan'
                continue
            kind = 'deriv' if instruments.is_deriv(pair) else 'ctrader'
            try:
                need = _requested(pair, requirements)
            except Exception as exc:
                result['error'] = store._safe(exc)
                continue
            hourly_update = False
            hour_key = (kind, pair, need['days'], str(store.DIR))
            closed_hour = int(now.floor('h').timestamp())
            if need['hourly']:
                try:
                    result['hourly'] = _cached_hours(pair, kind, now, need['days'])
                except Exception as exc:
                    result['error'] = store._safe(exc)
                hourly_update = requirements is None or (not _hours_ready(result['hourly'], now, need['days'])
                    and _HOURLY_CHECKS.get(hour_key) != closed_hour)
            if not (hourly_update or need['minutes'] or need['quote']):
                continue
            try:
                if kind in failures:
                    raise RuntimeError(failures[kind])
                if kind not in connections:
                    try:
                        _budget(deadline)
                        if kind == 'deriv':
                            from .deriv import Feed
                            feed = stack.enter_context(Feed(deadline=deadline))
                            # Load the shared catalogue without validating the whole
                            # watchlist: one delisted symbol must not poison this
                            # provider connection for other users' valid symbols.
                            feed.prefetch()
                            connections[kind] = feed
                        else:
                            client = _open_ctrader()
                            stack.callback(client.close)
                            client.timeout = max(1, min(8, deadline - time.monotonic()))
                            client.get_symbols([p for p in selected[:limit] if not instruments.is_deriv(p)])
                            connections[kind] = store.CTraderFeed(client)
                    except Exception as exc:
                        failures[kind] = store._safe(exc)
                        raise
            except Exception as exc:
                result['error'] = result['error'] or store._safe(exc)
                continue
            feed = connections[kind]
            if kind == 'deriv':
                try:
                    feed.info(pair)
                except Exception as exc:
                    result['error'] = result['error'] or store._safe(exc)
                    continue
            # Sample quotes before potentially longer historical downloads.
            if need['quote']:
                try:
                    _budget(deadline)
                    if kind == 'deriv':
                        result['quote'], result['quote_time'] = _deriv_quote(feed, pair)
                    elif not store.fx_closed(now) or instruments.market_category(pair) == 'Cryptocurrencies':
                        bid, _ = feed.c.get_spot(pair, timeout=max(1, min(8, deadline - time.monotonic())))
                        price = float(bid)
                        if not math.isfinite(price) or price <= 0:
                            raise ValueError('Invalid IC Markets quote')
                        result['quote'], result['quote_time'] = price, int(time.time())
                except Exception as exc:
                    result['error'] = result['error'] or store._safe(exc)
            if hourly_update:
                try:
                    _budget(deadline)
                    if kind == 'ctrader':
                        feed.c.timeout = max(1, min(8, deadline - time.monotonic()))
                    store.update(pair, now, days=need['days'], source=kind, feed=feed)
                    result['hourly'] = _cached_hours(pair, kind, now, need['days'])
                    # Do not suppress the next minute's retry when a provider
                    # has not yet published the latest closed H1 at the boundary.
                    if (not result['hourly'].empty
                            and result['hourly'].index[-1] + pd.Timedelta(hours=1) >= now.floor('h')):
                        if len(_HOURLY_CHECKS) >= 128:
                            _HOURLY_CHECKS.pop(next(iter(_HOURLY_CHECKS)))
                        _HOURLY_CHECKS[hour_key] = closed_hour
                except Exception as exc:
                    result['error'] = result['error'] or store._safe(exc)
            if need['minutes']:
                try:
                    _budget(deadline)
                    if kind == 'deriv':
                        result['frame'] = _deriv_minutes(feed, pair, now, deadline, minutes=need['minutes'])
                    else:
                        feed.c.timeout = max(1, min(8, deadline - time.monotonic()))
                        start = now.floor('min') - pd.Timedelta(minutes=need['minutes'])
                        result['frame'] = _validated(feed.c.get_trendbars(pair, 'M1',
                            start.to_pydatetime(), now.floor('min').to_pydatetime()), 60, now, start)
                except Exception as exc:
                    result['error'] = result['error'] or store._safe(exc)
    return out

"""Shared, bounded quote preview; never substitutes candle closes for quotes."""
from collections import OrderedDict, deque
from datetime import datetime, timezone
import threading
import time
from slk import alert_data, instruments, user_alerts

_CACHE = OrderedDict()
_ATTEMPTS = deque()
_LOCK = threading.Lock()
TTL = 60
MAX_CACHE = 128
MAX_REQUESTS_PER_MINUTE = 12


def _unavailable(pair, reason='Broker quote unavailable; try again shortly.'):
    return dict(pair=pair, available=False, fresh=False, price=None, quote_time=None, timestamp=None,
                source='Deriv' if instruments.is_deriv(pair) else 'IC Markets',
                reason=reason, refresh_after=TTL)


def _fetch(pair):
    # Use the same cross-process lease as personal checks. Never overlap an
    # active scanner connection or wait in a queue behind it.
    from slk import db, jobs
    with jobs.feed_lock(db, 0, name='slk_personal_feed') as acquired:
        if not acquired:
            return {}
        return alert_data.load([pair], datetime.now(timezone.utc),
            deadline=time.monotonic()+10, max_pairs=1,
            requirements={pair: {'quote': True, 'timeframes': []}}).get(pair, {})


def preview(pair):
    pair = str(pair).strip().upper()
    if pair not in user_alerts.symbols():
        raise ValueError('Choose a symbol from the broker catalogue')
    if not _LOCK.acquire(blocking=False):
        return _unavailable(pair, 'Quote service busy; try again shortly.')
    try:
        now = time.time()
        cached = _CACHE.get(pair)
        if cached and now-cached[0] < TTL:
            result = dict(cached[1])
            # Recheck actual provider timestamp, not just the cache age.
            if result['available'] and not user_alerts.fresh_quote(result['price'], result['quote_time'], now):
                return _unavailable(pair, 'Latest broker quote is stale. Market may be closed.')
            return result
        while _ATTEMPTS and _ATTEMPTS[0] <= now-60:
            _ATTEMPTS.popleft()
        if len(_ATTEMPTS) >= MAX_REQUESTS_PER_MINUTE:
            return _unavailable(pair, 'Quote refresh limit reached; try again in one minute.')
        _ATTEMPTS.append(now)
        result = _unavailable(pair)
        try:
            data = _fetch(pair)
            price, stamp = data.get('quote'), data.get('quote_time')
            if user_alerts.fresh_quote(price, stamp, time.time()):
                result.update(available=True, fresh=True, price=float(price), quote_time=int(stamp), timestamp=int(stamp),
                              formatted=instruments.fmt(pair, price), reason=None)
            elif stamp is not None:
                result['reason'] = 'Latest broker quote is stale. Market may be closed.'
        except Exception:
            # Never expose credentials or upstream exceptions to the page.
            pass
        _CACHE[pair] = (time.time(), result)
        _CACHE.move_to_end(pair)
        while len(_CACHE) > MAX_CACHE:
            _CACHE.popitem(last=False)
        return dict(result)
    finally:
        _LOCK.release()

"""Bounded on-demand H1 replay fill; shared cache, no per-user candle copies."""
from contextlib import ExitStack
from collections import deque
import threading
import time
from slk import replay_cache, instruments

_LOCK = threading.Lock()
_ATTEMPTS = deque()


def fill(db, pair, lo, hi, now):
    if hi - lo > 22 * 86400 or lo < 0:
        return False
    if not _LOCK.acquire(blocking=False):
        return False
    try:
        while _ATTEMPTS and _ATTEMPTS[0] <= time.monotonic() - 60:
            _ATTEMPTS.popleft()
        if len(_ATTEMPTS) >= 4:
            return False
        _ATTEMPTS.append(time.monotonic())
        from slk import jobs, store, alert_data
        with ExitStack() as stack:
            if not stack.enter_context(jobs.feed_lock(db, 0, name='slk_personal_feed')):
                return False
            # Same lock as hourly publication protects cache capacity and merging.
            if not stack.enter_context(jobs.feed_lock(db, 0, name='slk_replay_publish')):
                return False
            if replay_cache.available(db, pair, lo, hi, now, required_until=min(hi, now//3600*3600)) is not None:
                return True
            deadline = time.monotonic() + 25
            provider = 'deriv' if instruments.is_deriv(pair) else 'ctrader'
            if provider == 'deriv':
                from slk.deriv import Feed
                feed = stack.enter_context(Feed(deadline=deadline))
                feed.prefetch([pair])
            else:
                client = alert_data._open_ctrader()
                stack.callback(client.close)
                client.timeout = 8
                feed = store.CTraderFeed(client)
                feed.prefetch([pair])
            conn = db.connect()
            stack.callback(conn.close)
            for name, start, end in replay_cache.months(lo, min(hi, now//3600*3600)):
                if time.monotonic() >= deadline:
                    return False
                end = min(end, now//3600*3600)
                # Full monthly chunks keep the existing shared cache's coverage contract.
                rows = feed.bars(pair, start, end)
                rows = sorted({int(r[0]): list(r[:5]) for r in rows if start <= r[0] and r[0]+3600 <= end}.values())
                if not rows or rows[0][0] > max(start, lo)+3*86400 or rows[-1][0]+3600 < min(end,hi)-3*86400:
                    return False
                replay_cache._publish_chunk(conn, pair, name, rows, rows[-1][0]+3600, now, provider)
            return True
    except Exception:
        # No upstream credentials/errors in user-facing responses. Queue remains fallback.
        return False
    finally:
        _LOCK.release()

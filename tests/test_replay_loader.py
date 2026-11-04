from contextlib import contextmanager
from webapp import replay_loader as loader
from slk import jobs, replay_cache, alert_data, store


def test_busy_and_oversized_never_fetch(monkeypatch):
    monkeypatch.setattr(alert_data, '_open_ctrader', lambda: (_ for _ in ()).throw(AssertionError('must not fetch')))
    assert not loader.fill(None, 'EURUSD', 0, 23*86400, 23*86400)
    loader._LOCK.acquire()
    try:
        assert not loader.fill(None, 'EURUSD', 0, 86400, 86400)
    finally:
        loader._LOCK.release()


def test_fetch_publishes_closed_month_and_releases(monkeypatch):
    loader._ATTEMPTS.clear()
    @contextmanager
    def lock(*a, **kw):
        yield True
    monkeypatch.setattr(jobs, 'feed_lock', lock)
    monkeypatch.setattr(replay_cache, 'available', lambda *a, **kw: None)
    class Client:
        closed = False
        def close(self): self.closed = True
    client = Client()
    monkeypatch.setattr(alert_data, '_open_ctrader', lambda: client)
    class Feed:
        def prefetch(self, pairs): assert pairs == ['EURUSD']
        def bars(self, pair, start, end):
            return [[t,1,2,.5,1.5] for t in range(start,end+3600,3600)]
    monkeypatch.setattr(store, 'CTraderFeed', lambda c: Feed())
    class DB:
        def connect(self): return Client()
    published=[]
    monkeypatch.setattr(replay_cache, '_publish_chunk', lambda *args: published.append(args))
    assert loader.fill(DB(), 'EURUSD', 0, 86400, 86400)
    assert len(published)==1
    assert len(published[0][3])==24  # excludes the unfinished next candle
    assert published[0][-1]=='ctrader'
    assert client.closed
    assert not loader._LOCK.locked()


def test_upstream_failure_safe(monkeypatch):
    loader._ATTEMPTS.clear()
    @contextmanager
    def lock(*a, **kw): yield True
    monkeypatch.setattr(jobs, 'feed_lock', lock)
    monkeypatch.setattr(replay_cache, 'available', lambda *a, **kw: None)
    monkeypatch.setattr(alert_data, '_open_ctrader', lambda: (_ for _ in ()).throw(RuntimeError('private broker detail')))
    assert loader.fill(None,'EURUSD',0,86400,86400) is False
    assert not loader._LOCK.locked()

import pytest
from tests.test_webapp import client, hdr, make_init_data
import alert_quotes as quotes


@pytest.fixture(autouse=True)
def reset_quotes(monkeypatch):
    quotes._CACHE.clear(); quotes._ATTEMPTS.clear()
    monkeypatch.setattr(quotes.user_alerts, 'symbols', lambda: {'EURUSD','GBPUSD','DVR75'})
    monkeypatch.setattr(quotes.time, 'time', lambda: 1000)


def test_shared_cache_quote_only_and_immutable_result(monkeypatch):
    calls=[]
    monkeypatch.setattr(quotes,'_fetch',lambda pair: calls.append(pair) or {'quote':1.1,'quote_time':995})
    first=quotes.preview('eurusd'); first['price']=2
    assert quotes.preview('EURUSD')['price']==1.1
    assert calls==['EURUSD']
    assert quotes.preview('EURUSD')['quote_time']==995


def test_old_future_invalid_and_failure_quotes_never_current(monkeypatch):
    for data in ({'quote':1.2,'quote_time':800}, {'quote':1.2,'quote_time':1001},
                 {'quote':float('nan'),'quote_time':999},{}):
        quotes._CACHE.clear()
        monkeypatch.setattr(quotes,'_fetch',lambda pair: data)
        result=quotes.preview('EURUSD')
        assert result['available'] is False and result['price'] is None
    quotes._CACHE.clear()
    def fail(pair):raise RuntimeError('secret broker token')
    monkeypatch.setattr(quotes,'_fetch',fail)
    assert 'secret' not in str(quotes.preview('EURUSD'))


def test_cached_quote_freshness_is_rechecked(monkeypatch):
    monkeypatch.setattr(quotes,'_fetch',lambda pair:{'quote':1.1,'quote_time':890})
    assert quotes.preview('EURUSD')['available']
    monkeypatch.setattr(quotes.time,'time',lambda:1020)
    assert quotes.preview('EURUSD')['available'] is False


def test_rate_limit_and_busy_do_not_fetch(monkeypatch):
    monkeypatch.setattr(quotes,'_fetch',lambda pair: pytest.fail('must not fetch'))
    quotes._ATTEMPTS.extend([999]*quotes.MAX_REQUESTS_PER_MINUTE)
    assert not quotes.preview('GBPUSD')['available']
    quotes._LOCK.acquire()
    try:assert not quotes.preview('EURUSD')['available']
    finally:quotes._LOCK.release()
    with pytest.raises(ValueError):quotes.preview('https://malicious.test')


def test_endpoint_requires_auth_and_returns_no_store(client,monkeypatch):
    calls=[]
    monkeypatch.setattr(quotes,'_fetch',lambda pair:calls.append(pair) or {'quote':1.2,'quote_time':999})
    assert client.get('/api/alerts/quote?pair=EURUSD').status_code==403
    assert calls==[]
    response=client.get('/api/alerts/quote?pair=EURUSD',headers=hdr(make_init_data()))
    assert response.status_code==200
    assert response.json()['available']
    assert response.headers['cache-control']=='no-store'
    assert client.get('/api/alerts/quote?pair=WRONG',headers=hdr(make_init_data())).status_code==422


def test_fetch_is_quote_only_and_defers_when_scanner_owns_lease(monkeypatch):
    from contextlib import contextmanager
    from slk import jobs
    calls=[]; allowed=[True]
    @contextmanager
    def lease(db,wait,name):
        assert wait==0 and name=='slk_personal_feed'
        yield allowed[0]
    monkeypatch.setattr(jobs,'feed_lock',lease)
    def load(pairs,now,**kwargs):
        assert now.tzinfo is not None
        assert pairs==['EURUSD']
        assert kwargs['requirements']=={'EURUSD':{'quote':True,'timeframes':[]}}
        assert kwargs['max_pairs']==1
        calls.append(pairs)
        return {'EURUSD':{'quote':1.1,'quote_time':999}}
    monkeypatch.setattr(quotes.alert_data,'load',load)
    assert quotes._fetch('EURUSD')['quote']==1.1
    allowed[0]=False
    assert quotes._fetch('EURUSD')=={}
    assert len(calls)==1

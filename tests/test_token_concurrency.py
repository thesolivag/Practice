"""No broker calls: exercise shared token lease, fresh reread and atomic publication."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from ctrader import tokens
from slk import tenancy


class FakeDb:
    def __init__(self, busy=False, fail_store=False, barrier=None):
        self.values=dict(zip(tokens.TOKEN_KEYS,('old-access','old-refresh','1')))
        self.lock=threading.Lock();self.events=[];self.reads=0;self.busy=busy;self.fail_store=fail_store;self.barrier=barrier
    def get_setting(self,k,default=None):
        assert tenancy.tenant_id() is None
        value=self.values.get(k,default)
        if k==tokens.TOKEN_KEYS[2] and self.barrier:self.barrier.wait(timeout=5)
        return value
    def set_setting(self,k,v):
        assert tenancy.tenant_id() is None
        self.values[k]=v
    def connect(self):
        assert tenancy.tenant_id() is None
        db=self
        class Conn:
            def __init__(self):self.pending=None;self.owns=False
            def cursor(self):return self
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def execute(self,sql,args):
                self.sql=sql;self.args=args
                if 'GET_LOCK' in sql:
                    assert ',60)' in sql
                    self.owns=not db.busy and db.lock.acquire(timeout=5)
                    db.events.append('lock' if self.owns else 'busy')
                elif 'RELEASE_LOCK' in sql:
                    assert self.owns
                    db.lock.release();self.owns=False;db.events.append('release')
                elif sql.startswith('SELECT v FROM settings'):
                    self.one=({'v':db.values[args[0]]} if args[0] in db.values else None)
                elif sql.startswith('INSERT INTO settings'):
                    if db.fail_store:raise RuntimeError('storage failed')
                    db.values[args[0]]=args[1]
                elif sql.startswith('SELECT k,v'):
                    db.reads+=1
                    self.rows=[{'k':k,'v':v} for k,v in db.values.items()]
                    if not self.owns and db.barrier:db.barrier.wait(timeout=5)
            def fetchone(self):return self.one if self.sql.startswith('SELECT v FROM settings') else {'acquired':int(self.owns)}
            def fetchall(self):return self.rows
            def begin(self):db.events.append('begin');self.pending=dict(db.values)
            def executemany(self,sql,args):
                assert 'tenant_' not in sql and self.owns
                assert len(args)==3
                self.pending.update(args)
                if db.fail_store:raise RuntimeError('storage failed')
            def commit(self):
                if self.pending is not None:db.values=self.pending
                db.events.append('commit')
            def rollback(self):self.pending=None;db.events.append('rollback')
            def close(self):
                if self.owns:db.lock.release();self.owns=False
                db.events.append('close')
        return Conn()


def refresh(store,http,**kw):
    return tokens.refresh_tokens(tokens.DbSettings(store),client_id='c',client_secret='s',http_get=http,**kw)


def test_parallel_waiters_refresh_once_and_reuse_latest_pair():
    db=FakeDb(barrier=threading.Barrier(2));calls=[]
    def http(url,params):
        calls.append(params['refresh_token'])
        return {'accessToken':'new-access','refreshToken':'new-refresh','expiresIn':999999}
    def run(_):
        with tenancy.scope(42):return refresh(db,http)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,range(2)))
    assert calls==['old-refresh']
    assert results[0]==results[1]
    assert db.events.count('commit')==1 and db.events.count('release')==2 and db.events.count('close')==4
    assert db.values['ctrader_access_token']=='new-access' and db.values['ctrader_refresh_token']=='new-refresh'
    assert tenancy.USER.get() is None


def test_explicit_stale_refresh_argument_reuses_committed_tokens():
    db=FakeDb();db.values=dict(zip(tokens.TOKEN_KEYS,('new-access','new-refresh',str(time.time()+9999))))
    result=refresh(db,lambda *a:pytest.fail('must reuse DB pair'),refresh_token='old-refresh')
    assert result['access_token']=='new-access'
    assert db.events==['close','lock','release','close']


def test_busy_lock_never_refreshes_or_falls_back():
    db=FakeDb(busy=True)
    with pytest.raises(RuntimeError,match='busy'):refresh(db,lambda *a:pytest.fail('must not call broker'))
    assert db.events==['close','busy','close']
    assert db.values['ctrader_refresh_token']=='old-refresh'


def test_refresh_failure_releases_lock_and_keeps_previous_pair():
    db=FakeDb()
    def fail(*a):raise RuntimeError('provider failed')
    with pytest.raises(RuntimeError):refresh(db,fail)
    assert db.events==['close','lock','release','close']
    assert db.values['ctrader_access_token']=='old-access'


def test_storage_failure_rolls_back_whole_pair_and_releases_lock():
    db=FakeDb(fail_store=True)
    with pytest.raises(RuntimeError):refresh(db,lambda *a:{'accessToken':'new','refreshToken':'new-r','expiresIn':999})
    assert db.values['ctrader_access_token']=='old-access' and db.values['ctrader_refresh_token']=='old-refresh'
    assert db.events==['close','lock','begin','rollback','release','close']


def test_global_broker_settings_do_not_read_or_write_tenant_settings():
    db=FakeDb();settings=tokens.DbSettings(db)
    with tenancy.scope(42):
        assert settings.get('ctrader_refresh_token')=='old-refresh'
        settings.set('ctrader_access_token','replacement')
        assert tenancy.USER.get()==42
    assert db.values['ctrader_access_token']=='replacement'


def test_refresh_error_does_not_expose_oauth_query_credentials():
    db=FakeDb()
    def fail(*a):raise RuntimeError('https://provider?refresh_token=top-secret&client_secret=another-secret')
    with pytest.raises(RuntimeError) as exc:refresh(db,fail)
    assert str(exc.value)=='cTrader token refresh failed'
    assert exc.value.__suppress_context__


def test_real_mysql_parallel_refresh_is_one_rotation(monkeypatch):
    import os
    from slk import db as mysql
    url=os.environ.get('SLK_TEST_MYSQL')
    if not url:pytest.skip('requires disposable MySQL8')
    barrier=threading.Barrier(2)
    class Adapter:
        def connect(self):return mysql.connect(url)
        def get_setting(self,k,default=None):
            conn=self.connect()
            try:
                with conn.cursor() as cur:
                    cur.execute('SELECT v FROM settings WHERE k=%s',(k,))
                    row=cur.fetchone()
                value=row['v'] if row else default
            finally:conn.close()
            if k==tokens.TOKEN_KEYS[2]:barrier.wait(timeout=10)
            return value
    real_load=tokens.load_tokens
    def load(settings):
        result=real_load(settings)
        barrier.wait(timeout=10)
        return result
    monkeypatch.setattr(tokens,'load_tokens',load)
    adapter=Adapter();conn=adapter.connect()
    try:
        with conn.cursor() as cur:
            cur.execute('CREATE TABLE IF NOT EXISTS settings (k VARCHAR(64) PRIMARY KEY,v TEXT NULL)')
            cur.execute('SELECT k,v FROM settings WHERE k IN (%s,%s,%s)',tokens.TOKEN_KEYS)
            previous=cur.fetchall()
            cur.executemany('INSERT INTO settings (k,v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=VALUES(v)',
                            list(zip(tokens.TOKEN_KEYS,('test-old-a','test-old-r','1'))))
        calls=[]
        def http(url,params):
            calls.append(params['refresh_token'])
            return {'accessToken':'test-new-a','refreshToken':'test-new-r','expiresIn':999999}
        def run(_):return tokens.refresh_tokens(tokens.DbSettings(adapter),client_id='c',client_secret='s',http_get=http)
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,range(2)))
        assert calls==['test-old-r'] and results[0]==results[1]
        with conn.cursor() as cur:
            cur.execute('SELECT IS_FREE_LOCK(%s) AS free',(tokens.TOKEN_LOCK,))
            assert cur.fetchone()['free']==1
    finally:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM settings WHERE k IN (%s,%s,%s)',tokens.TOKEN_KEYS)
            if previous:cur.executemany('INSERT INTO settings (k,v) VALUES (%s,%s)',[(r['k'],r['v']) for r in previous])
        conn.close()


def test_db_load_reads_three_token_fields_in_one_global_statement(monkeypatch):
    db=FakeDb()
    monkeypatch.setattr(db,'get_setting',lambda *a:pytest.fail('individual reads can straddle a rotation'))
    with tenancy.scope(42):
        result=tokens.load_tokens(tokens.DbSettings(db))
        assert tenancy.USER.get()==42
    assert result=={'access_token':'old-access','refresh_token':'old-refresh','expiry':1.0}
    assert db.reads==1 and db.events==['close']


def test_db_settings_get_set_use_private_connections_not_shared_singleton(monkeypatch):
    db=FakeDb()
    def shared_forbidden(*args):pytest.fail('must not touch shared singleton helpers')
    monkeypatch.setattr(db,'get_setting',shared_forbidden)
    monkeypatch.setattr(db,'set_setting',shared_forbidden)
    settings=tokens.DbSettings(db)
    with tenancy.scope(42):
        assert settings.get('missing','default')=='default'
        settings.set('kill_switch','on')
        assert settings.get('kill_switch')=='on'
        settings.set('nullable',None)
        assert settings.get('nullable','fallback')=='fallback'
        assert tenancy.USER.get()==42
    assert db.events.count('close')==5 and db.events.count('commit')==2


def test_db_settings_write_failure_closes_dedicated_connection():
    db=FakeDb(fail_store=True)
    with pytest.raises(RuntimeError):tokens.DbSettings(db).set('kill_switch','on')
    assert db.events==['rollback','close']

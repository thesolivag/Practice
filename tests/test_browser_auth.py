"""Auth semantics with actual transactional storage, no production DB or Telegram."""
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
import browser_auth as auth


@pytest.fixture
def auth_app(monkeypatch, tmp_path):
    path = tmp_path / "auth.sqlite"
    sqlite3.connect(path).executescript("""
      CREATE TABLE app_users(user_id INTEGER PRIMARY KEY);
      CREATE TABLE web_auth_codes(code_hash TEXT PRIMARY KEY,user_id INTEGER,client TEXT,created_at INTEGER,expires_at INTEGER,used_at INTEGER);
      CREATE TABLE browser_sessions(id TEXT PRIMARY KEY,token_hash TEXT UNIQUE,user_id INTEGER,client TEXT,name TEXT,created_at INTEGER,expires_at INTEGER,revoked_at INTEGER);
      CREATE TABLE auth_rate_limits(k TEXT PRIMARY KEY,attempts INTEGER,expires_at INTEGER);
    """)
    def translate(sql):
        return sql.replace("INSERT IGNORE INTO", "INSERT OR IGNORE INTO").replace("%s", "?").replace(" FOR UPDATE", "").replace(
            "ON DUPLICATE KEY UPDATE attempts=attempts+1", "ON CONFLICT(k) DO UPDATE SET attempts=attempts+1")
    class Cursor:
        def __init__(self, conn): self.cur=conn.cursor()
        def __enter__(self):return self
        def __exit__(self,*a):self.cur.close()
        def execute(self,sql,args=None):self.cur.execute(translate(sql),args or ());return self.cur.rowcount
        @property
        def rowcount(self):return self.cur.rowcount
        def fetchone(self):
            row=self.cur.fetchone();return dict(row) if row else None
        def fetchall(self):return [dict(r) for r in self.cur.fetchall()]
    class Connection:
        def __init__(self):
            self.conn=sqlite3.connect(path,timeout=10,isolation_level=None)
            self.conn.row_factory=sqlite3.Row
        def cursor(self,*a):return Cursor(self.conn)
        def begin(self):self.conn.execute("BEGIN IMMEDIATE")
        def commit(self):self.conn.commit()
        def rollback(self):self.conn.rollback()
        def close(self):self.conn.close()
    def query(sql,args=None):
        c=Connection()
        try:
            with c.cursor() as cur:cur.execute(sql,args);return cur.fetchall()
        finally:c.close()
    def execute(sql,args=None):
        c=Connection()
        try:
            with c.cursor() as cur:return cur.execute(sql,args)
        finally:c.close()
    monkeypatch.setattr(auth.db,'connect',Connection)
    monkeypatch.setattr(auth.db,'query',query)
    monkeypatch.setattr(auth.db,'execute',execute)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','test')
    monkeypatch.delenv('APP_ORIGIN',raising=False)
    def validate(init,*args):
        if init not in ('verified','other'):raise ValueError('bad')
        return {'id':12345 if init=='verified' else 12346}
    app=FastAPI();auth.register_routes(app,validate)
    @app.post('/mutate')
    def mutate(request:Request):return auth.resolve_user(request)
    app.test_query=query
    with TestClient(app,base_url='https://testserver') as c:
        yield c,app


TG={'X-Telegram-Init-Data':'verified'}
ORIGIN={'Origin':'https://testserver'}


def pair(client,kind='browser'):
    r=client.post('/api/auth/pair-code',headers=TG,json={'client':kind,'user_id':999})
    assert r.status_code==200,r.text
    return r.json()['code']


def test_code_telegram_only_hash_only_single_use(auth_app):
    c,app=auth_app
    assert c.post('/api/auth/pair-code',json={}).status_code==403
    code=pair(c)
    row=app.test_query('SELECT * FROM web_auth_codes')[0]
    assert row['user_id']==12345 and code.replace('-','') not in str(row)
    result=c.post('/api/auth/redeem',headers=ORIGIN,json={'code':code})
    assert result.status_code==200 and result.json()['user']['id']==12345
    assert 'token' not in result.json()
    cookie=result.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie
    assert c.post('/api/auth/redeem',headers=ORIGIN,json={'code':code}).status_code==401
    assert c.post('/api/auth/pair-code',json={}).status_code==403 # browser cannot mint new codes
    token=c.cookies.get(auth.COOKIE)
    assert token not in str(app.test_query('SELECT * FROM browser_sessions'))


def test_cookie_csrf_origin_and_revocation(auth_app):
    c,app=auth_app
    r=c.post('/api/auth/redeem',headers=ORIGIN,json={'code':pair(c)})
    assert r.status_code==200
    session=c.get('/api/auth/session').json()
    assert session['auth_method']=='browser' and session['user']['id']==12345
    csrf=session['csrf']
    assert c.post('/mutate',headers=ORIGIN).status_code==403
    assert c.post('/mutate',headers={'Origin':'https://evil.test','X-CSRF-Token':csrf}).status_code==403
    valid={**ORIGIN,'X-CSRF-Token':csrf}
    assert c.post('/mutate',headers=valid).status_code==200
    sessions=c.get('/api/auth/sessions',headers=TG).json()
    assert len(sessions)==1 and 'token_hash' not in sessions[0]
    assert c.get('/api/auth/sessions').status_code==403
    assert c.delete('/api/auth/sessions/'+sessions[0]['id'],headers=TG).status_code==200
    assert c.post('/mutate',headers=valid).status_code==403


def test_extension_token_purpose_and_expiry(auth_app,monkeypatch):
    c,app=auth_app
    code=pair(c,'extension')
    assert c.post('/api/auth/redeem',headers=ORIGIN,json={'code':code,'client':'browser'}).status_code==401
    result=c.post('/api/auth/redeem',json={'code':code,'client':'extension','name':'Chrome'}).json()
    assert 'token' in result and not c.cookies
    bearer={'Authorization':'Bearer '+result['token']}
    assert c.get('/api/auth/session',headers=bearer).json()['auth_method']=='extension'
    assert c.post('/mutate',headers=bearer).status_code==200
    monkeypatch.setattr(auth,'_now',lambda:result['expires_at'])
    assert c.get('/api/auth/session',headers=bearer).status_code==403


def test_pairing_code_expiry_origin_and_issue_rate(auth_app,monkeypatch):
    c,app=auth_app
    code=pair(c)
    assert c.post('/api/auth/redeem',headers={'Origin':'https://evil.test'},json={'code':code}).status_code==403
    now=auth._now()
    monkeypatch.setattr(auth,'_now',lambda:now+auth.CODE_TTL)
    assert c.post('/api/auth/redeem',headers=ORIGIN,json={'code':code}).status_code==401
    monkeypatch.setattr(auth,'_now',lambda:now)
    for _ in range(4):pair(c)
    assert c.post('/api/auth/pair-code',headers=TG,json={}).status_code==429


def test_concurrent_code_redemption_creates_one_session(auth_app):
    c,app=auth_app
    code=pair(c)
    def redeem(_):
        try:
            return auth.consume_code(code,'browser','Browser')['user']['id']
        except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(redeem,range(2)))
    assert sorted(results)==[401,12345]
    assert len(app.test_query('SELECT * FROM browser_sessions'))==1


def test_logout_invalidates_server_session(auth_app):
    c,_=auth_app
    c.post('/api/auth/redeem',headers=ORIGIN,json={'code':pair(c)})
    session=c.get('/api/auth/session').json()
    assert c.post('/api/auth/logout',headers={**ORIGIN,'X-CSRF-Token':session['csrf']}).status_code==200
    assert c.get('/api/auth/session').status_code==403


def test_sessions_cannot_be_revoked_by_another_telegram_user(auth_app):
    c,app=auth_app
    c.post('/api/auth/redeem',headers=ORIGIN,json={'code':pair(c)})
    sid=c.get('/api/auth/session').json()['session_id']
    assert c.delete('/api/auth/sessions/'+sid,headers={'X-Telegram-Init-Data':'other'}).status_code==200
    assert c.get('/api/auth/session').status_code==200
    assert c.get('/api/auth/sessions',headers={'X-Telegram-Init-Data':'other'}).json()==[]


def test_browser_and_extension_tokens_are_not_interchangeable(auth_app):
    c,_=auth_app
    c.post('/api/auth/redeem',headers=ORIGIN,json={'code':pair(c)})
    browser=c.cookies.get(auth.COOKIE)
    assert c.get('/api/auth/session',headers={'Authorization':'Bearer '+browser}).status_code==403
    c.cookies.clear()
    r=c.post('/api/auth/redeem',json={'code':pair(c,'extension'),'client':'extension'})
    token=r.json()['token']
    c.cookies.set(auth.COOKIE,token)
    assert c.get('/api/auth/session').status_code==403


def test_new_code_invalidates_previous_same_client_and_active_sessions_are_bounded(auth_app,monkeypatch):
    c,app=auth_app
    monkeypatch.setattr(auth,'_limit',lambda *args:None)
    old=pair(c)
    fresh=pair(c)
    assert c.post('/api/auth/redeem',headers=ORIGIN,json={'code':old}).status_code==401
    assert c.post('/api/auth/redeem',headers=ORIGIN,json={'code':fresh}).status_code==200
    for _ in range(auth.MAX_SESSIONS-1):
        assert c.post('/api/auth/redeem',headers=ORIGIN,json={'code':pair(c)}).status_code==200
    assert c.post('/api/auth/redeem',headers=ORIGIN,json={'code':pair(c)}).status_code==409
    assert len(app.test_query('SELECT * FROM browser_sessions'))==auth.MAX_SESSIONS


def test_concurrent_different_client_codes_share_session_cap(auth_app,monkeypatch):
    c,app=auth_app
    monkeypatch.setattr(auth,'_limit',lambda *args:None)
    for _ in range(auth.MAX_SESSIONS-1):auth.consume_code(pair(c),'browser','Browser')
    codes=[(pair(c,'browser'),'browser'),(pair(c,'extension'),'extension')]
    def redeem(args):
        code,kind=args
        try:auth.consume_code(code,kind,kind);return 200
        except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(redeem,codes))
    assert sorted(results)==[200,409]
    assert len(app.test_query('SELECT * FROM browser_sessions'))==auth.MAX_SESSIONS


def test_mysql_pairing_transaction_and_concurrent_session_cap(monkeypatch):
    """Optional real InnoDB proof: account locks serialize separate browser/extension codes."""
    import os
    import time
    url=os.environ.get('SLK_TEST_MYSQL')
    if not url:pytest.skip('requires disposable MySQL8')
    monkeypatch.setenv('DATABASE_URL',url)
    monkeypatch.delenv('DATABASE_PASSWORD',raising=False)
    auth.db.execute('CREATE TABLE IF NOT EXISTS app_users (user_id BIGINT PRIMARY KEY)')
    sql=(Path(__file__).resolve().parents[1]/'db'/'browser_auth.sql').read_text()
    import re
    for statement in re.sub(r'--[^\n]*','',sql).split(';'):
        if statement.strip():auth.db.execute(statement)
    monkeypatch.setattr(auth,'_limit',lambda *args:None)
    uid=time.time_ns()
    try:
        for _ in range(auth.MAX_SESSIONS-1):
            code=auth.issue_code(uid)['code']
            auth.consume_code(code,'browser','Browser')
        codes=[(auth.issue_code(uid,'browser')['code'],'browser'),
               (auth.issue_code(uid,'extension')['code'],'extension')]
        def redeem(args):
            code,kind=args
            try:auth.consume_code(code,kind,kind);return 200
            except HTTPException as exc:return exc.status_code
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(redeem,codes))
        assert sorted(results)==[200,409]
        rows=auth.db.query('SELECT id FROM browser_sessions WHERE user_id=%s',(uid,))
        assert len(rows)==auth.MAX_SESSIONS
    finally:
        auth.db.execute('DELETE FROM browser_sessions WHERE user_id=%s',(uid,))
        auth.db.execute('DELETE FROM web_auth_codes WHERE user_id=%s',(uid,))
        auth.db.execute('DELETE FROM app_users WHERE user_id=%s',(uid,))

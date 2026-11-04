"""Pause lifecycle against a real transactional table (SQLite SQL adapter)."""
import json
import sqlite3
import pytest
from slk import user_alerts as A
from tests.test_alert_modes import body


class Connection:
    def __init__(self):
        self.raw=sqlite3.connect(':memory:',isolation_level=None)
        self.raw.row_factory=sqlite3.Row
    def begin(self):self.raw.execute('BEGIN')
    def commit(self):self.raw.commit()
    def rollback(self):self.raw.rollback()


class Repo(A.Repository):
    def __init__(self):
        self.conn=Connection()
        self.conn.raw.execute('CREATE TABLE manual_alerts (id INTEGER,user_id INTEGER,status TEXT,expires_at INTEGER,created_at INTEGER,last_checked INTEGER,options_json TEXT,last_quote REAL,quote_time INTEGER,lease_token TEXT,lease_until INTEGER,error TEXT,condition TEXT)')
        data=A.validate(body(),100)
        self.conn.raw.execute('INSERT INTO manual_alerts VALUES (1,42,\'ACTIVE\',10000,100,100,?,9,101,NULL,0,NULL,\'breakout\')',(data['options_json'],))
    def sql(self,sql):return sql.replace(' FOR UPDATE','').replace('%s','?').replace('GREATEST(','MAX(')
    def query(self,sql,args=()):return [dict(r) for r in self.conn.raw.execute(self.sql(sql),args).fetchall()]
    def execute(self,sql,args=()):return self.conn.raw.execute(self.sql(sql),args).rowcount
    def current(self):return self.query('SELECT * FROM manual_alerts')[0]


def test_owned_pause_resume_fixed_expiry_and_no_paused_signals():
    repo=Repo()
    assert repo.set_paused(99,1,True,200) is None
    assert repo.current()['status']=='ACTIVE'
    assert repo.set_paused(42,1,True,200)
    paused=repo.current()
    assert paused['status']=='PAUSED' and paused['expires_at']==10000
    assert not repo._trigger_locked(paused,{'time':250})
    assert repo.set_paused(42,1,False,300)
    resumed=repo.current()
    assert resumed['status']=='ACTIVE' and resumed['expires_at']==10000
    assert resumed['last_quote'] is None and resumed['quote_time'] is None
    assert set(A.watch_options(resumed)['cursors'].values())=={300}
    assert not repo._trigger_locked(resumed,{'time':250,'timeframe':'H1'})
    assert repo.set_paused(42,1,False,400)  # retry must not move cursors
    assert set(A.watch_options(repo.current())['cursors'].values())=={300}
    assert repo.cancel(42,1,400)
    assert repo.current()['status']=='CANCELLED'


def test_expired_paused_alert_cannot_resume():
    repo=Repo();repo.set_paused(42,1,True,200)
    with pytest.raises(ValueError,match='expired'):repo.set_paused(42,1,False,10000)
    assert repo.current()['status']=='EXPIRED'


@pytest.mark.parametrize('status,lease', [('TRIGGERED',0),('FIRED',0),('ACTIVE',1000)])
def test_pending_delivery_and_terminal_state_cannot_pause(status,lease):
    repo=Repo();repo.execute('UPDATE manual_alerts SET status=%s,lease_until=%s',(status,lease))
    with pytest.raises(ValueError):repo.set_paused(42,1,True,200)
    assert repo.current()['status']==status


def test_confirmation_default_is_one_day():
    data=A.validate(body(),100)
    assert data['expires_at']-data['created_at']==86400


def test_pause_api_requires_auth_and_ownership(client,monkeypatch):
    class Store:
        def __init__(self,db):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def set_paused(self,uid,ident,paused):
            assert uid==777000111
            if ident==2:return None
            if ident==3:raise ValueError('Delivery is in progress')
            return True
    from tests.test_webapp import make_init_data
    monkeypatch.setattr(A,'Repository',Store)
    headers={'X-Telegram-Init-Data':make_init_data()}
    for action in ('pause','resume'):
        assert client.post('/api/alerts/1/'+action).status_code==403
        assert client.post('/api/alerts/1/'+action,headers=headers).status_code==200
        assert client.post('/api/alerts/2/'+action,headers=headers).status_code==404
        assert client.post('/api/alerts/3/'+action,headers=headers).status_code==409

from tests.test_webapp import client

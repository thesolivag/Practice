from types import SimpleNamespace
import pytest
from slk import runtime_config as R,tenancy
from ctrader.tokens import DbSettings
from ctrader.client import CTraderClient
from tests.test_webapp import client


class DB:
    def __init__(self):self.values=dict(zip(R.KEYS,('stored-id','stored-secret','77','demo')));self.events=[];self.fail=False
    def connect(self):
        assert tenancy.tenant_id() is None
        db=self
        class Connection:
            def begin(self):db.events.append('begin')
            def cursor(self):return self
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def execute(self,sql,args):
                self.args=args;self.sql=sql;db.events.append('lock' if 'GET_LOCK' in sql else 'unlock' if 'RELEASE_LOCK' in sql else 'read')
            def fetchone(self):return {'acquired':1}
            def fetchall(self):return [dict(k=k,v=db.values[k]) for k in self.args if k in db.values]
            def executemany(self,sql,args):
                db.events.append('write')
                values=dict(args)
                if 'v=IF' in sql:values={k:v for k,v in values.items() if not db.values.get(k)}
                self.pending={**getattr(self,'pending',{}),**values}
                if db.fail:raise RuntimeError('write failed')
            def commit(self):db.values.update(self.pending);db.events.append('commit')
            def rollback(self):db.events.append('rollback')
            def close(self):db.events.append('close')
        return Connection()


@pytest.fixture
def clean_env(monkeypatch):
    for name in ('CTRADER_CLIENT_ID','CTRADER_CLIENT_SECRET','CTRADER_ACCOUNT_ID','CTRADER_ENV','CTRADER_ACCESS_TOKEN','CTRADER_REFRESH_TOKEN'):
        monkeypatch.delenv(name,raising=False)


def test_server_config_is_atomic_global_and_preserves_account_selection(clean_env):
    db=DB()
    with tenancy.scope(42):
        config=R.load(DbSettings(db))
        assert tenancy.USER.get()==42
    assert config==dict(client_id='stored-id',client_secret='stored-secret',account_id='77',environment='demo')
    assert db.events==['read','close']
    client=CTraderClient(settings=DbSettings(db))
    assert (client.client_id,client.client_secret,client.account_id_cfg,client.env)==('stored-id','stored-secret','77','demo')


def test_partial_environment_does_not_mix_with_stored_credentials(clean_env,monkeypatch):
    monkeypatch.setenv('CTRADER_CLIENT_ID','partial-env')
    assert R.credentials(DbSettings(DB()))==('stored-id','stored-secret')
    monkeypatch.setenv('CTRADER_CLIENT_SECRET','env-secret')
    assert R.credentials(DbSettings(DB()))==('partial-env','env-secret')


@pytest.mark.parametrize('failure',[False,True])
def test_trusted_actions_sync_is_one_transaction(clean_env,monkeypatch,failure):
    db=DB();db.fail=failure
    monkeypatch.setenv('CTRADER_CLIENT_ID','new-id');monkeypatch.setenv('CTRADER_CLIENT_SECRET','new-secret')
    monkeypatch.setenv('CTRADER_ACCOUNT_ID','88');monkeypatch.setenv('CTRADER_ENV','demo')
    if failure:
        with pytest.raises(RuntimeError):R.sync(db)
        assert db.values[R.KEYS[0]]=='stored-id'
    else:
        assert R.sync(db)=={'synced':True}
        assert R.load(DbSettings(db))['account_id']=='88'
    assert ('rollback' if failure else 'commit') in db.events and db.events[-1]=='close'


def test_private_broker_keys_cannot_be_read_or_changed_through_user_settings(client):
    from tests.test_webapp import hdr,make_init_data
    client.store.update({'ctrader_client_id':'private-app-id','ctrader_client_secret':'private-app-secret','ctrader_account_id':'77'})
    response=client.get('/api/settings',headers=hdr(make_init_data()))
    assert 'private-app-secret' not in response.text and 'ctrader_client_id' not in response.json()
    rejected=client.post('/api/settings',headers=hdr(make_init_data()),json={'ctrader_client_secret':'replacement'})
    assert rejected.status_code==422 and client.store['ctrader_client_secret']=='private-app-secret'


def test_bootstrap_seeds_missing_tokens_but_never_overwrites_rotated_pair(clean_env,monkeypatch):
    db=DB()
    monkeypatch.setenv('CTRADER_CLIENT_ID','app-id');monkeypatch.setenv('CTRADER_CLIENT_SECRET','app-secret')
    monkeypatch.setenv('CTRADER_ACCESS_TOKEN','bootstrap-access');monkeypatch.setenv('CTRADER_REFRESH_TOKEN','bootstrap-refresh')
    R.sync(db)
    assert db.values['ctrader_access_token']=='bootstrap-access'
    assert db.values['ctrader_refresh_token']=='bootstrap-refresh'
    db.values.update(ctrader_access_token='rotated-access',ctrader_refresh_token='rotated-refresh')
    R.sync(db)
    assert db.values['ctrader_access_token']=='rotated-access' and db.values['ctrader_refresh_token']=='rotated-refresh'


def test_partial_rotated_pair_is_never_mixed_with_old_bootstrap(clean_env,monkeypatch):
    db=DB();db.values['ctrader_access_token']='rotated-access'
    monkeypatch.setenv('CTRADER_CLIENT_ID','app-id');monkeypatch.setenv('CTRADER_CLIENT_SECRET','app-secret')
    monkeypatch.setenv('CTRADER_ACCESS_TOKEN','old-access');monkeypatch.setenv('CTRADER_REFRESH_TOKEN','old-refresh')
    with pytest.raises(RuntimeError,match='incomplete'):R.sync(db)
    assert 'rollback' in db.events and 'ctrader_refresh_token' not in db.values

"""Shared Entries API keeps Bishop source labels and explicit user ownership."""
import json
from tests.test_webapp import client,make_init_data,OWNER
from tests.test_bishop_paper import saved
from slk import bishop_paper as B
import app


def test_entry_strategy_filters_and_bishop_summary_are_separate(client,monkeypatch):
    calls=[]
    winner=saved('WIN','CLOSED');winner['observation']['net_r']='2'
    unknown=saved('CENSORED','CENSORED');unknown['order']['id']='unknown'
    unknown['observation']['net_r']=None
    def query(sql,args=None):
        calls.append((sql,args))
        if 'bishop_app_entries' in sql:
            assert args[0]==OWNER
            return [{'payload':json.dumps(r)} for r in [winner,unknown]]
        if 'bishop_app_state' in sql:return []
        return [{'id':1,'pair':'EURUSD','tf':'H4','side':'BUY','model':'continuation','status':'PENDING','created_at':'2026-11-02 00:00:00'}]
    monkeypatch.setattr(app.db,'query',query)
    headers={'X-Telegram-Init-Data':make_init_data()}
    assert client.get('/api/bishop/status').status_code==403
    response=client.get('/api/entries?strategy=bishop',headers=headers)
    assert response.status_code==200
    assert {r['strategy'] for r in response.json()}=={'bishop'}
    assert {r['status'] for r in response.json()}=={'WIN','UNKNOWN'}
    assert all(r['paper_only'] and str(r['id']).startswith('bishop:') for r in response.json())
    assert {r['strategy'] for r in client.get('/api/entries?strategy=kk',headers=headers).json()}=={'kk'}
    summary=client.get('/api/entries/summary',headers=headers).json()
    assert summary['bishop']['closed']==1 and summary['bishop']['wins']==1 and summary['bishop']['unknown']==1
    assert summary['bishop']['total_r']==2 and summary['closed']==0
    assert client.get('/api/entries?strategy=unrecognised',headers=headers).status_code==422
    # Existing numeric KK approval endpoint cannot accept a Bishop identifier.
    assert client.post('/api/entries/bishop:order-test/approve',headers=headers).status_code==422
    status=client.get('/api/bishop/status',headers=headers).json()
    assert status['paper_only'] and status['entry_timeframes']==['H4','H3','H2','H1']


def test_rr_endpoint_is_private_and_user_scoped(client,monkeypatch):
    calls=[]
    def query(sql,args=None):
        calls.append((sql,args));assert 'bishop_rr_studies' in sql and args==(OWNER,)
        return []
    monkeypatch.setattr(app.db,'query',query)
    assert client.get('/api/bishop/rr-study').status_code==403
    response=client.get('/api/bishop/rr-study',headers={'X-Telegram-Init-Data':make_init_data()})
    assert response.status_code==200 and response.json()['summary']['cohort']==0
    assert set(response.json()['summary']['variants'])=={'1','2','3'}
    assert calls

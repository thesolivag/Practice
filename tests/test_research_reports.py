import json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
from fastapi import FastAPI,Header,HTTPException
from fastapi.testclient import TestClient
import research_reports as reports

SETUP={'id':'setup','pair':'EURUSD','strategy':'recognition_RR','confirmation':'breakout','tf':'H1','side':'BUY','decision':'2026-02-18T10:00:00Z','cutoff':'2026-02-20T10:00:00Z','entry':1.1,'stop':1.09,'targets':[{'label':'1R','price':1.11,'order_id':'order'}]}
class MemoryDB:
    def __init__(self):self.rows={}
    def execute(self,sql,args):
        uid,key,payload,created,updated=args
        assert 'ON DUPLICATE KEY' in sql
        old=self.rows.get((uid,key));self.rows[(uid,key)]={'setup_id':key,'payload':payload,'created_at':old['created_at'] if old else created,'updated_at':updated}
    def query(self,sql,args):
        assert 'WHERE user_id=%s' in sql
        return [r for (uid,key),r in self.rows.items() if uid==args[0] and (len(args)==1 or key==args[1])]
@pytest.fixture
def client(monkeypatch):
    def selected(key):
        if key!='setup':raise HTTPException(404,'Missing')
        return SETUP
    monkeypatch.setattr(reports,'selected',selected)
    def user(x_user:int|None=Header(None)):
        if not x_user:raise HTTPException(403,'Login required')
        return {'id':x_user}
    app=FastAPI();reports.register_routes(app,user,MemoryDB());return TestClient(app)

def test_private_reports_persist_update_and_export(client):
    a={'X-User':'1'};b={'X-User':'2'}
    body={'assessments':{'bias':'wrong','entry':'correct'},'notes':'Daily candle did not close above the level','expected':'Wait for a close','context_tf':'D','entry_tf':'H1'}
    assert client.put('/api/research-reports/setup',headers=a,json=body).status_code==200
    saved=client.get('/api/research-reports/setup',headers=a).json()
    assert saved['report']['assessments']==body['assessments']
    assert saved['report']['setup']['entry']==1.1
    assert client.get('/api/research-reports/setup',headers=b).json() is None
    assert client.get('/api/research-reports',headers=b).json()=={'reports':[]}
    assert client.put('/api/research-reports/setup',headers=b,json={'notes':'Different assessment'}).status_code==200
    assert client.get('/api/research-reports/setup',headers=a).json()['report']['notes']==body['notes']
    body['notes']='Updated';assert client.put('/api/research-reports/setup',headers=a,json=body).status_code==200
    allrows=client.get('/api/research-reports',headers=a).json()['reports'];assert len(allrows)==1;assert allrows[0]['report']['notes']=='Updated'
    assert 'result' not in allrows[0]['report']['setup']['targets'][0]

@pytest.mark.parametrize('body',[{}, {'user_id':2,'notes':'Spoof'}, {'assessments':{'bias':'WIN'}},{'assessments':[]},{'notes':'x'*4001},{'notes':4},{'notes':'x','review_clock':1},{'notes':'x','outcomes_revealed':'yes'},{'notes':'x','context_tf':'M1'}])
def test_invalid_reports(client,body):assert client.put('/api/research-reports/setup',headers={'X-User':'1'},json=body).status_code==422

def test_auth_and_unknown_setup(client):
    for route in ['/api/research-reports','/api/research-reports/setup']:assert client.get(route).status_code==403
    assert client.put('/api/research-reports/setup',json={'notes':'x'}).status_code==403
    assert client.put('/api/research-reports/missing',headers={'X-User':'1'},json={'notes':'x'}).status_code==404

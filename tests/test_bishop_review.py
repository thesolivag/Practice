"""Research review: auth, closed-bar clock boundaries and outcome isolation."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
import bishop_review as review

@pytest.fixture
def client(monkeypatch):
    e={'id':'test','pair':'EURUSD','strategy':'recognition_RR','confirmation':'breakout','tf':'H1','side':'BUY','decision':'2026-02-18T10:00:00Z','cutoff':'2026-02-19T10:00:00Z','highlight':True,'targets':[{'price':1.2,'result':{'outcome':'LOSS'}}],'flow':{'plans':[{'future':True}],'status':'FINISHED','timeline':[{'at':'2026-02-18T09:00:00Z'},{'at':'2026-02-18T11:00:00Z'}]}}
    monkeypatch.setattr(review,'archive',lambda:{'entries':[e],'notice':'test','source_run':'123'})
    monkeypatch.setattr(review,'lookup',lambda:{'test':e})
    now=review.epoch(e['decision']);rows=[{'time':now-7200,'end':now-3600,'available_at':now-3600},{'time':now-3600,'end':now,'available_at':now},{'time':now,'end':now+3600,'available_at':now+3600}]
    monkeypatch.setattr(review,'candles',lambda pair,tf:rows)
    app=FastAPI();review.register_routes(app,lambda:{'id':1})
    return TestClient(app)
def test_hidden_results_and_future_evidence(client):
    a=client.get('/api/research-review').json();assert 'targets' not in a['entries'][0]
    d=client.get('/api/research-review/test').json();assert 'result' not in d['targets'][0];assert len(d['flow']['timeline'])==1;assert 'plans' not in d['flow']
    assert client.get('/api/research-review/test?reveal=true').json()['targets'][0]['result']['outcome']=='LOSS'
    assert 'result' not in client.get('/api/research-review/test').json()['targets'][0]
def test_clock_paging_and_validation(client):
    d=client.get('/api/research-review/test/candles?limit=1').json();assert d['has_more'];assert len(d['candles'])==1
    before=d['candles'][0]['time'];older=client.get(f'/api/research-review/test/candles?before={before}').json();assert len(older['candles'])==1;assert older['candles'][0]['time']<before
    assert client.get('/api/research-review/test/candles?tf=M1').status_code==422
    assert client.get('/api/research-review/test/candles?as_of=1').status_code==422
    assert client.get('/api/research-review/test/candles?limit=10000').status_code==422
    assert client.get('/api/research-review/not-found').status_code==404
    for tf in ['H1','H2','H3','H4','D','W']:
        data=client.get('/api/research-review/test/candles?tf='+tf).json();assert all(b['end']<=data['as_of'] and b['available_at']<=data['as_of'] for b in data['candles'])
def test_requires_auth():
    app=FastAPI()
    def deny():raise HTTPException(401,'Unauthorized')
    review.register_routes(app,deny);c=TestClient(app)
    for route in ['/api/research-review','/api/research-review/test','/api/research-review/test/candles']:
        assert c.get(route).status_code==401

def test_broker_aggregation_excludes_unfinished_h4():
    from bishop.v2.types import Bar,Instrument
    from bishop.v2.aggregation import aggregate
    from datetime import datetime,timedelta,timezone
    start=datetime(2026,2,18,6,tzinfo=timezone.utc)
    bars=tuple(Bar('EURUSD','H1',start+timedelta(hours=i),start+timedelta(hours=i+1),100,110,90,105,start+timedelta(hours=i+1),'test','0') for i in range(4))
    result=aggregate(bars,'H4',calendar='fx_ny_v1',anchor='ny17_wall_v2',as_of=start+timedelta(hours=3))
    assert not result['bars']
    assert len(aggregate(bars,'H4',calendar='fx_ny_v1',anchor='ny17_wall_v2')['bars'])==1

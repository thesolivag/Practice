import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
import journal_replay as J
from slk import replay_cache as R,tenancy


def bars(lo,count):return [[lo+i*3600,1.,2.,.5,1.5] for i in range(count)]


def test_cache_codec_bounded_and_finite():
    values=bars(0,744)
    assert R.decode(R.encode(values))==values
    with pytest.raises(ValueError):R.encode(values+bars(744*3600,1))
    with pytest.raises(ValueError):R.encode([[1,1,2,.5,1]])
    with pytest.raises(ValueError):R.encode([[0,1,float('nan'),.5,1]])
    with pytest.raises(ValueError):R.decode(__import__('zlib').compress(b' '*200000))


def test_cache_actual_coverage_and_bounds():
    rows=bars(0,10)
    db=SimpleNamespace(query=lambda *a:[dict(payload=R.encode(rows),covered_until=36000)])
    assert R.available(db,'DVR25',0,72000,now=72000) is None
    assert R.available(db,'DVR25',0,72000,now=72000,required_until=18000)==rows
    with pytest.raises(ValueError):R.available(db,'DVR25',0,513*3600,now=513*3600)


def test_journal_validation_does_not_accept_oversized_or_arbitrary_fields():
    assert J.clean_journal({'pair':'eurusd','notes':'ok'})['pair']=='EURUSD'
    for body in ({'notes':'x'*2001},{'entry':float('inf')},{'entry':-1},{'result_r':True},{'user_id':42},{'notes':{}},{'side':'HOLD'}):
        with pytest.raises(HTTPException):J.clean_journal(body)
    with pytest.raises(HTTPException):J.clean_journal({'source_id':1},partial=True)


def test_owned_source_scope_and_manual_watch_guard():
    calls=[]
    def query(sql,args):
        calls.append((sql,args,tenancy.USER.get()))
        if 'manual_alerts' in sql:return []
        return [dict(id=1,pair='EURUSD',confirm_time=100,created_at=100)]
    db=SimpleNamespace(query=query)
    assert J.source(db,42,'bias',1,now=1000)['anchor']==100
    assert calls[-1][2]==42
    with pytest.raises(HTTPException) as err:J.source(db,42,'watch',1,now=1000)
    assert err.value.status_code==404
    assert calls[-1][1]==(1,42)
    assert tenancy.USER.get() is None


def test_replay_prefix_step_owner_and_tamper(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','replay-test-secret')
    now=2000000;anchor=now//3600*3600-24*3600
    values=bars(anchor-7*86400,200)
    monkeypatch.setattr(J.time,'time',lambda:now)
    monkeypatch.setattr(R,'available',lambda *a,**kw:{'rows':values,'provider':'deriv'})
    src={'kind':'bias','id':1,'pair':'DVR25','anchor':anchor}
    first=J.replay_view(None,42,src)
    assert first['bars'] and all(b['time']+3600<=anchor for b in first['bars'])
    cursor=J._read_token(first['cursor'],42)
    stepped=J.replay_view(None,42,src,cursor,2)
    assert len(stepped['bars'])==len(first['bars'])+2
    assert max(b['time'] for b in stepped['bars'])+3600==anchor+7200
    with pytest.raises(HTTPException):J._read_token(first['cursor'],43)
    with pytest.raises(HTTPException):J._read_token(first['cursor']+'x',42)
    monkeypatch.setattr(J.time,'time',lambda:now+3601)
    with pytest.raises(HTTPException):J._read_token(first['cursor'],42)


def test_journal_delete_is_explicitly_owned():
    calls=[]
    db=SimpleNamespace(execute=lambda sql,args:calls.append((sql,args)) or 0)
    app=FastAPI();J.register_routes(app,lambda:{'id':42},db)
    with TestClient(app) as c:
        assert c.delete('/api/journal/1').status_code==404
    assert 'user_id=%s' in calls[0][0] and calls[0][1]==(1,42)


def test_bad_cursor_encoding_is_forbidden_not_server_error(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','key')
    for value in ('*.x','%%%%.x','a.x','_w.x'):
        with pytest.raises(HTTPException) as e:J._read_token(value,42)
        assert e.value.status_code==403
    assert J.epoch('2026-10-24T10:00:00+01:00')==J.epoch('2026-10-24T09:00:00Z')


def test_journal_user_quota_rolls_back_and_closes(monkeypatch):
    events=[]
    class Conn:
        def cursor(self):return self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,args=None):events.append((sql,args))
        def fetchone(self):return {'ok':1,'n':200}
        def begin(self):events.append('begin')
        def commit(self):events.append('commit')
        def rollback(self):events.append('rollback')
        def close(self):events.append('close')
    with pytest.raises(HTTPException) as e:J.write_journal(SimpleNamespace(connect=Conn),42,{'notes':''})
    assert e.value.status_code==422 and 'rollback' in events and 'commit' not in events and events[-1]=='close'
    assert any(isinstance(x,tuple) and 'WHERE user_id=%s' in x[0] and x[1]==(42,) for x in events)


@pytest.mark.parametrize("unit",["s","ms","us","ns"])
def test_publisher_excludes_forming_and_records_actual_coverage(monkeypatch,unit):
    import pandas as pd
    from slk import store
    at=int(pd.Timestamp('2026-10-24T05:00Z').timestamp())
    frame=pd.DataFrame({'open':[1.]*7,'high':[2.]*7,'low':[.5]*7,'close':[1.5]*7},index=pd.date_range('2026-10-24T00:00Z',periods=7,freq='h'))
    frame.index=frame.index.as_unit(unit)
    monkeypatch.setattr(store,'Pair',lambda *a:SimpleNamespace(frame=lambda:frame,src='deriv'))
    written=[]
    monkeypatch.setattr(R,'_publish_chunk',lambda conn,pair,name,rows,covered,now,provider:written.append((rows,covered)))
    class Conn:
        def cursor(self):return self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):pass
        def fetchone(self):return {'ok':1}
        def close(self):pass
    db=SimpleNamespace(connect=Conn,query=lambda *a:[dict(id=1,pair='DVR25',lo=at-5*3600,hi=at)],execute=lambda *a:None)
    assert R.publish(db,now=at)['processed']==1
    assert written[0][1]==at and max(r[0] for r in written[0][0])==at-3600


def test_replay_never_combines_different_broker_months():
    jan=J.epoch('2026-01-31T00:00:00Z');feb=J.epoch('2026-02-01T00:00:00Z')
    def query(sql,args):
        p='ctrader' if args[1]=='2026-01' else 'dukascopy'
        t=jan if p=='ctrader' else feb
        return [dict(payload=R.encode(bars(t,1)),covered_until=t+3600,provider=p)]
    assert R.available(SimpleNamespace(query=query),'EURUSD',jan,feb+3600,now=feb+7200,required_until=feb+3600) is None


def test_enum_json_types_reject_with_validation_error():
    for key in ('source_kind','side','outcome'):
        for bad in ([],{}):
            with pytest.raises(HTTPException) as error:J.clean_journal({key:bad})
            assert error.value.status_code==422
    with pytest.raises(HTTPException) as error:J.source(None,42,[],1)
    assert error.value.status_code==422

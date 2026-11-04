"""Distinct price/alert replay, bounded calendars, and clock-preserving switching."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
import journal_replay as J
from slk import replay_cache


def hourly(start,count):
    return [[start+i*3600,1+i*.001,2+i*.001,.5+i*.001,1.5+i*.001] for i in range(count)]


@pytest.fixture
def replay(monkeypatch):
    now=J.epoch('2026-10-26T12:00:00Z');anchor=J.epoch('2026-10-20T10:30:00Z')
    rows=hourly(anchor//3600*3600-14*86400,21*24)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','price-replay-tests')
    monkeypatch.setattr(J.time,'time',lambda:now)
    monkeypatch.setattr(replay_cache,'available',lambda *a,**kw:{'rows':rows,'provider':'deriv'})
    uid=[42];calls=[]
    def query(sql,args=None):
        calls.append((sql,args))
        if 'replay_requests' in sql:return [{'status':'READY','updated_at':now}]
        if 'manual_alert_events' in sql and args==(7,42):
            return [dict(id=7,user_id=42,watch_id=99,pair='DVR25',event_time=anchor,model='breakout',timeframe='H1',side='BUY',level=1.75,
                         event_payload=json.dumps({'close':1.8,'matches':[{'pattern_level':1.7,'reference_level':1.6}]}))]
        if 'manual_alerts' in sql and args==(99,42):
            return [dict(id=99,pair='DVR25',event_time=anchor+3600,level=999)]
        return []
    app=FastAPI();J.register_routes(app,lambda:{'id':uid[0]},SimpleNamespace(query=query))
    with TestClient(app) as client:yield SimpleNamespace(client=client,now=now,anchor=anchor,rows=rows,uid=uid,calls=calls)


def test_price_replay_requires_no_alert_or_journal_and_hides_future(replay):
    c=replay.client
    r=c.post('/api/replay/open',json={'mode':'price','pair':'DVR25','start':replay.anchor,'timeframe':'H1'})
    assert r.status_code==200,r.text
    data=r.json()
    assert data['mode']=='price' and data['event'] is None and data['markers']==[]
    assert data['clock']==data['anchor']==replay.anchor
    assert data['bars'] and all(b['end']<=replay.anchor for b in data['bars'])
    assert not any('manual_alert' in sql or 'trade_journal' in sql or 'FROM bias' in sql or 'FROM entries' in sql for sql,_ in replay.calls)
    assert len(data['bars'])<=14*24


def test_timeframe_switch_keeps_clock_and_never_aggregates_future_prices(replay):
    c=replay.client
    data=c.post('/api/replay/open',json={'mode':'price','pair':'DVR25','start':replay.anchor}).json()
    replay.rows[-1][2]=1e8
    for tf in ('H4','H1','D','W','H3','H2'):
        r=c.post('/api/replay/timeframe',json={'cursor':data['cursor'],'timeframe':tf})
        assert r.status_code==200,r.text
        data=r.json()
        assert data['clock']==replay.anchor and data['timeframe']==tf
        assert all(b['end']<=data['clock'] and b['high']<1e8 for b in data['bars'])
    data=c.post('/api/replay/step',json={'cursor':data['cursor'],'count':2}).json()
    assert data['clock']>replay.anchor and data['timeframe']=='H2'
    assert data['clock']<=replay.anchor+4*3600
    reset=c.post('/api/replay/open',json={'mode':'price','pair':'DVR25','start':replay.anchor,'timeframe':'H2'}).json()
    assert reset['clock']==replay.anchor


def test_signed_cursors_are_user_mode_pair_timeframe_and_clock_bound(replay):
    c=replay.client
    data=c.post('/api/replay/open',json={'mode':'price','pair':'DVR25','start':replay.anchor}).json()
    cursor=data['cursor']
    replay.uid[0]=43
    assert c.post('/api/replay/step',json={'cursor':cursor}).status_code==403
    replay.uid[0]=42
    p=J._read_token(cursor,42)
    for key,value in (('mode','alert'),('pair','EURUSD'),('timeframe','H4'),('revealed',replay.now+3600)):
        tampered={**p,key:value}
        encoded=__import__('base64').urlsafe_b64encode(json.dumps(tampered,separators=(',',':')).encode()).decode().rstrip('=')
        unsigned=encoded+'.'+cursor.split('.')[1]
        assert c.post('/api/replay/step',json={'cursor':unsigned}).status_code==403
    assert c.post('/api/replay/step',json={'cursor':cursor,'count':True}).status_code==422
    assert c.post('/api/replay/timeframe',json={'cursor':cursor,'timeframe':'H4','start':replay.now}).status_code==422
    assert c.post('/api/replay/step',json={'cursor':cursor,'count':25}).status_code==422


@pytest.mark.parametrize('body',[
    {'mode':'price','pair':'NOTREAL','start':'2026-10-20T10:00:00Z'},
    {'mode':'price','pair':'DVR25','start':'2026-10-27T10:00:00Z'},
    {'mode':'price','pair':'DVR25','start':'2010-01-01T00:00:00Z'},
    {'mode':'price','pair':'DVR25','start':'2026-10-20T10:00:00'},
    {'mode':'price','pair':'DVR25','start':True},
    {'mode':'price','pair':'DVR25','start':float('inf')},
    {'mode':'price','pair':'DVR25','start':'2026-10-20T10:00:00Z','timeframe':'M5'},
    {'mode':'price','pair':'DVR25','start':'2026-10-20T10:00:00Z','kind':'bias','id':1},
    {'kind':'bias','id':1,'start':'2026-10-20T10:00:00Z'},
])
def test_price_and_alert_input_scopes_are_distinct_and_bounded(replay,body):
    # JSON cannot encodeInfinity; exercise the validator directly for that case.
    if body.get('start')==float('inf'):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):J.price_source(body,now=replay.now)
    else:assert replay.client.post('/api/replay/open',json=body).status_code==422


def test_alert_event_replay_uses_immutable_owned_event_not_latest_watch(replay):
    c=replay.client
    data=c.post('/api/replay/open',json={'kind':'watch_event','id':7,'timeframe':'H2'}).json()
    assert data['mode']=='alert' and data['clock']==replay.anchor
    assert data['event']['kind']=='watch_event' and data['event']['snapshot'] is True
    assert data['event']['model']=='breakout'
    assert {m['price'] for m in data['markers']}=={1.75,1.8,1.7,1.6}
    assert all(m['time']==replay.anchor for m in data['markers'])
    assert not any('FROM manual_alerts ' in sql for sql,_ in replay.calls)
    assert c.post('/api/replay/open',json={'kind':'watch_event','id':8}).status_code==404
    legacy=c.post('/api/replay/open',json={'kind':'watch','id':99}).json()
    assert legacy['anchor']==replay.anchor+3600 and legacy['event']['snapshot'] is False and legacy['markers']==[]


def test_aggregation_omits_incomplete_or_gapped_bins_before_and_after_switch():
    begin=J.epoch('2026-10-24T00:00:00Z')
    rows=hourly(begin,12)
    assert len(J.aggregate_replay(rows,'H4','DVR25',begin+6*3600))==1
    missing=[r for r in rows if r[0]!=begin+2*3600]
    bars=J.aggregate_replay(missing,'H4','DVR25',begin+8*3600)
    assert len(bars)==1 and bars[0]['time']==begin+4*3600
    assert all(b['end']<=begin+8*3600 for b in bars)
    # A month/source window starting partway into H4 cannot manufacture its open.
    assert J.aggregate_replay(rows[1:4],'H4','DVR25',begin+4*3600)==[]


def test_deriv_and_ic_crypto_have_true_weekend_daily_weekly_bars():
    for pair,start in (('DVR25','2026-10-19T00:00:00Z'),('BTCUSD','2026-10-18T21:00:00Z')):
        begin=J.epoch(start)
        rows=hourly(begin,7*24)
        d=J.aggregate_replay(rows,'D',pair,begin+7*86400)
        w=J.aggregate_replay(rows,'W',pair,begin+7*86400)
        assert len(d)==7 and len(w)==1
        assert w[0]['time']==begin and w[0]['end']==begin+7*86400
        assert J.aggregate_replay(rows,'W',pair,begin+7*86400-1)==[]


def test_fx_daily_and_weekly_use_new_york_17_close():
    begin=J.epoch('2026-10-18T21:00:00Z') # Sunday17NY, Monday wall-calendar
    rows=hourly(begin,120)
    days=J.aggregate_replay(rows,'D','EURUSD',begin+120*3600)
    weeks=J.aggregate_replay(rows,'W','EURUSD',begin+120*3600)
    assert len(days)==5 and all(b['time']%86400==21*3600 for b in days)
    assert len(weeks)==1 and weeks[0]['end']==J.epoch('2026-10-23T21:00:00Z')
    assert J.aggregate_replay(rows,'W','EURUSD',begin+120*3600-1)==[]


def test_ic_crypto_weekend_h4_keeps_ny_bucket_alignment():
    start=J.epoch('2026-10-24T21:00:00Z') # Saturday17NY, nextwallmidnight
    rows=hourly(start,4)
    bars=J.aggregate_replay(rows,'H4','BTCUSD',start+4*3600)
    assert len(bars)==1 and bars[0]['time']==start
    assert J.aggregate_replay(rows,'H4','BTCUSD',start+4*3600-1)==[]


def test_crypto_dst_ambiguous_h4_edges_are_omitted_not_guessed():
    start=J.epoch('2026-11-01T00:00:00Z')
    rows=hourly(start,16)
    result=J.aggregate_replay(rows,'H4','BTCUSD',start+16*3600)
    # NY01:00 occurs twice; scanner rejects ambiguous local nominal edges too.
    assert all(b['time'] not in (J.epoch('2026-11-01T05:00:00Z'),J.epoch('2026-11-01T06:00:00Z')) for b in result)
    assert all(b['end']<=start+16*3600 for b in result)


def test_sources_expose_owned_immutable_watch_id_for_direct_replay(monkeypatch):
    now=J.epoch('2026-10-26T12:00:00Z');anchor=now-3600
    monkeypatch.setattr(J.time,'time',lambda:now)
    calls=[]
    def query(sql,args=None):
        calls.append((sql,args))
        if 'manual_alert_events' in sql:
            assert args==(42,)
            return [dict(id=7,user_id=42,watch_id=99,pair='DVR25',event_time=anchor)]
        return []
    app=FastAPI();J.register_routes(app,lambda:{'id':42},SimpleNamespace(query=query))
    with TestClient(app) as c:
        rows=c.get('/api/replay/sources').json()
        assert rows==[dict(kind='watch_event',id=7,watch_id=99,pair='DVR25',anchor=anchor,label='DVR25 · watch_event #7')]


def test_history_route_reauthorizes_cursor_and_source(replay):
    c=replay.client
    opened=c.post('/api/replay/open',json={'kind':'watch_event','id':7}).json()
    cursor=opened['cursor']
    reply=c.post('/api/replay/history',json={'cursor':cursor,'before':replay.anchor})
    assert reply.status_code==200 and reply.json()['clock']==replay.anchor
    assert all(b['end']<=replay.anchor for b in reply.json()['bars'])
    assert c.post('/api/replay/history',json={'cursor':cursor,'pair':'EURUSD'}).status_code==422
    replay.uid[0]=43
    assert c.post('/api/replay/history',json={'cursor':cursor}).status_code==403
    replay.uid[0]=42
    replay.calls.clear()
    c.post('/api/replay/history',json={'cursor':cursor})
    assert any('manual_alert_events' in sql and args==(7,42) for sql,args in replay.calls)

"""Paging and rolling replay preserve closed-bar and resource boundaries."""
from types import SimpleNamespace
import sys
from pathlib import Path
import pytest
from fastapi import HTTPException
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
import journal_replay as J
from slk import replay_cache as R


def epoch(value):return J.epoch(value)
def rows(lo,hi):return [[t,1.,2.,.5,1.5] for t in range(lo//3600*3600,hi,3600)]


@pytest.fixture
def history(monkeypatch):
    now=epoch('2026-10-27T12:00:00Z');anchor=epoch('2026-09-01T00:00:00Z');calls=[]
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','history-test')
    monkeypatch.setattr(J.time,'time',lambda:now)
    def cache(db,pair,lo,hi,*a,**kw):
        calls.append((lo,hi,kw))
        assert hi-lo<=R.MAX_BARS*3600
        # Deliberately return future/out-of-window data to test API filtering.
        return {'rows':rows(lo-3600,hi+3600),'provider':'deriv'}
    monkeypatch.setattr(R,'available',cache)
    db=SimpleNamespace(query=lambda *a:[{'status':'QUEUED','updated_at':now}])
    src={'mode':'price','pair':'DVR25','anchor':anchor,'markers':[],'event':None}
    return SimpleNamespace(now=now,anchor=anchor,calls=calls,src=src,db=db)


def test_paging_does_not_reveal_future_or_advance_clock(history):
    h=history
    opened=J.replay_view(h.db,42,h.src,timeframe='H4')
    cursor=J._read_token(opened['cursor'],42)
    before=opened['bars'][0]['time']
    page=J.replay_history(h.db,42,h.src,cursor,before)
    assert page['available'] and page['bars']
    assert page['clock']==h.anchor
    assert all(b['time']<before and b['end']<=before for b in page['bars'])
    assert page['before']==page['bars'][0]['time']<before
    assert page['provider']=='deriv'
    following=J.replay_history(h.db,42,h.src,cursor,page['before'])
    assert {b['time'] for b in following['bars']}.isdisjoint(b['time'] for b in page['bars'])
    assert following['before']<page['before']


def test_weekly_initial_context_and_rolling_step_beyond_seven_days(history):
    h=history
    opened=J.replay_view(h.db,42,h.src,timeframe='W')
    assert opened['window']['context_days']==21
    assert len(opened['bars'])>=2 and not opened['finished']
    initial_clock=opened['clock']
    data=opened
    for _ in range(3):
        cursor=J._read_token(data['cursor'],42)
        data=J.replay_view(h.db,42,h.src,cursor,1)
        assert data['clock']>cursor['revealed']
        assert all(b['end']<=data['clock'] for b in data['bars'])
    assert data['clock']>initial_clock+7*86400
    assert J._read_token(data['cursor'],42)['revealed']==data['clock']
    assert all(hi-lo<=R.MAX_BARS*3600 for lo,hi,_ in h.calls)


def test_history_validates_boundary_and_owner(history):
    h=history;opened=J.replay_view(h.db,42,h.src)
    cursor=J._read_token(opened['cursor'],42)
    for value in (True,'2026-01-01',h.anchor+1,0,[],1.5):
        with pytest.raises(HTTPException) as error:J.replay_history(h.db,42,h.src,cursor,value)
        assert error.value.status_code==422
    with pytest.raises(HTTPException) as error:J._read_token(opened['cursor'],99)
    assert error.value.status_code==403


def test_busy_history_does_not_advance_boundary_or_claim_oldest(history,monkeypatch):
    import webapp.replay_loader as loader
    h=history;opened=J.replay_view(h.db,42,h.src);cursor=J._read_token(opened['cursor'],42)
    monkeypatch.setattr(R,'available',lambda *a,**kw:None)
    monkeypatch.setattr(loader,'fill',lambda *a:False)
    queued=[];monkeypatch.setattr(J,'queue_replay',lambda *a:queued.append(a))
    before=opened['bars'][0]['time']
    page=J.replay_history(h.db,42,h.src,cursor,before)
    assert not page['available'] and page['before']==before and page['has_more']
    assert page['clock']==h.anchor and page['status']=='queued' and queued


def test_forex_weekend_page_requires_last_trading_close(monkeypatch):
    now=epoch('2026-10-27T12:00:00Z');clock=epoch('2026-10-25T12:00:00Z')
    monkeypatch.setattr(J.time,'time',lambda:now)
    checks=[]
    def cache(db,pair,lo,hi,*a,**kw):
        checks.append(kw['required_until'])
        return {'rows':[], 'provider':'ctrader'}
    monkeypatch.setattr(R,'available',cache)
    result=J.replay_history(None,42,{'pair':'EURUSD'}, {'revealed':clock,'timeframe':'W'},clock)
    assert result['available']
    assert checks==[epoch('2026-10-23T21:00:00Z')]

"""Separate alert contracts, real pattern input, recurrence and immutable anchors."""
import json
import os
import time
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import pytest
from slk import user_alerts as A


def body(**changes):
    return dict(kind='confirmation',pair='DVR75',models=['breakout','engulfing','fourth_man'],
                timeframes=['M5','H1'],scope='anywhere',repeat='each',**changes)


def row(**changes):
    data=A.validate(body(),100)
    return dict(data,id=1,user_id=42,status='ACTIVE',**changes)


def test_modes_have_distinct_controls_and_anywhere_is_not_a_fake_level():
    schema=A.schema()
    assert {r['value'] for r in schema['confirmation_models']}==A.CONFIRMATIONS
    assert not ({r['value'] for r in schema['price_conditions']}&A.CONFIRMATIONS)
    raw=row();public=A.public_watch(raw)
    assert public['kind']=='confirmation' and public['level'] is None
    assert public['models']==A.MODEL_ORDER and public['scope']=='anywhere'
    assert 'options_json' not in public
    assert all(v['level'] is None for v in A._variants(raw))
    assert len(A._variants(raw))==6
    old=A.validate({'pair':'DVR75','condition':'fourth_man','level':10},100)
    assert A.watch_options(old)['scope']=='level' and A.watch_options(old)['repeat']=='once'


@pytest.mark.parametrize('changes',[
    {'models':[]},{'models':['cisd_v1']},{'timeframes':[]},{'timeframes':['M1']},
    {'timeframes':['M5','M15','M30','M45','H1','H2','H3']},{'level':10},
    {'repeat':'always'},{'scope':'fake'},{'cursors':{'H1':99999}},
    {'condition':'close_above'},{'timeframe':'H1'},{'models':{}},
])
def test_confirmation_contract_rejects_price_fields_and_invalid_selections(changes):
    with pytest.raises(ValueError):A.validate({**body(),**changes},100)


def test_price_contract_requires_price_and_cannot_select_confirmation():
    assert A.validate({'kind':'price','pair':'DVR75','level':10,'condition':'close_above'},100)
    for changes in ({'level':None},{'condition':'fourth_man'},{'models':['breakout']},{'scope':'anywhere'},{'engulfing':True}):
        with pytest.raises(ValueError):A.validate({'kind':'price','pair':'DVR75','level':10,'condition':'close_above',**changes},100)


def test_anywhere_fourth_man_detects_real_geometry_without_level_touch():
    h=pd.DataFrame([(10,16,8,14),(13,15,7,11)],columns=['open','high','low','close'],index=pd.date_range('2026-10-20',periods=2,freq='h',tz='UTC'))
    created=int(h.index[0].timestamp())
    raw={**A.validate({**body(),'models':['fourth_man'],'timeframes':['H1']},created), 'id':1,'user_id':42}
    event=A.evaluate(raw,h,h.index[-1]+pd.Timedelta(hours=1))
    assert event['side']=='BUY' and event['level'] is None and event['scope']=='anywhere'
    assert event['condition']=='fourth_man'
    scoped={**raw,'level':1,'options_json':A._options_json({**A.watch_options(raw),'scope':'level'})}
    assert A.evaluate(scoped,h,h.index[-1]+pd.Timedelta(hours=1)) is None
    assert 'Watched price' not in A.message(raw,event)


def test_tied_models_and_timeframes_are_grouped_with_actual_directions(monkeypatch):
    def one(variant,source,now,cache=None):
        return [dict(time=200,condition=variant['condition'],timeframe=variant['timeframe'],side='SELL' if variant['condition']=='fourth_man' else 'BUY',close=12)]
    monkeypatch.setattr(A,'_evaluate_one',one)
    event=A.evaluate(row(),None,datetime.now(timezone.utc))
    assert len(event['matches'])==6
    assert {m['timeframe'] for m in event['matches']}=={'M5','H1'}
    assert len({(m['condition'],m['timeframe'],m['side']) for m in event['matches']})==6
    text=A.message(row(),event)
    assert 'SELL · 4th man confirmation · H1' in text


def test_missing_timeframe_does_not_advance_its_cursor(monkeypatch):
    raw=row()
    h=pd.DataFrame([(10,12,9,11)],columns=['open','high','low','close'],index=pd.date_range('1970-01-01',periods=1,freq='h',tz='UTC'))
    def one(variant,source,now,cache=None):return [dict(time=200,side='BUY',close=12,condition=variant['condition'],timeframe=variant['timeframe'])]
    monkeypatch.setattr(A,'_evaluate_one',one)
    monkeypatch.setattr(A,'data_fresh',lambda source,*a:source is not None)
    monkeypatch.setattr(A,'complete_bars',lambda *a:[{'end':pd.Timestamp(300,unit='s',tz='UTC')}])
    event,checked,missing=A.evaluate_market(raw,{'hourly':h},datetime.now(timezone.utc),400)
    assert event['timeframe']=='H1' and missing==['M5'] and set(checked)=={'H1'}
    options=A.watch_options(raw);options['cursors']={'H1':200}
    delayed={**raw,'options_json':A._options_json(options),'last_checked':200}
    assert all(v['last_checked']==100 for v in A._variants(delayed) if v['timeframe']=='M5')


@pytest.fixture
def mysql(monkeypatch):
    if not os.environ.get('SLK_TEST_MYSQL'):pytest.skip('requires disposable MySQL8')
    from slk import db
    monkeypatch.setenv('DATABASE_URL',os.environ['SLK_TEST_MYSQL']);monkeypatch.delenv('DATABASE_PASSWORD',raising=False)
    db._conn=None;db.apply_schema()
    uid=time.time_ns()
    yield db,uid
    db.execute('DELETE FROM manual_alert_events WHERE user_id IN (%s,%s)',(uid,uid+1))
    db.execute('DELETE FROM manual_alerts WHERE user_id IN (%s,%s)',(uid,uid+1))
    db.execute('DELETE FROM manual_alert_users WHERE user_id IN (%s,%s)',(uid,uid+1))


def test_real_mysql_recurring_ack_retry_cursors_and_frozen_replay(mysql):
    db,uid=mysql;now=int(time.time());data=A.validate(body(),now-7200)
    with A.Repository(db) as repo:
        public=repo.create(uid,data)
        stored=repo.query('SELECT * FROM manual_alerts WHERE id=%s AND user_id=%s',(public['id'],uid))[0]
        def event(tf,stamp):return {'time':stamp,'side':'BUY','close':12,'condition':'breakout','timeframe':tf,'reference_level':11,'pattern_level':11}
        early=event('M5',now-60)
        assert repo.trigger(stored,early)
        triggered=repo.query('SELECT * FROM manual_alerts WHERE id=%s',(stored['id'],))[0]
        assert repo.deliver(triggered,lambda *a,**kw:False,now) is False
        assert repo.query('SELECT * FROM manual_alert_events WHERE user_id=%s',(uid,))==[]
        assert repo.deliver(triggered,lambda *a,**kw:True,now+1)
        current=repo.query('SELECT * FROM manual_alerts WHERE id=%s',(stored['id'],))[0]
        assert current['status']=='ACTIVE'
        assert A.watch_options(current)['cursors']=={'M5':early['time']}
        assert not repo.trigger(current,early)
        # H1 was unavailable then: its older unseen event is still eligible.
        delayed=event('H1',now-120)
        assert repo.trigger(current,delayed)
        triggered=repo.query('SELECT * FROM manual_alerts WHERE id=%s',(stored['id'],))[0]
        assert repo.deliver(triggered,lambda *a,**kw:True,now+2)
        events=repo.query('SELECT * FROM manual_alert_events WHERE user_id=%s ORDER BY id',(uid,))
        assert len(events)==2 and events[0]['event_time']==early['time'] and events[1]['event_time']==delayed['time']
        assert json.loads(events[0]['event_payload'])['reference_level']==11
        current=repo.query('SELECT * FROM manual_alerts WHERE id=%s',(stored['id'],))[0]
        assert current['last_checked']==early['time']
        assert A.watch_options(current)['cursors']=={'M5':early['time'],'H1':delayed['time']}
        assert repo.list(uid+1)==[]
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
    import journal_replay as J
    assert J.source(db,uid,'watch_event',events[0]['id'],now=now+3)['anchor']==early['time']
    from fastapi import HTTPException
    with pytest.raises(HTTPException):J.source(db,uid+1,'watch_event',events[0]['id'],now=now+3)


def test_real_mysql_normal_price_crossing_has_immutable_quote_event(mysql):
    db,uid=mysql;now=int(time.time())
    with A.Repository(db) as repo:
        row=repo.create(uid,A.validate({'kind':'price','pair':'DVR75','condition':'crossing','level':10},now-100))
        assert repo.observe_quote(row,9,now-20,now) is None
        fired=repo.observe_quote(row,11,now-10,now)
        assert fired and repo.deliver(fired,lambda *a,**kw:True,now)
        recorded=repo.query('SELECT * FROM manual_alert_events WHERE user_id=%s',(uid,))
        assert len(recorded)==1 and recorded[0]['timeframe']=='QUOTE' and recorded[0]['model']=='crossing'
        assert repo.query('SELECT status FROM manual_alerts WHERE id=%s',(row['id'],))[0]['status']=='FIRED'


def test_real_mysql_existing_table_migration_is_idempotent(mysql):
    db,uid=mysql;schema='slk_migration_'+str(uid)
    conn=db.connect()
    try:
        with conn.cursor() as c:c.execute('CREATE DATABASE '+schema)
        conn.select_db(schema)
        with conn.cursor() as c:
            c.execute('CREATE TABLE manual_alerts (id BIGINT PRIMARY KEY,note VARCHAR(300))')
            db.migrate_global_cursor(c);db.migrate_global_cursor(c)
            c.execute("SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='manual_alerts' AND COLUMN_NAME='options_json'")
            assert c.fetchall()==[{'IS_NULLABLE':'YES'}]
            c.execute('INSERT INTO manual_alerts (id,note,options_json) VALUES (1,%s,%s)',('preserved','{}'))
            db.migrate_global_cursor(c)
            c.execute('SELECT note,options_json FROM manual_alerts WHERE id=1')
            assert c.fetchone()=={'note':'preserved','options_json':'{}'}
    finally:
        with conn.cursor() as c:c.execute('DROP DATABASE IF EXISTS '+schema)
        conn.close()

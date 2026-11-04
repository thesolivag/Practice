"""Whole application login/watch/journal isolation against disposable MySQL only."""
import io
import os
import sys
import time
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'webapp'))
import app
from tests.test_webapp import TOKEN,make_init_data,hdr

pytestmark=pytest.mark.skipif(not os.environ.get('SLK_TEST_MYSQL'),reason='requires disposable MySQL8')


def test_browser_extension_same_telegram_account_and_tenant_isolation(monkeypatch):
    from slk import db
    monkeypatch.setenv('DATABASE_URL',os.environ['SLK_TEST_MYSQL'])
    monkeypatch.delenv('DATABASE_PASSWORD',raising=False)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('TELEGRAM_CHAT_ID','777000111')
    monkeypatch.setenv('APP_ORIGIN','https://testserver')
    db._conn=None;db.apply_schema()
    uid=time.time_ns();other=uid+1
    tg=hdr(make_init_data(user_id=uid));tg_other=hdr(make_init_data(user_id=other))
    with TestClient(app.app,base_url='https://testserver') as browser:
        assert browser.get('/api/settings').status_code==403
        code=browser.post('/api/auth/pair-code',headers=tg,json={'client':'browser'})
        assert code.status_code==200,code.text
        redeemed=browser.post('/api/auth/redeem',headers={'Origin':'https://testserver'},json={'code':code.json()['code'],'client':'browser'})
        assert redeemed.status_code==200,redeemed.text
        assert 'token' not in redeemed.json()
        assert 'HttpOnly' in redeemed.headers['set-cookie'] and 'Secure' in redeemed.headers['set-cookie']
        csrf={'Origin':'https://testserver','X-CSRF-Token':redeemed.json()['csrf']}
        assert browser.get('/api/auth/session').json()['user']['id']==uid
        assert browser.post('/api/settings',json={'pairs':'DVR75'}).status_code==403
        assert browser.post('/api/settings',headers=csrf,json={'pairs':'DVR75'}).status_code==200
        assert browser.get('/api/settings',headers=tg).json()['pairs']=='DVR75'
        assert browser.post('/api/entries/1/approve',headers=csrf).status_code==403
        watch=browser.post('/api/alerts',headers=csrf,json={'pair':'DVR75','condition':'close_above','timeframe':'M5','level':3000})
        assert watch.status_code==200,watch.text
        ident=watch.json()['id']
        assert any(r['id']==ident for r in browser.get('/api/alerts',headers=tg).json())
        assert browser.get('/api/alerts',headers=tg_other).json()==[]
        assert browser.post(f'/api/alerts/{ident}/cancel',headers=tg_other).status_code==404
        note=browser.post('/api/journal',headers=csrf,json={'source_kind':'manual','pair':'DVR75','side':'BUY','entry':3000,'stop':2990,'target':3020,'notes':'manual result'})
        assert note.status_code==200,note.text
        note_id=note.json()['id']
        assert browser.get('/api/journal',headers=tg_other).json()==[]
        assert browser.put(f'/api/journal/{note_id}',headers=tg_other,json={'notes':'intrusion'}).status_code==404
        assert browser.post('/api/replay/open',headers=csrf,json={'kind':'watch','id':ident}).status_code==409
        pair=browser.post('/api/auth/pair-code',headers=tg,json={'client':'extension'}).json()
        ext_origin='chrome-extension://'+'a'*32
        ext=browser.post('/api/auth/redeem',headers={'Origin':ext_origin},json={'code':pair['code'],'client':'extension'})
        assert ext.status_code==200,ext.text
        bearer={'Authorization':'Bearer '+ext.json()['token']}
        assert browser.get('/api/settings',headers=bearer).status_code==403
        assert browser.get('/api/settings/schema',headers=bearer).status_code==200
        assert browser.get('/api/alerts',headers=bearer).status_code==200
        assert browser.get('/api/journal',headers=bearer).status_code==403
        assert browser.post('/api/auth/pair-code',headers=bearer,json={}).status_code==403
        assert browser.post('/api/alerts',headers={**bearer,'X-Telegram-Init-Data':'invalid'},json={}).status_code==403
        sid=redeemed.json()['session_id']
        assert browser.delete('/api/auth/sessions/'+sid,headers=tg_other).status_code==200
        assert browser.get('/api/settings').status_code==200
        assert browser.delete('/api/auth/sessions/'+sid,headers=tg).status_code==200
        assert browser.get('/api/settings').status_code==403
        package=browser.get('/extension/download')
        assert package.status_code==200
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            assert 'manifest.json' in archive.namelist()
            assert all(not name.startswith('/') and '..' not in name.split('/') for name in archive.namelist())


def test_shared_replay_publication_and_signed_reveal(monkeypatch,tmp_path):
    from datetime import datetime,timezone
    from slk import db,store,tenancy,replay_cache
    monkeypatch.setenv('DATABASE_URL',os.environ['SLK_TEST_MYSQL'])
    monkeypatch.delenv('DATABASE_PASSWORD',raising=False)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('TELEGRAM_CHAT_ID','777000111')
    db._conn=None;db.apply_schema()
    db.execute('DELETE FROM replay_candles WHERE pair=%s',('DVR25',))
    db.execute('DELETE FROM replay_requests WHERE pair=%s',('DVR25',))
    uid=time.time_ns();now=int(time.time());anchor=(now//3600-48)*3600
    with tenancy.scope(uid):
        ident=db.upsert_bias({'pair':'DVR25','story':'D','side':'BUY','status':'CONFIRMED',
            'tap_time':datetime.fromtimestamp(anchor-86400,timezone.utc).replace(tzinfo=None),
            'confirm_time':datetime.fromtimestamp(anchor,timezone.utc).replace(tzinfo=None)})
    cached=store.Pair('DVR25',str(tmp_path),source='deriv')
    rows=[(t,100.,102.,99.,101.) for t in range((now//3600-30*24)*3600,now//3600*3600,3600)]
    cached.put(rows,store.MONTH);cached.save()
    with TestClient(app.app,base_url='https://testserver') as client:
        headers=hdr(make_init_data(user_id=uid))
        body={'kind':'bias','id':ident}
        response=client.post('/api/replay/open',headers=headers,json=body)
        assert response.status_code==200,response.text
        assert response.json()['available'] is False
        assert replay_cache.publish(db,root=str(tmp_path),now=now)['processed']>=1
        opened=client.post('/api/replay/open',headers=headers,json=body)
        assert opened.status_code==200,opened.text
        data=opened.json();assert data['available'],data
        assert data['bars'] and max(r['time']+3600 for r in data['bars'])<=anchor
        assert 'Deriv' in data['feed']
        advanced=client.post('/api/replay/step',headers=headers,json={'cursor':data['cursor'],'count':1})
        assert advanced.status_code==200,advanced.text
        assert len(advanced.json()['bars'])==len(data['bars'])+1
        denied=client.post('/api/replay/step',headers=hdr(make_init_data(user_id=uid+1)),json={'cursor':data['cursor'],'count':1})
        assert denied.status_code==403

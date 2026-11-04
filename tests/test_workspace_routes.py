from tests.test_webapp import client
import app


def test_private_api_responses_are_not_cached(client):
    response=client.get('/api/auth/session')
    assert response.status_code==403
    assert response.headers['cache-control']=='no-store'


def test_external_watch_timer_auth_idle_and_one_minute_dedupe(client,monkeypatch):
    monkeypatch.setenv('CRON_SECRET','test-cron')
    monkeypatch.delenv('GH_DISPATCH_TOKEN',raising=False)
    state={'n':0,'last':0};calls=[]
    monkeypatch.setattr(app.db,'query',lambda *a:[{'n':state['n']}])
    def execute(sql,args):
        if 'UPDATE settings SET v=' in sql and 'CAST' in sql:
            if state['last']>args[2]:return 0
            state['last']=int(args[0]);return 1
        return 1
    monkeypatch.setattr(app.db,'execute',execute)
    monkeypatch.setattr(app,'run_personal_scan',lambda:calls.append('scan'))
    assert client.get('/cron/alerts?key=wrong').status_code==403
    assert client.get('/cron/alerts?key=test-cron').json()['accepted'] is False
    assert calls==[]
    state['n']=1
    assert client.get('/cron/alerts?key=test-cron').json()['accepted'] is True
    assert client.get('/cron/alerts?key=test-cron').json()['accepted'] is False
    assert calls==['scan']
    state['last']-=60
    assert client.get('/cron/alerts?key=test-cron').json()['accepted'] is True
    assert calls==['scan','scan']


def test_personal_background_worker_releases_lock_on_failure(monkeypatch):
    import threading
    from contextlib import contextmanager
    from slk import jobs,user_alerts
    events=[]
    @contextmanager
    def lease(*a,**kw):
        assert kw['name']=='slk_personal_feed'
        try:yield True
        finally:events.append('release')
    def fail(**kwargs):
        assert kwargs=={'budget_seconds':40,'max_pairs':4}
        events.append('scan');raise RuntimeError('unavailable')
    monkeypatch.setattr(app,'_personal_scan_lock',threading.Lock())
    monkeypatch.setattr(jobs,'feed_lock',lease)
    monkeypatch.setattr(user_alerts,'tick',fail)
    app.run_personal_scan();app.run_personal_scan()
    assert events==['scan','release','scan','release']
    assert not app._personal_scan_lock.locked()


def test_extension_cors_preflight_and_package(client):
    response=client.options('/api/alerts',headers={'Origin':'chrome-extension://'+'a'*32,
        'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type'})
    assert response.status_code==200
    assert response.headers['access-control-allow-origin']=='chrome-extension://'+'a'*32
    assert 'access-control-allow-credentials' not in response.headers
    response=client.options('/api/alerts',headers={'Origin':'https://unrelated.example','Access-Control-Request-Method':'POST'})
    assert 'access-control-allow-origin' not in response.headers
    assert client.get('/extension/download').status_code==200

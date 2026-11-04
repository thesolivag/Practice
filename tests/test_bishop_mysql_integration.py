"""Real MySQL checks against an explicitly named ephemeral Actions database only."""
import os
from urllib.parse import urlparse
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from bishop.paper_store import Store

URL = os.environ.get('BISHOP_TEST_MYSQL_URL', '')
pytestmark = pytest.mark.skipif(not URL, reason='Ephemeral MySQL service not configured')


@pytest.fixture
def stores():
    parsed = urlparse(URL)
    assert parsed.hostname in ('127.0.0.1','localhost') and parsed.path == '/bishop_ci', 'CI-only database required'
    first = Store(mysql_url=URL,mysql_password='',mysql_ca='',migrate=True,delivery_enabled=True)
    with first.transaction():
        for table in ('paper_runs','bias','bias_snapshots','stream_state','entries','orders','events','outbox','job_requests'):
            first._execute(f'DELETE FROM bishop_{table}')
    second = Store(mysql_url=URL,mysql_password='',mysql_ca='',delivery_enabled=True)
    try:
        yield first,second
    finally:
        first.connection.close()
        second.connection.close()


def test_render_read_connection_sees_new_actions_snapshots(stores):
    writer,reader=stores
    assert reader.list('bias_snapshots')==[]
    result=dict(schema='test',scope='BIAS_ONLY',status='COMPUTED_UNVALIDATED',
                as_of='2026-06-24T12:00:00Z',instrument={'symbol':'GBPUSD'},input={},
                policy={'origin_tfs':['D']},coverage={},
                structural_context={'D':dict(state='DIRECTIONAL',side='SELL')})
    writer.persist_result(result,'one')
    assert reader.list('bias_snapshots')[0]['rows'][0]['side']=='SELL'
    result={**result,'as_of':'2026-06-24T13:00:00Z',
            'structural_context':{'D':dict(state='DIRECTIONAL',side='BUY')}}
    writer.persist_result(result,'two')
    assert reader.list('bias_snapshots')[0]['rows'][0]['side']=='BUY'


def test_json_retry_deadline_is_numeric_in_mysql(stores):
    writer,reader=stores
    with writer.transaction():
        writer._put('outbox','future',dict(id='future',status='PENDING',text='paper',next_attempt_at=1030.5))
    assert reader.pending_alerts(now=1030)==[]
    assert reader.pending_alerts(now=1031)[0]['id']=='future'


def test_two_workers_claim_one_notification_under_real_row_lock(stores):
    from bishop.telegram_delivery import deliver_pending
    first,second=stores
    with first.transaction():
        first._put('outbox','shared',dict(id='shared',status='PENDING',text='Bishop paper'))
    barrier=Barrier(2,timeout=10)
    for store in stores:
        original=store.pending_alerts
        def simultaneous(limit,original=original):
            items=original(limit)
            barrier.wait()
            return items
        store.pending_alerts=simultaneous
    calls=[]
    def post(*args,**kwargs):
        calls.append(kwargs['json']['text'])
        return SimpleNamespace(status_code=200,json=lambda:{'ok':True,'result':{'message_id':42}})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(deliver_pending,s,token='dummy-ci-token',chat_id='dummy-chat',post=post) for s in stores]
        results=[f.result(timeout=15) for f in futures]
    assert sum(r['sent'] for r in results)==1 and len(calls)==1
    assert first.list('outbox')[0]['status']=='SENT'

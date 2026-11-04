from types import SimpleNamespace
from bishop.paper_store import Store
from bishop.telegram_delivery import deliver_pending


def queued():
    store = Store(delivery_enabled=True)
    with store.transaction():
        store._put('outbox', 'alert', dict(id='alert', status='PENDING', text='Bishop paper bias'))
    return store


def test_success_is_persisted_and_never_resent():
    store = queued()
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs['json'])
        return SimpleNamespace(status_code=200, json=lambda: {'ok': True, 'result': {'message_id': 7}})
    assert deliver_pending(store, token='bishop', chat_id='owner', post=post)['sent'] == 1
    assert deliver_pending(store, token='bishop', chat_id='owner', post=post)['sent'] == 0
    assert len(calls) == 1
    assert store.list('outbox')[0]['message_id'] == 7


def test_timeout_is_uncertain_and_not_automatically_retried():
    store = queued()
    def post(*args, **kwargs):
        raise TimeoutError('may already have reached Telegram')
    assert deliver_pending(store, token='bishop', chat_id='owner', post=post)['uncertain'] == 1
    assert store.list('outbox')[0]['status'] == 'UNKNOWN'
    assert deliver_pending(store, token='bishop', chat_id='owner', post=post)['uncertain'] == 0


def test_disabled_historical_previews_are_not_delivered():
    store = queued()
    with store.transaction():
        store._put('outbox', 'preview', dict(id='preview', status='DISABLED', text='old'))
    def post(*args, **kwargs):
        return SimpleNamespace(status_code=400, json=lambda: {'ok': False})
    assert deliver_pending(store, token='bishop', chat_id='owner', post=post)['failed'] == 1
    assert store._get('outbox', 'preview')['status'] == 'DISABLED'


def test_reimporting_events_does_not_reset_sent_outbox():
    store = Store(delivery_enabled=True)
    event = dict(id='event', kind='ORDER_FILLED')
    data = dict(schema='test', status='COMPUTED', as_of='2026-06-24T12:00:00Z', instrument={},
                input={}, policy={}, coverage={}, execution_events=[event])
    store.persist_result(data, 'one')
    row = store.list('outbox')[0]
    with store.transaction():
        row['status'] = 'SENT'
        store._put('outbox', row['id'], row)
    store.persist_result({**data, 'as_of': '2026-06-24T13:00:00Z'}, 'two')
    assert store.list('outbox')[0]['status'] == 'SENT'


def test_disabled_history_does_not_hide_pending_delivery():
    store = queued()
    with store.transaction():
        for i in range(501):
            store._put('outbox', f'000-old-{i}', dict(id=f'000-old-{i}', status='DISABLED', text='old'))
    assert [r['id'] for r in store.pending_alerts(1)] == ['alert']


def test_activation_baselines_warmup_and_only_queues_new_events():
    store = Store(delivery_enabled=True)
    old = dict(id='old', kind='ORDER_FILLED', clock={'available_at': '2026-06-23T12:00:00Z'})
    base = dict(schema='test', status='COMPUTED', instrument={}, input={}, policy={}, coverage={})
    store.persist_result({**base, 'as_of': '2026-06-24T12:00:00Z', 'execution_events': [old]}, 'one')
    assert store.pending_alerts() == []
    fresh = dict(id='new', kind='ORDER_FILLED', clock={'available_at': '2026-06-24T12:30:00Z'})
    store.persist_result({**base, 'as_of': '2026-06-24T13:00:00Z', 'execution_events': [old, fresh]}, 'two')
    assert len(store.pending_alerts()) == 1
    assert store.pending_alerts()[0]['text'].startswith('BISHOP · PAPER')


def test_known_rate_limit_is_deferred_and_does_not_starve_ready_alerts(monkeypatch):
    store = queued()
    monkeypatch.setattr('bishop.telegram_delivery.time.time', lambda: 1000)
    def post(*args, **kwargs):
        return SimpleNamespace(status_code=429, json=lambda: {'ok': False, 'parameters': {'retry_after': 30}})
    assert deliver_pending(store, token='bishop', chat_id='owner', post=post)['deferred'] == 1
    assert store.pending_alerts(now=1029) == []
    assert store.pending_alerts(now=1030)[0]['id'] == 'alert'
    with store.transaction():
        store._put('outbox', 'z-ready', dict(id='z-ready', status='PENDING', text='new'))
    assert [r['id'] for r in store.pending_alerts(1, now=1029)] == ['z-ready']

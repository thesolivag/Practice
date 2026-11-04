"""The application must not pick up Kevin's database or Telegram credentials."""
from unittest.mock import patch
import pytest
from bishop import db, runtime


def test_explicit_application_password_does_not_use_shared_password(monkeypatch):
    monkeypatch.setenv('DATABASE_PASSWORD', 'kevin-password')
    url = 'mysql://bishop:url-password@localhost/bishop'
    assert db.parse_url(url, password='')['password'] == 'url-password'
    assert db.parse_url(url, password='bishop-secret')['password'] == 'bishop-secret'
    assert db.parse_url(url)['password'] == 'kevin-password'  # existing collector contract


def test_runtime_refuses_shared_database_fallback(monkeypatch):
    monkeypatch.delenv('BISHOP_DATABASE_URL', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'mysql://kevin:secret@localhost/kevin')
    with pytest.raises(RuntimeError, match='BISHOP_DATABASE_URL'):
        runtime.application_store()


def test_runtime_passes_separate_credentials_without_mutating_environment(monkeypatch):
    monkeypatch.setenv('DATABASE_PASSWORD', 'kevin-password')
    monkeypatch.setenv('BISHOP_DATABASE_URL', 'mysql://bishop:secret@localhost/bishop')
    monkeypatch.setenv('BISHOP_DATABASE_CA', 'bishop-ca')
    monkeypatch.delenv('BISHOP_DATABASE_PASSWORD', raising=False)
    with patch('bishop.paper_store.Store') as store:
        runtime.application_store()
        store.assert_called_once_with(mysql_url='mysql://bishop:secret@localhost/bishop',
                                      mysql_password='', mysql_ca='bishop-ca', migrate=True, delivery_enabled=False)
    assert db.parse_url('mysql://kevin@localhost/kevin')['password'] == 'kevin-password'


def test_hosted_app_refuses_shared_telegram_token(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'kevin-token')
    monkeypatch.delenv('BISHOP_TELEGRAM_BOT_TOKEN', raising=False)
    with pytest.raises(RuntimeError, match='BISHOP_TELEGRAM_BOT_TOKEN'):
        runtime.create_hosted_app()


def test_bias_review_is_authenticated_and_keeps_unknown_clock_pending():
    from fastapi.testclient import TestClient
    from bishop.webapp import create_app
    with TestClient(create_app(local_api_key='owner'), client=('127.0.0.1', 123)) as client:
        assert client.get('/api/bias-review').status_code == 403
        response = client.get('/api/bias-review', headers={'X-Bishop-Owner-Key': 'owner'})
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 40
        assert data['source_charts_reviewed'] == 40
        assert data['source_labels_reviewed'] == 27
        assert all(row['assessment_time'] is None
                   for row in data['items'])
        audusd = next(r for r in data['items'] if r['case_id'] == 'pdf-p25-audusd-sell-1')
        assert audusd['side'] == 'BUY' and audusd['trade_side'] == 'SELL'
        assert audusd['bias_tf'] == 'D'
        assert client.get('/api/source-chart/pdf-p13-eurnzd-sell-1').status_code == 403
        chart = client.get('/api/source-chart/pdf-p13-eurnzd-sell-1', headers={'X-Bishop-Owner-Key': 'owner'})
        assert chart.status_code == 200 and chart.content.startswith(b'\x89PNG')


def test_mysql_uses_fresh_reads_and_reconnects_only_outside_transaction():
    from unittest.mock import MagicMock
    from bishop.paper_store import Store
    connection = MagicMock()
    with patch('bishop.db.connect', return_value=connection):
        store = Store(mysql_url='mysql://bishop@localhost/bishop')
    connection.autocommit.assert_called_once_with(True)
    store._execute('SELECT 1')
    assert connection.ping.call_count == 1
    with store.transaction():
        assert connection.ping.call_count == 2
        store._execute('SELECT 2')
        assert connection.ping.call_count == 2  # no silent reconnect in a transaction
    store._execute('SELECT 3')
    assert connection.ping.call_count == 3

import json
from unittest.mock import patch
from fastapi.testclient import TestClient
from bishop.webapp import create_app
from bishop.dispatch import dispatch_bias, REF, URL


def test_dispatch_is_fixed_to_bishop_branch_and_workflow():
    class Response:
        status=204
        def __enter__(self): return self
        def __exit__(self,*args): pass
    def open_url(request,timeout):
        assert request.full_url==URL and timeout==15
        assert json.loads(request.data)=={'ref':REF}
        assert request.get_header('Authorization')=='Bearer bishop-token'
        return Response()
    assert dispatch_bias('bishop-token',open_url=open_url)['branch']=='claude-bishop-aggressive'


def test_cron_requires_bishop_specific_configuration_and_header(monkeypatch):
    monkeypatch.setenv('GH_DISPATCH_TOKEN','kevin-token')
    monkeypatch.delenv('BISHOP_CRON_ENABLED',raising=False)
    with TestClient(create_app()) as client:
        assert client.post('/cron/tick').status_code==403
        monkeypatch.setenv('BISHOP_CRON_ENABLED','true')
        monkeypatch.setenv('BISHOP_CRON_SECRET','bishop-cron')
        monkeypatch.setenv('BISHOP_GH_DISPATCH_TOKEN','bishop-token')
        with patch('bishop.dispatch.dispatch_bias',return_value={'queued':True}) as dispatch:
            assert client.post('/cron/tick',headers={'X-Bishop-Cron-Key':'wrong'}).status_code==403
            assert not dispatch.called
            assert client.post('/cron/tick',headers={'X-Bishop-Cron-Key':'bishop-cron'}).json()=={'queued':True}
            dispatch.assert_called_once_with('bishop-token')

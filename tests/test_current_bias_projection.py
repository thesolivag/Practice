"""A new confirmed stream supersedes legacy structural cards without deletion."""
import pytest
from fastapi.testclient import TestClient
from bishop.paper_store import Store
from bishop.webapp import create_app


def row(pair,namespace,hour,basis,state='DIRECTIONAL',side='SELL'):
    return dict(instrument=pair,namespace=namespace,as_of=f'2026-06-24T{hour:02d}:00:00+00:00',
                rows=[dict(instrument=pair,tf='D',basis=basis,state=state,side=side)])


@pytest.mark.parametrize('state,side',[('WAIT_EXTERNAL_BREAK',None),('CONFLICT',None),('DIRECTIONAL','BUY')])
def test_current_api_prefers_latest_confirmed_even_when_newer_raw_row_exists(state,side):
    store=Store()
    payloads=[row('GBPUSD','bias-scan-GBPUSD',23,'SAME_TIMEFRAME_STRUCTURE'),
              row('GBPUSD','confirmed-bias-scan-GBPUSD-old',20,'CONFIRMED_STORIES'),
              row('GBPUSD','confirmed-bias-scan-GBPUSD',22,'CONFIRMED_STORIES',state,side),
              row('EURNZD','bias-scan-EURNZD-old',19,'SAME_TIMEFRAME_STRUCTURE'),
              row('EURNZD','bias-scan-EURNZD',21,'SAME_TIMEFRAME_STRUCTURE')]
    with store.transaction():
        for i,payload in enumerate(payloads):store._put('bias_snapshots',str(i),payload)
    before=store.list('bias_snapshots',500)
    with TestClient(create_app(store,local_api_key='local-test'),client=('127.0.0.1',123)) as client:
        response=client.get('/api/bias/current',headers={'X-Bishop-Owner-Key':'local-test'})
    assert response.status_code==200
    by_pair={item['instrument']:item for item in response.json()['items']}
    assert set(by_pair)=={'GBPUSD','EURNZD'}
    assert by_pair['GBPUSD']==payloads[2]
    assert by_pair['GBPUSD']['rows'][0]['state']==state
    assert by_pair['GBPUSD']['rows'][0]['side']==side
    assert by_pair['EURNZD']==payloads[4]
    assert store.list('bias_snapshots',500)==before

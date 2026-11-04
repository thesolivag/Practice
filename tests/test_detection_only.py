"""Detection audit preserves plans and cannot be mistaken for executed results."""
from datetime import datetime,timedelta,timezone
import random
import pytest
from bishop.v2 import engine
from bishop.v2.types import Bar,Instrument,StrategyPolicy
from bishop.v2.simulation import Costs


def test_detection_only_preserves_all_plans_without_calling_execution(monkeypatch):
    at=datetime(2026,1,5,tzinfo=timezone.utc)
    rng=random.Random(41);price=1000;bars=[]
    for i in range(72):
        close=price+rng.choice((-12,-8,-4,4,8,12))
        bars.append(Bar('X','H1',at+timedelta(hours=i),at+timedelta(hours=i+1),
                        price,max(price,close)+3,min(price,close)-3,close))
        price=close
    feed={'instrument':Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1'),'bars':bars}
    args=dict(as_of=bars[-1].end,costs=Costs(),policy=StrategyPolicy(origin_tfs=('H4',),entry_tfs=('H1',),
              risk_profile='fixed11',target_profile='fixed3r',source_profile='source_all'))
    full=engine.run(feed,**args)
    def forbidden(*a,**k):pytest.fail('detection-only must not execute orders')
    monkeypatch.setattr(engine,'simulate',forbidden)
    audit=engine.run(feed,**args,detection_only=True)
    assert audit['instrument']['symbol']=='X'
    assert audit['schema_version']=='bishop_detection_v2'
    assert audit['graph_projection'].startswith('ENTRY_STATE_ONLY')
    assert {s['story_id'] for s in audit['setups']} <= {s['id'] for s in audit['stories']}
    assert audit['setups']==full['setups'] and audit['setups']
    assert audit['orders']==audit['observations']==[]
    assert audit['scope']=='DETECTION_ONLY_NOT_EXECUTED'
    assert audit['selection']['mode']=='NOT_RUN_DETECTION_ONLY'
    assert audit['run_id']!=full['run_id']
    assert audit['summary']['outcomes']=={}


@pytest.mark.parametrize('extra',[{'bias_only':True},{'execution_feed':{}},{'refinement_directory':'x'},
                                  {'management_actions':({'kind':'CANCEL'},)}])
def test_detection_only_rejects_execution_inputs(extra):
    with pytest.raises(ValueError,match='detection-only'):
        engine.run({},as_of='2026-01-01T00:00Z',detection_only=True,**extra)

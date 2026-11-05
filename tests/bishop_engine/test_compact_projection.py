"""Compact story projection preserves entry selection and paper execution."""
from datetime import datetime,timedelta,timezone
import random
import pytest
from bishop.v2.types import Bar,Instrument,StrategyPolicy
from bishop.v2.engine import run
from bishop.v2.simulation import Costs


def fixture():
    at=datetime(2026,1,1,tzinfo=timezone.utc)
    randomizer=random.Random(41);price=1000;bars=[]
    for i in range(72):
        close=price+randomizer.choice((-12,-8,-4,4,8,12))
        bars.append(Bar('X','H1',at+timedelta(hours=i),at+timedelta(hours=i+1),
                        price,max(price,close)+3,min(price,close)-3,close))
        price=close
    inst=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    return {'instrument':inst,'bars':tuple(bars)}


@pytest.mark.parametrize('source_profile',['bishop_confirmation','source_all'])
def test_compact_projection_keeps_orders_outcomes_and_cancellations(source_profile):
    feed=fixture()
    policy=StrategyPolicy(origin_tfs=('H4',),entry_tfs=('H1',),risk_profile='fixed11',
                          target_profile='fixed3r',source_profile=source_profile)
    kwargs=dict(as_of=feed['bars'][-1].end,policy=policy,costs=Costs())
    full=run(feed,**kwargs)
    compact=run(feed,compact_story_diagnostics=True,**kwargs)
    assert full['stories']
    if source_profile=='source_all':assert full['setups'] and full['orders']
    for key in ('stories','setups','orders','actions','observations','positions','execution_events','selection','summary'):
        assert compact[key]==full[key],key
    # Compact observations may omit successor diagnostics, but retain every
    # lifecycle event that can cancel/block an entry.
    terminal=lambda rows:[r for r in rows if r['kind'] in ('STORY_INVALIDATED','STORY_DESTINATION_REACHED','STORY_CANCELLED','STORY_FLIPPED') or r.get('details',{}).get('pending_action')=='CANCEL_DEPENDENT']
    assert terminal(compact['story_events'])==terminal(full['story_events'])


def test_compact_projection_rejects_nonboolean_flag():
    with pytest.raises(ValueError,match='compact_story_diagnostics'):
        run(fixture(),as_of=datetime(2026,1,4,tzinfo=timezone.utc),costs=Costs(),compact_story_diagnostics=1)

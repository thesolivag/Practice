"""Independent prospective safeguards; these are not mentor selection rules."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import bishop.v2.engine as engine
from bishop.v2.simulation import Costs
from bishop.v2.types import Bar, Clock, Instrument, Setup, StrategyPolicy

T = datetime(2026, 1, 5, tzinfo=timezone.utc)


def setup(ident, **changes):
    at = changes.pop('at', T)
    return replace(Setup(id=ident, instrument='X', tf='M1', model='direct_h4',
                         side='BUY', story_id='story', clock=Clock(at,at,at),
                         entry_ticks=8, stop_ticks=5, target_ticks=12,
                         level_id='level', risk_profile='context_liquidity'), **changes)


def replay(monkeypatch, setups, profile='owner_aggressive', cap=1, blocked=False):
    instrument = Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    bars = tuple(Bar('X','M1',T+timedelta(minutes=i),T+timedelta(minutes=i+1),
                     10,11,9,10) for i in range(3))
    stories = (SimpleNamespace(id='story',details={}),
               SimpleNamespace(id='blocked',details={'owner_selection':'BLOCKED_COUNTERWEEKLY'} if blocked else {}))
    monkeypatch.setattr(engine,'find_stories',lambda *a:
                        SimpleNamespace(stories=stories,events=(),support=()))
    monkeypatch.setattr(engine,'detect_setups',lambda *a,**k:
                        SimpleNamespace(setups=tuple(setups),events=(),support=()))
    monkeypatch.setattr(engine,'jsonable',lambda x:x)
    return engine.run({'instrument':instrument,'bars':bars},as_of=bars[-1].end,
                      costs=Costs(),max_open_orders=cap,
                      policy=StrategyPolicy(source_profile=profile,entry_tfs=('M1',),origin_tfs=('D',)))


@pytest.mark.parametrize('ids', [('a','z'), ('z','a')])
def test_conflicting_risk_waits_without_consuming_exposure(monkeypatch, ids):
    choices = (setup(ids[0]), setup(ids[1],stop_ticks=6), setup('valid',entry_ticks=7))
    result = replay(monkeypatch, choices)
    assert [o.setup_id for o in result['orders']] == ['valid']
    rejected = result['selection']['rejected']
    assert {r['setup_id'] for r in rejected} == set(ids)
    assert {r['reason'] for r in rejected} == {'AMBIGUOUS_EXECUTION_PLAN'}
    assert len(result['selection']['conflicts']) == 1
    assert set(result['selection']['conflicts'][0]['setup_ids']) == set(ids)
    assert len(result['setups']) == 3
    assert result['selection']['ambiguity_policy'].endswith('OUR_CHOICE')


def test_same_price_geometry_with_different_levels_remains_unresolved(monkeypatch):
    result = replay(monkeypatch,(setup('a'),setup('b',level_id='other_level')))
    assert not result['orders']
    assert not result['selection']['aliases']
    assert {r['reason'] for r in result['selection']['rejected']} == {'AMBIGUOUS_LEVEL_SELECTION'}


def test_exact_aliases_and_later_clock_are_preserved(monkeypatch):
    result = replay(monkeypatch,(setup('a'),setup('b'),
                                 setup('later',at=T+timedelta(minutes=1),stop_ticks=6)),cap=2)
    assert {o.setup_id for o in result['orders']} == {'a','later'}
    assert len(result['selection']['aliases']) == 1
    assert not result['selection']['rejected']


@pytest.mark.parametrize('profile',['source_all','all_routes'])
def test_source_alternatives_are_not_silently_selected(monkeypatch, profile):
    result = replay(monkeypatch,(setup('a'),setup('b',stop_ticks=6),
                                 setup('c',level_id='other_level')),profile=profile)
    assert len(result['orders']) == 3
    assert not result['selection']['rejected']
    assert result['selection']['mode'] == 'INDEPENDENT_ALTERNATIVES'


def test_blocked_or_ineligible_candidate_does_not_create_conflict(monkeypatch):
    result = replay(monkeypatch,(setup('valid'),setup('blocked_risk',story_id='blocked',stop_ticks=6),
                                 setup('unresolved',status='UNRESOLVED',target_ticks=20)),blocked=True)
    assert [o.setup_id for o in result['orders']] == ['valid']
    assert result['selection']['rejected'] == [{'setup_id':'blocked_risk','reason':'BLOCKED_COUNTERWEEKLY'}]

"""Synthetic risk integration: target lineage, not mentor-trade acceptance."""
from dataclasses import replace
from types import SimpleNamespace
from test_target_context import fixtures
from bishop.v2.target_context import resolve_context, context_from_reference
from bishop.v2.types import Instrument, StrategyPolicy, Liquidity, Level
from bishop.v2.risk import plan


def run(context=None, profile='context_objective', relation='ALIGNED', obstacle=None):
    sponsor,pool,scope,bar,structure=fixtures()
    micro=Liquidity(id='micro',instrument='X',tf='H1',kind='HIGH',price_ticks=111,
                    formed_at=bar.start,available_at=bar.start)
    entry_range=replace(scope,endpoint_liquidity_id=micro.id,endpoint_ticks=111)
    story=SimpleNamespace(details={'entry_weekly_relation':relation},destination_ticks=200,destination_ref_id='weekly')
    return plan('BUY',100,bar.end,'H1',(),(),(micro,),story,
                Instrument('X','1','1',calendar_id='24x7_utc_v1'),
                StrategyPolicy(target_profile=profile,risk_profile='fixed11'),ranges=(entry_range,),
                target_context=context,context_bars=(bar,),countertrend_obstacle=obstacle)


def context():
    sponsor,pool,scope,bar,structure=fixtures()
    return resolve_context(sponsor,structure,(bar,),bar.end,'BUY')


def test_context_target_preserves_h4_objective_and_stop_over_h1_micro_target():
    carried=run(context())
    explicit_lower=run(profile='entry_erl')
    assert carried.status=='ELIGIBLE' and carried.target_ticks==150
    assert explicit_lower.status=='ELIGIBLE' and explicit_lower.target_ticks==111
    assert carried.stop_ticks==explicit_lower.stop_ticks
    assert carried.details['target_plan']['story_destination']['price_ticks']==200
    assert carried.details['target_plan']['entry_erl_candidates'][0][0]==111


def test_missing_context_holds_instead_of_falling_back_or_crashing():
    result=run()
    assert result.status=='UNRESOLVED' and result.target_ticks is None
    assert 'context_objective_unresolved' in result.details['unresolved_reasons']


def test_counterweekly_requires_qualified_obstacle_and_accepts_same_scope_kl():
    sponsor,pool,scope,bar,structure=fixtures()
    kl=Level(id='obstacle',instrument='X',tf='H4',kind='OC',price_ticks=140,side='SELL',
             formed_at=bar.start,available_at=bar.start)
    linked=replace(scope,details={**scope.details,'target_level_id':kl.id})
    guard=context_from_reference(sponsor,linked,kl,bar.end,'BUY','SELL')
    assert run(context(),relation='COUNTER_WEEKLY').status=='UNRESOLVED'
    result=run(context(),relation='COUNTER_WEEKLY',obstacle=guard)
    assert result.status=='ELIGIBLE' and result.target_ticks==140
    assert result.details['target_plan']['selected_domain']=='COUNTERTREND_OBSTACLE'
    assert run(guard,relation='COUNTER_WEEKLY').status=='ELIGIBLE'
    assert run(context(),relation='COUNTER_WEEKLY',obstacle=replace(guard,scope_id='other')).status=='UNRESOLVED'

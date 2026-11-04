"""Liquidity origins keep source identity and context, without inventing ERL targets."""
from dataclasses import replace
from datetime import timedelta
import pytest
from test_frozen_bias_reference import fixture,T
from bishop.v2.types import Bar,Clock,Event,Level,Liquidity,StrategyPolicy
from bishop.v2.structure import Range,StructureResult
from bishop.v2.stories import (_confirm,_StoryStructureView,_liquidity_origin,
                               _liquidity_environment,find_stories)


def source(side='BUY'):
    reaction,origin,lower,structure,parents,old,last,external=fixture(side)
    previous=Bar('X','D',T,T+timedelta(hours=24),105,150,100,110) if side=='BUY' else Bar('X','D',T,T+timedelta(hours=24),95,100,50,90)
    reaction=replace(reaction,kind='PRIOR_CANDLE_SWEEP',reference_id=previous.id,
                     details={'origin_tf':'D','level_tf':None,'origin_bar_id':origin.id,'fallback':False})
    return reaction,previous,origin,lower,structure,old,last,external


@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('indexed',[False,True])
def test_liquidity_strict_external_anchor_needs_no_higher_tf_key_level(side,indexed):
    reaction,previous,origin,lower,structure,old,last,external=source(side)
    parents={'D':StructureResult((),(),(),(),())}
    result=_StoryStructureView(structure,lower) if indexed else structure
    args=(reaction,origin,'H4',lower,result,(previous,origin),parents)
    assert _confirm(*args,reference_profile='last_pre_touch')[2].reference_id==last.id
    assert _confirm(*args,reference_profile='source_lineage')[2].reference_id==old.id
    missing=replace(structure,events=structure.events[:1])
    assert _confirm(reaction,origin,'H4',lower,missing,(previous,origin),parents,reference_profile='last_pre_touch') is None


def test_full_liquidity_story_carries_identity_and_preserves_kl_exit_caveat():
    reaction,previous,origin,lower,structure,old,last,external=source()
    exit_level=Level(id='kl_exit',instrument='X',tf='D',kind='A',price_ticks=130,side='SELL',formed_at=T,available_at=T)
    policy=StrategyPolicy(origin_tfs=('D',),entry_tfs=('H4',),bias_reference_profile='last_pre_touch')
    result=find_stories({'D':(previous,origin),'H4':lower},
                        {'D':StructureResult((),(exit_level,),(),(),()),'H4':structure},policy)
    story=next(s for s in result.stories if s.route=='candle_sweep_structural' and s.side=='BUY')
    identity=story.details['liquidity_origin']
    assert identity['swept_liquidity']['bar_ids']==(previous.id,)
    assert identity['swept_liquidity']['price_ticks']==previous.low_ticks
    assert identity['swept_liquidity']['role']=='UNKNOWN'
    assert identity['opposite_candle_liquidity_candidate']['selected_as_target'] is False
    assert story.available_at>=origin.available_at
    assert story.details['frozen_external_reference_id']==last.id
    assert story.destination_ticks==130 and story.details['destination_domain']=='KEY_LEVEL_EXIT_CANDIDATE'
    assert story.details['external_liquidity_destination_status']=='UNRESOLVED'
    assert any(e.kind=='BIAS_REFERENCE_FROZEN' and e.details['origin_kind']=='PRIOR_CANDLE_SWEEP' for e in result.events)


def environment_fixture():
    reaction,previous,origin,lower,structure,old,last,external=source()
    at=origin.start
    pool=Liquidity(id='endpoint',instrument='X',tf='D',kind='LOW',price_ticks=100,
                   formed_at=previous.end,available_at=at,bar_ids=(previous.id,),form='TURN_LEG')
    root=Range('root',None,'SELL','DEFINED','origin',None,'endpoint_turn',pool.id,
               150,100,at,at,'v1',{'endpoint_stage':'CONFIRMED_DELIVERY'})
    internal=Event(id='internal_buy',kind='BOS',instrument='X',tf='D',side='BUY',scope_id='child',clock=Clock(at,at,at))
    parent=StructureResult((),(),(pool,),(internal,),(root,))
    return previous,origin,lower,parent,root,pool


@pytest.mark.parametrize('indexed',[False,True])
def test_environment_freezes_pre_contact_and_internal_break_does_not_flip_root(indexed):
    previous,origin,lower,parent,root,pool=environment_fixture()
    future=replace(root,direction='BUY',version_id='future',available_at=origin.start+timedelta(hours=4))
    parent=replace(parent,ranges=(root,future))
    if indexed:parent=_StoryStructureView(parent,(previous,origin))
    identity=_liquidity_origin(previous,origin,'BUY',parent,lower)
    env=identity['structural_environment']
    assert env['as_of']==origin.start and env['side']=='SELL'
    assert env['latest_break_sides']==('BUY',)
    assert identity['relation_to_structure']=='COUNTER_STRUCTURE_RETRACEMENT'
    assert identity['swept_liquidity']['role']=='ERL'
    assert identity['first_obstacle_status']=='UNRESOLVED'


@pytest.mark.parametrize('reverse',[False,True])
def test_tied_conflicting_root_versions_are_unknown_in_both_cache_paths(reverse):
    previous,origin,lower,parent,root,pool=environment_fixture()
    other=replace(root,direction='BUY',version_id='other')
    rows=(root,other) if reverse else (other,root)
    plain=replace(parent,ranges=rows)
    for view in (plain,_StoryStructureView(plain,(previous,origin))):
        identity=_liquidity_origin(previous,origin,'BUY',view,lower)
        assert identity['structural_environment']['state']=='UNKNOWN'
        assert identity['structural_environment']['side'] is None
        assert identity['swept_liquidity']['role']=='UNKNOWN'


def test_equal_price_without_source_bar_identity_cannot_claim_erl():
    previous,origin,lower,parent,root,pool=environment_fixture()
    parent=replace(parent,liquidity=(replace(pool,bar_ids=('other_candle',)),))
    assert _liquidity_origin(previous,origin,'BUY',parent,lower)['swept_liquidity']['role']=='UNKNOWN'


def test_opposite_source_point_already_taken_is_not_offered_as_valid_target():
    previous,origin,lower,parent,root,pool=environment_fixture()
    previous=replace(previous,high_ticks=120)
    candidate=_liquidity_origin(previous,origin,'BUY',parent,lower)['opposite_candle_liquidity_candidate']
    assert candidate['status_at_sweep_close']=='TAKEN' and candidate['selected_as_target'] is False


def test_source_liquidity_publication_after_first_sweep_cannot_confirm_strict_bias():
    reaction,previous,origin,lower,structure,old,last,external=source()
    late=replace(previous,available_at=origin.start+timedelta(hours=1))
    parents={'D':StructureResult((),(),(),(),())}
    identity=_liquidity_origin(late,origin,'BUY',parents['D'],lower)
    assert identity['swept_liquidity']['knowledge_at_contact']=='UNPUBLISHED_SOURCE_REFERENCE'
    assert _confirm(reaction,origin,'H4',lower,structure,(late,origin),parents,reference_profile='last_pre_touch') is None


def test_existing_known_period_pool_is_preserved_as_alias_not_invented_role():
    previous,origin,lower,parent,root,pool=environment_fixture()
    source_pool=replace(pool,id='bar_pool',form='BAR')
    identity=_liquidity_origin(previous,origin,'BUY',replace(parent,liquidity=(pool,source_pool)),lower)
    assert identity['swept_liquidity']['observed_pool_ids']==('bar_pool',)


def test_strict_liquidity_requires_its_previous_source_candle():
    reaction,previous,origin,lower,structure,old,last,external=source()
    assert _confirm(reaction,origin,'H4',lower,structure,(origin,),
                    {'D':StructureResult((),(),(),(),())},reference_profile='last_pre_touch') is None


def test_delayed_child_cannot_rewrite_the_published_reaction_contact():
    previous,origin,lower,parent,root,pool=environment_fixture()
    delayed=tuple(replace(b,available_at=origin.available_at+timedelta(hours=1)) for b in lower)
    a=_liquidity_origin(previous,origin,'BUY',parent,delayed)
    prefix=_liquidity_origin(previous,origin,'BUY',parent,())
    assert a==prefix
    assert a['contact_bar_id'] is None
    assert a['environment_cutoff_policy']=='ORIGIN_BAR_START_CONSERVATIVE_NO_LOWER_CONTACT'

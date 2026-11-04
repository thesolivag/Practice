"""Story objectives require structural evidence; first exits do not retire HTF bias."""
from dataclasses import replace
from datetime import timedelta
import pytest
from test_frozen_bias_reference import T
from bishop.v2.types import Bar,Liquidity,Level,StrategyPolicy
from bishop.v2.structure import Range,StructureResult
from bishop.v2.stories import _story_destinations,_StoryStructureView


def fixture(side='BUY'):
    at=T+timedelta(days=2)
    p=Liquidity(id='erl',instrument='X',tf='D',kind='HIGH' if side=='BUY' else 'LOW',
        price_ticks=150 if side=='BUY' else 50,formed_at=T,available_at=T,form='TURN_LEG')
    r=Range('root',None,side,'DEFINED','origin',None,'endpoint',p.id,150 if side=='SELL' else 50,p.price_ticks,T,T,'v1',
            {'endpoint_stage':'CONFIRMED_DELIVERY','endpoint_broken':False})
    kl=Level(id='kl',instrument='X',tf='D',kind='A' if side=='BUY' else 'V',
        price_ticks=120 if side=='BUY' else 80,side='SELL' if side=='BUY' else 'BUY',formed_at=T,available_at=T)
    b=Bar('X','D',T,T+timedelta(days=1),100,110,90,100)
    return at,p,r,kl,b


@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('indexed',[False,True])
def test_qualified_root_objective_and_distinct_nearer_first_exit(side,indexed):
    at,p,r,kl,b=fixture(side)
    result=StructureResult((),(kl,),(p,),(),(r,))
    if indexed:result=_StoryStructureView(result,(b,))
    target,details=_story_destinations('D',side,100,at,{'D':result},StrategyPolicy(),(b,))
    assert target.id=='erl'
    assert details['overall_objective']['role']=='ERL'
    assert details['first_obstacle']['id']=='kl'
    assert details['destination_domain']=='EXTERNAL_LIQUIDITY'


@pytest.mark.parametrize('reason',['future','taken','broken','unconfirmed','opposite_structure','ambiguous'])
def test_unqualified_pool_does_not_replace_known_kl(reason):
    at,p,r,kl,b=fixture()
    ranges=(r,)
    if reason=='future':p=replace(p,available_at=at+timedelta(seconds=1))
    if reason=='taken':b=replace(b,high_ticks=155)
    if reason=='broken':r=replace(r,details={'endpoint_stage':'CONFIRMED_DELIVERY','endpoint_broken':True})
    if reason=='unconfirmed':r=replace(r,details={'endpoint_stage':'PROVISIONAL'})
    if reason=='opposite_structure':r=replace(r,direction='SELL')
    ranges=(r,replace(r,direction='SELL',version_id='conflict')) if reason=='ambiguous' else (r,)
    result=StructureResult((),(kl,),(p,),(),ranges)
    target,details=_story_destinations('D','BUY',100,at,{'D':result},StrategyPolicy(),(b,))
    assert target.id=='kl'
    assert details['overall_objective'] is None
    assert details['external_liquidity_destination_status']=='UNRESOLVED'
    assert details['destination_domain']=='KEY_LEVEL_EXIT_CANDIDATE'


def test_arbitrary_nearer_wick_is_not_significant_obstacle():
    at,p,r,kl,b=fixture()
    wick=replace(p,id='arbitrary',price_ticks=115,form='BAR')
    result=StructureResult((),(kl,),(p,wick),(),(r,))
    target,details=_story_destinations('D','BUY',100,at,{'D':result},StrategyPolicy(),(b,))
    assert target.id=='erl' and details['first_obstacle']['id']=='kl'


@pytest.mark.parametrize('invalidated',[False,True])
def test_local_obstacle_take_does_not_emit_overall_destination_retirement(invalidated):
    from test_liquidity_bias_identity import source
    from bishop.v2.stories import find_stories
    _,previous,origin,lower,structure,*_=source()
    pool=Liquidity(id='overall',instrument='X',tf='D',kind='HIGH',price_ticks=180,
                   formed_at=T,available_at=T,form='TURN_LEG')
    root=Range('root',None,'BUY','DEFINED','origin',None,'endpoint',pool.id,60,180,T,T,'v1',
               {'endpoint_stage':'CONFIRMED_DELIVERY'})
    obstacle=Level(id='obstacle',instrument='X',tf='D',kind='A',side='SELL',price_ticks=150,formed_at=T,available_at=T)
    after=Bar('X','D',origin.end,origin.end+timedelta(days=1),110,160,105,140)
    if invalidated:
        from bishop.v2.types import Event,Clock
        when=origin.end+timedelta(hours=1)
        broken=Event(id='broken',kind='RANGE_BROKEN',instrument='X',tf='H4',scope_id=None,clock=Clock(when,when,when))
        structure=replace(structure,events=(*structure.events,broken))
    result=find_stories({'D':(previous,origin,after),'H4':lower},
        {'D':StructureResult((),(obstacle,),(pool,),(),(root,)),'H4':structure},
        StrategyPolicy(origin_tfs=('D',),entry_tfs=('H4',),bias_reference_profile='last_pre_touch'))
    story=next(s for s in result.stories if s.side=='BUY' and s.route=='candle_sweep_structural')
    assert story.destination_ticks==180
    events=[e for e in result.events if e.reference_id==story.id]
    assert any(e.kind=='STORY_FIRST_OBSTACLE_REACHED' and e.details['overall_bias_retired'] is False for e in events) is not invalidated
    if invalidated:assert any(e.kind=='STORY_INVALIDATED' for e in events)
    assert not any(e.kind=='STORY_DESTINATION_REACHED' for e in events)


@pytest.mark.parametrize('reason',['segment','gap','unknown_source'])
def test_objective_needs_observed_same_segment_source_evidence(reason):
    at,p,r,kl,b=fixture()
    if reason=='unknown_source':p=replace(p,bar_ids=('unpublished',))
    nextbar=Bar('X','D',b.end+(timedelta(hours=1) if reason=='gap' else timedelta()),
                at+timedelta(hours=1),100,110,90,100,segment_id='other' if reason in ('segment','gap') else '0')
    result=StructureResult((),(kl,),(p,),(),(r,))
    target,details=_story_destinations('D','BUY',100,nextbar.available_at,{'D':result},StrategyPolicy(),(b,nextbar))
    assert target.id=='kl' and details['overall_objective'] is None


def test_declared_contiguous_segment_allows_scheduled_weekend_closure():
    at,p,r,kl,b=fixture()
    # The feed declares continuity; elapsed wall time alone cannot classify a gap.
    monday=Bar('X','D',b.end+timedelta(days=2),b.end+timedelta(days=3),100,110,90,100,segment_id=b.segment_id)
    result=StructureResult((),(kl,),(p,),(),(r,))
    target,details=_story_destinations('D','BUY',100,monday.available_at,{'D':result},StrategyPolicy(),(b,monday))
    assert target.id=='erl' and details['external_liquidity_destination_status']=='QUALIFIED'

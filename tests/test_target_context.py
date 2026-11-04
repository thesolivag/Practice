"""Semantic source templates and causal carry invariants, not price fitting."""
from dataclasses import FrozenInstanceError,replace
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from bishop.v2.types import Bar,Clock,Event,Liquidity,Level
from bishop.v2.structure import Range,StructureResult
from bishop.v2.target_context import resolve_context,validate_context,context_from_reference

T=datetime(2026,1,1,tzinfo=timezone.utc)


def fixtures():
    sponsor=Event(id='break',kind='BOS',instrument='X',tf='H4',clock=Clock(T,T,T),side='BUY',scope_id='scope')
    pool=Liquidity(id='erl',instrument='X',tf='H4',kind='HIGH',price_ticks=150,formed_at=T,available_at=T)
    selected=Range('scope',None,'BUY','DEFINED','low',None,'high','erl',80,150,T,T,'v1',{'endpoint_stage':'CONFIRMED_DELIVERY'})
    bar=Bar('X','H4',T,T+timedelta(hours=4),100,120,90,110)
    structure=StructureResult((),(),(pool,),(),(selected,))
    return sponsor,pool,selected,bar,structure


def test_context_h4_objective_carries_unchanged_over_lower_timeframe_entry():
    sponsor,pool,selected,bar,structure=fixtures()
    lower=Liquidity(id='h1',instrument='X',tf='H1',kind='HIGH',price_ticks=111,formed_at=T,available_at=T)
    structure=replace(structure,liquidity=(pool,lower))
    context=resolve_context(sponsor,structure,(bar,),bar.end,'BUY')
    assert context.status=='KNOWN' and context.tf=='H4'
    assert validate_context(context,bar.end,100,'BUY',(bar,))==(150,())
    assert context.objective_ref_id=='erl'


def test_missing_scope_never_borrows_an_unrelated_containing_range():
    sponsor,pool,selected,bar,structure=fixtures()
    context=resolve_context(replace(sponsor,scope_id=None),structure,(bar,),bar.end,'BUY')
    assert context.status=='UNRESOLVED' and 'context_scope_unresolved' in context.reasons
    assert validate_context(context,bar.end,100,'BUY',(bar,))[0] is None


def test_future_objective_cannot_qualify_snapshot():
    sponsor,pool,selected,bar,structure=fixtures()
    structure=replace(structure,liquidity=(replace(pool,available_at=bar.end+timedelta(hours=1)),))
    context=resolve_context(sponsor,structure,(bar,),bar.end,'BUY')
    assert context.status=='UNRESOLVED'


@pytest.mark.parametrize('reverse',[False,True])
def test_latest_published_range_state_wins_permuted_history(reverse):
    sponsor,pool,selected,bar,structure=fixtures()
    broken=replace(selected,available_at=T+timedelta(hours=1),version_id='v2',status='BROKEN')
    future=replace(selected,available_at=T+timedelta(hours=5),version_id='future')
    versions=(selected,broken) if not reverse else (broken,selected)
    context=resolve_context(sponsor,replace(structure,ranges=(*versions,future)),(bar,),bar.end,'BUY')
    assert 'context_range_origin_broken' in context.reasons


def test_exact_erl_touch_after_snapshot_consumes_without_retargeting():
    sponsor,pool,selected,bar,structure=fixtures()
    context=resolve_context(sponsor,structure,(bar,),bar.end,'BUY')
    next_bar=Bar('X','H4',bar.end,bar.end+timedelta(hours=4),110,150,105,145)
    price,reasons=validate_context(context,next_bar.end,100,'BUY',(bar,next_bar))
    assert price is None and 'context_objective_consumed_or_ordering_unknown' in reasons
    assert context.objective_price_ticks==150


def test_unpublished_candle_does_not_consume_context():
    sponsor,pool,selected,bar,structure=fixtures()
    context=resolve_context(sponsor,structure,(bar,),bar.end,'BUY')
    next_bar=Bar('X','H4',bar.end,bar.end+timedelta(hours=4),110,160,105,145,
                 available_at=bar.end+timedelta(hours=5))
    price,reasons=validate_context(context,next_bar.end,100,'BUY',(bar,next_bar))
    assert price is None and 'context_entry_interval_unobserved' in reasons
    assert 'context_objective_consumed_or_ordering_unknown' not in reasons


def test_range_invalidation_is_causal_and_endpoint_delivery_is_not_origin_break():
    sponsor,pool,selected,bar,structure=fixtures()
    context=resolve_context(sponsor,structure,(bar,),bar.end,'BUY')
    event=Event(id='broken',kind='RANGE_BROKEN',instrument='X',tf='H4',scope_id='scope',
                clock=Clock(bar.end,bar.end,bar.end+timedelta(hours=1)),side='SELL')
    assert validate_context(context,bar.end,100,'BUY',(bar,),(event,))==(150,())
    assert 'context_range_origin_broken' in validate_context(context,event.available_at,100,'BUY',(bar,),(event,))[1]
    delivered=replace(event,id='delivery',kind='RANGE_ENDPOINT_DELIVERED')
    assert 'context_range_origin_broken' not in validate_context(context,delivered.available_at,100,'BUY',(bar,),(delivered,))[1]


def test_v16_linked_opposing_h4_kl_not_nearest_h1_junction():
    sponsor,pool,selected,bar,structure=fixtures()
    kl=Level(id='h4oc',instrument='X',tf='H4',kind='OC',price_ticks=140,side='SELL',formed_at=T,available_at=T)
    selected=replace(selected,details={**selected.details,'target_level_id':kl.id})
    context=resolve_context(sponsor,replace(structure,levels=(kl,),ranges=(selected,)),(bar,),bar.end,'BUY')
    assert context.status=='KNOWN' and context.objective_kind=='KL'
    assert validate_context(context,bar.end,100,'BUY',(bar,))==(140,())


def test_unlinked_or_ambiguous_kl_is_not_guessed():
    sponsor,pool,selected,bar,structure=fixtures()
    kl=Level(id='h4oc',instrument='X',tf='H4',kind='OC',price_ticks=140,side='SELL',formed_at=T,available_at=T)
    assert context_from_reference(sponsor,selected,kl,bar.end,'BUY','SELL').status=='UNRESOLVED'
    selected=replace(selected,details={**selected.details,'target_level_id':kl.id,'opposing_level_id':'other'})
    context=resolve_context(sponsor,replace(structure,levels=(kl,),ranges=(selected,)),(bar,),bar.end,'BUY')
    assert 'context_objective_links_ambiguous' in context.reasons


def test_reusable_kl_touch_survives_but_role_loss_retires_its_snapshot():
    sponsor,pool,selected,bar,structure=fixtures()
    kl=Level(id='h4oc',instrument='X',tf='H4',kind='OC',price_ticks=140,side='SELL',formed_at=T,available_at=T)
    selected=replace(selected,details={**selected.details,'target_level_id':kl.id})
    context=resolve_context(sponsor,replace(structure,levels=(kl,),ranges=(selected,)),(bar,),bar.end,'BUY')
    touch=Bar('X','H4',bar.end,bar.end+timedelta(hours=4),110,140,105,130)
    assert validate_context(context,touch.end,100,'BUY',(bar,touch))==(140,())
    flip=Event(id='flip',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='H4',reference_id=kl.id,side='BUY',clock=Clock(touch.end,touch.end,touch.end))
    assert 'context_objective_role_lost' in validate_context(context,touch.end,100,'BUY',(bar,touch),(flip,))[1]


def test_context_is_deeply_immutable_and_identity_is_publication_sensitive():
    sponsor,pool,selected,bar,structure=fixtures()
    context=resolve_context(sponsor,structure,(bar,),bar.end,'BUY')
    with pytest.raises(FrozenInstanceError):context.objective_price_ticks=999
    with pytest.raises(TypeError):context.provenance['range_version_id']='other'
    assert replace(context,available_at=context.available_at+timedelta(seconds=1)).id!=context.id


def test_published_child_touch_retires_objective_before_parent_close():
    sponsor,pool,selected,bar,structure=fixtures()
    context=resolve_context(sponsor,structure,(bar,),bar.end,'BUY')
    child=Bar('X','H1',bar.end,bar.end+timedelta(hours=1),110,150,105,145)
    assert 'context_objective_consumed_or_ordering_unknown' in validate_context(context,child.end,100,'BUY',(bar,child))[1]
    safe=replace(child,high_ticks=140,close_ticks=130)
    assert validate_context(context,safe.end,100,'BUY',(bar,safe))==(150,())
    gap=replace(safe,start=safe.start+timedelta(minutes=30))
    assert 'context_entry_interval_unobserved' in validate_context(context,gap.end,100,'BUY',(bar,gap))[1]


def test_reaction_snapshot_between_h4_closes_uses_published_child_coverage():
    sponsor,pool,selected,bar,structure=fixtures()
    child=Bar('X','H1',bar.end,bar.end+timedelta(hours=1),110,140,105,130)
    context=resolve_context(sponsor,structure,(bar,child),child.end,'BUY')
    assert context.status=='KNOWN'
    assert validate_context(context,child.end,100,'BUY',(bar,child))==(150,())


@pytest.mark.parametrize('side,entry,near,far,role',[
    ('BUY',100,130,140,'SELL'),('SELL',140,110,100,'BUY')])
def test_v16_explicit_h4_kl_route_uses_entry_not_reaction_or_h1(side,entry,near,far,role):
    from bishop.v2.target_context import resolve_h4_key_level
    sponsor,pool,selected,bar,structure=fixtures()
    sponsor=replace(sponsor,side=side,scope_id=None)
    def level(ident,price,tf='H4',at=T):
        return Level(id=ident,instrument='X',tf=tf,kind='OC',price_ticks=price,
                     side=role,formed_at=T,available_at=at)
    levels=(level('near',near),level('far',far),level('h1',entry+(1 if side=='BUY' else -1),'H1'),
            level('future',entry+(2 if side=='BUY' else -2),at=bar.end+timedelta(hours=1)))
    context=resolve_h4_key_level(sponsor,replace(structure,levels=levels),(bar,),bar.end,entry,side)
    assert context.status=='KNOWN' and context.objective_ref_id=='near'
    assert context.scope_id is None and context.objective_price_ticks==near
    assert context.provenance['entry_ticks']==entry


def test_h4_kl_route_excludes_unavailable_and_wrong_role_without_erl_fallback():
    from bishop.v2.target_context import resolve_h4_key_level
    sponsor,pool,selected,bar,structure=fixtures()
    kl=Level(id='kl',instrument='X',tf='H4',kind='A',price_ticks=140,side='SELL',formed_at=T,available_at=T)
    gone=Event(id='gone',kind='LEVEL_UNAVAILABLE',instrument='X',tf='H4',reference_id=kl.id,
               clock=Clock(T,T,T))
    for events in ((gone,), (replace(gone,kind='LEVEL_ROLE_CHANGE',side='BUY'),)):
        context=resolve_h4_key_level(sponsor,replace(structure,levels=(kl,),events=events),
                                     (bar,),bar.end,100,'BUY')
        assert context.status=='UNRESOLVED' and context.objective_ref_id is None

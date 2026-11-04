"""Source-qualified objectives; synthetic prices do not certify teacher replay."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from bishop.v2.types import Bar,Clock,Event,Instrument,Liquidity,Level,StrategyPolicy
from bishop.v2.structure import Range,StructureResult
from bishop.v2.objectives import resolve_objectives,ObjectiveResolver
from bishop.v2.risk import plan

T=datetime(2026,1,1,tzinfo=timezone.utc)
I=Instrument('X','1','1',calendar_id='24x7_utc_v1')
S=SimpleNamespace(origin_tf='W',destination_ticks=160,destination_ref_id='overall',details={})


def source(tf='H4',price=130,ident='parent'):
    a=Bar('X',tf,T,T+timedelta(hours=4),100,price,90,105)
    b=Bar('X',tf,a.end,a.end+timedelta(hours=4),105,110,95,106)
    pool=Liquidity(id=ident+'pool',instrument='X',tf=tf,kind='HIGH',price_ticks=price,
        formed_at=a.end,available_at=a.end,form='TURN_LEG',bar_ids=(a.id,))
    event=Event(id=ident+'break',kind='BREAKOUT',instrument='X',tf=tf,
        side='BUY',clock=Clock(a.end,a.end,a.end),scope_id=ident,bar_ids=(a.id,))
    r=Range(ident,None,'BUY','DEFINED','protect',None,'endturn',pool.id,90,price,
        a.end,a.end,ident+'v',{'endpoint_stage':'CONFIRMED_DELIVERY','seed_break_event_id':event.id})
    return (a,b),pool,event,r,StructureResult((),(),(pool,),(event,),(r,))


def risk(res,bars,events=(),side='BUY'):
    return plan(side,100,bars[-1].end,bars[-1].tf,bars,(),(),S,I,
        StrategyPolicy(risk_profile='fixed11'),trade_objectives=res.candidates,
        trade_objective_diagnostics=res.diagnostics,context_bars=bars,context_events=events)


def test_default_requires_genuine_sponsor_not_smallest_containing_range():
    bars,pool,e,r,st=source()
    missing=resolve_objectives((),{'H4':st},{'H4':bars},bars[-1].end,100,'BUY')
    assert not missing.candidates and risk(missing,bars).status=='UNRESOLVED'
    resolved=resolve_objectives((e,),{'H4':st},{'H4':bars},bars[-1].end,100,'BUY')
    out=risk(resolved,bars,st.events)
    assert out.status=='ELIGIBLE' and out.target_ticks==130
    assert out.stop_ticks==89
    assert out.details['target_plan']['story_destination']['price_ticks']==160
    assert out.details['target_plan']['terminal_entry_range_fallback'] is False


def test_nearest_is_after_qualification_and_unrelated_junction_cannot_truncate():
    h4,p4,e4,r4,s4=source()
    h1,p1,e1,r1,s1=source('H1',120,'child')
    unrelated=replace(p1,id='ordinary_wick',price_ticks=101)
    s1=replace(s1,liquidity=(*s1.liquidity,unrelated))
    resolved=resolve_objectives((e4,e1),{'H4':s4,'H1':s1},{'H4':h4,'H1':h1},h4[-1].end,100,'BUY')
    out=risk(resolved,(*h4,*h1),(*s4.events,*s1.events))
    assert out.target_ticks==120
    assert {c.objective_price_ticks for c in resolved.candidates}=={120,130}


@pytest.mark.parametrize('change,reason',[
    ({'price_ticks':131},'endpoint_pool_price_mismatch'),
    ({'bar_ids':('missing',)},'objective_source_bars_unresolved_or_unpublished'),
    ({'available_at':T+timedelta(days=2)},'endpoint_pool_unresolved_or_ambiguous'),
])
def test_unknown_or_mismatched_endpoint_never_becomes_target(change,reason):
    bars,pool,e,r,st=source();st=replace(st,liquidity=(replace(pool,**change),))
    result=resolve_objectives((e,),{'H4':st},{'H4':bars},bars[-1].end,100,'BUY')
    assert not result.candidates
    assert any(reason in d['reasons'] for d in result.diagnostics)


def test_ambiguous_sponsor_cannot_fallthrough_to_convenient_seed():
    bars,pool,e,r,st=source()
    conflict=replace(r,endpoint_ticks=135,version_id='conflict')
    alternate=replace(r,id='alternate',version_id='alternate')
    result=resolve_objectives((e,),{'H4':replace(st,ranges=(r,conflict,alternate))},{'H4':bars},bars[-1].end,100,'BUY')
    assert not result.candidates
    assert any('sponsor_scope_versions_ambiguous' in d['reasons'] for d in result.diagnostics)


def test_consumed_endpoint_and_future_context_stay_unresolved():
    bars,pool,e,r,st=source()
    taken=replace(bars[-1],high_ticks=130)
    result=resolve_objectives((e,),{'H4':st},{'H4':(bars[0],taken)},taken.end,100,'BUY')
    assert not result.candidates
    assert any('context_objective_consumed_or_ordering_unknown' in d['reasons'] for d in result.diagnostics)
    later=replace(r,available_at=bars[-1].end+timedelta(hours=1))
    assert not resolve_objectives((e,),{'H4':replace(st,ranges=(later,))},{'H4':bars},bars[-1].end,100,'BUY').candidates


def test_only_explicit_scope_link_can_offer_first_key_level_obstacle():
    bars,pool,e,r,st=source()
    kl=Level(id='obstacle',instrument='X',tf='H4',kind='A',price_ticks=115,side='SELL',
        formed_at=bars[0].end,available_at=bars[0].end,bar_ids=(bars[0].id,))
    plain=replace(st,levels=(kl,))
    assert len(resolve_objectives((e,),{'H4':plain},{'H4':bars},bars[-1].end,100,'BUY').candidates)==1
    linked=replace(plain,ranges=(replace(r,details={**r.details,'opposing_level_id':kl.id}),))
    resolved=resolve_objectives((e,),{'H4':linked},{'H4':bars},bars[-1].end,100,'BUY')
    assert risk(resolved,bars,st.events).target_ticks==115


def test_weekend_scheduled_closure_same_segment_is_not_data_gap():
    bars,pool,e,r,st=source()
    later=replace(bars[-1],start=bars[-1].start+timedelta(days=2),end=bars[-1].end+timedelta(days=2),available_at=bars[-1].end+timedelta(days=2))
    result=resolve_objectives((e,),{'H4':st},{'H4':(bars[0],later)},later.end,100,'BUY')
    assert result.candidates


def test_cached_resolver_preserves_prefix_and_never_uses_future_endpoint():
    bars,pool,e,r,st=source()
    at=bars[-1].end
    initial=resolve_objectives((e,),{'H4':st},{'H4':bars},at,100,'BUY')
    future=replace(r,endpoint_ticks=150,available_at=at+timedelta(hours=4))
    changed=replace(st,ranges=(r,future))
    resolver=ObjectiveResolver({'H4':changed},{'H4':bars})
    assert resolver.resolve((e,),at,100,'BUY')==initial
    assert resolver.resolve((e,),at,100,'BUY')==initial

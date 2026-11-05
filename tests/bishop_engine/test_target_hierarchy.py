"""Source-backed local ERL/H4 exit target invariants; no teacher-price fitting."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from bishop.v2.types import Bar,Clock,Event,Turn,Liquidity,Level,Instrument,StrategyPolicy
from bishop.v2.structure import StructureResult,Range
from bishop.v2.objectives import resolve_objectives
from bishop.v2.risk import plan
T=datetime(2026,1,5,tzinfo=timezone.utc)


def fixture(side='BUY',tf='H1',with_kl=False):
    hours=4 if tf=='H4' else 1
    prices=[(100,116,95,110),(110,112,96,105),(105,111,97,108)]
    if side=='SELL':prices=[(200-o,200-l,200-h,200-c) for o,h,l,c in prices]
    bars=tuple(Bar('X',tf,T+timedelta(hours=i*hours),T+timedelta(hours=(i+1)*hours),*row) for i,row in enumerate(prices))
    turn=Turn(id='turn',instrument='X',tf=tf,kind='H' if side=='BUY' else 'L',price_ticks=110 if side=='BUY' else 90,
        formed_at=bars[0].end,available_at=bars[1].end,anchor_bar_id=bars[0].id,confirmation_bar_id=bars[1].id,bar_ids=(bars[0].id,bars[1].id))
    pool=Liquidity(id='pool',instrument='X',tf=tf,kind='HIGH' if side=='BUY' else 'LOW',price_ticks=116 if side=='BUY' else 84,
        formed_at=turn.formed_at,available_at=turn.available_at,form='TURN_LEG',bar_ids=turn.bar_ids,details={'turn_id':'turn'})
    r=Range('r',None,side,'DEFINED','origin',None,'turn','pool',90 if side=='BUY' else 110,turn.price_ticks,T,bars[1].end,'v',
        {'endpoint_stage':'CONFIRMED_DELIVERY','endpoint_broken':False,'seed_break_event_id':'sponsor'})
    sponsor=Event(id='sponsor',kind='BOS',instrument='X',tf=tf,clock=Clock(bars[1].end,bars[1].end,bars[1].end),side=side,scope_id='r')
    levels=()
    if with_kl:
        levels=(Level(id='exit',instrument='X',tf=tf,kind='A' if side=='BUY' else 'V',price_ticks=112 if side=='BUY' else 88,
            side='SELL' if side=='BUY' else 'BUY',formed_at=T,available_at=bars[1].end,bar_ids=turn.bar_ids),)
    structure=StructureResult((turn,),levels,(pool,),(sponsor,),(r,))
    return bars,structure,sponsor


@pytest.mark.parametrize('side,target',[('BUY',116),('SELL',84)])
def test_erl_uses_exact_turn_wick_not_close_boundary(side,target):
    bars,s,sponsor=fixture(side)
    result=resolve_objectives((sponsor,),{'H1':s},{'H1':bars},bars[-1].end,100,side)
    assert len(result.candidates)==1 and result.candidates[0].objective_price_ticks==target
    assert s.ranges[0].endpoint_ticks==(110 if side=='BUY' else 90)


def test_wrong_turn_or_wick_evidence_cannot_qualify():
    bars,s,sponsor=fixture()
    for bad in [replace(s.liquidity[0],details={'turn_id':'other'}),replace(s.liquidity[0],price_ticks=117)]:
        result=resolve_objectives((sponsor,),{'H1':replace(s,liquidity=(bad,))},{'H1':bars},bars[-1].end,100,'BUY')
        assert not result.candidates


def test_consumed_endpoint_is_not_revived_by_lineage_fix():
    bars,s,sponsor=fixture()
    bars=(*bars[:2],replace(bars[2],high_ticks=117))
    result=resolve_objectives((sponsor,),{'H1':s},{'H1':bars},bars[-1].end,100,'BUY')
    assert not result.candidates
    assert any('context_objective_consumed_or_ordering_unknown' in d['reasons'] for d in result.diagnostics)


@pytest.mark.parametrize('side,target',[('BUY',112),('SELL',88)])
def test_h4_exit_is_nearer_than_erl_and_story_destination_stays_distinct(side,target):
    bars,s,sponsor=fixture(side,tf='H4',with_kl=True)
    result=resolve_objectives((sponsor,),{'H4':s},{'H4':bars},bars[-1].end,100,side)
    assert {c.objective_kind for c in result.candidates}=={'ERL','KL'}
    story=SimpleNamespace(origin_tf='D',destination_ticks=150 if side=='BUY' else 50,destination_ref_id='far',details={})
    risk=plan(side,100,bars[-1].end,'H4',bars,s.levels,s.liquidity,story,Instrument('X','1','1'),
        StrategyPolicy(risk_profile='fixed11'),trade_objectives=result.candidates,trade_objective_diagnostics=result.diagnostics,
        context_bars=bars,context_events=s.events)
    assert risk.status=='ELIGIBLE' and risk.target_ticks==target
    assert risk.details['story_destination_ticks']==story.destination_ticks
    assert risk.details['target_plan']['selected_domain'] is not None


def test_h4_exit_does_not_need_fabricated_range_and_ignores_h1_junction():
    bars,s,sponsor=fixture(tf='H4',with_kl=True)
    sponsor=replace(sponsor,scope_id=None)
    s=replace(s,ranges=(),events=(sponsor,))
    h1level=replace(s.levels[0],id='entry_tf_junction',tf='H1',price_ticks=101)
    s=replace(s,levels=(*s.levels,h1level))
    result=resolve_objectives((sponsor,),{'H4':s},{'H4':bars},bars[-1].end,100,'BUY')
    assert len(result.candidates)==1 and result.candidates[0].objective_ref_id=='exit'
    assert result.candidates[0].scope_id is None
    future=replace(s.levels[0],available_at=bars[-1].end+timedelta(hours=1))
    result=resolve_objectives((sponsor,),{'H4':replace(s,levels=(future,h1level))},{'H4':bars},bars[-1].end,100,'BUY')
    assert not result.candidates


def test_explicit_continuation_owner_is_validated_against_original_range_version():
    bars,s,sponsor=fixture()
    original=s.ranges[0]
    continuation=replace(sponsor,id='continuation',scope_id=None,reference_id='turn',
        details={'continuation_range_owners':({'range_id':'r','range_version_id':'v','reference_turn_id':'turn'},)})
    result=resolve_objectives((continuation,),{'H1':s},{'H1':bars},bars[-1].end,100,'BUY')
    assert result.candidates
    assert all(c.provenance['scope_relation']=='EXPLICIT_CONTINUATION_OWNER' for c in result.candidates)
    bad=replace(continuation,details={'continuation_range_owners':({'range_id':'r','range_version_id':'invented','reference_turn_id':'turn'},)})
    assert not resolve_objectives((bad,),{'H1':s},{'H1':bars},bars[-1].end,100,'BUY').candidates


def test_close_line_break_does_not_consume_an_unhit_wick_target():
    bars,s,sponsor=fixture()
    # Close111 crosses structural110, but high112 leaves wick target116 intact.
    bars=(*bars[:2],replace(bars[2],high_ticks=112,close_ticks=111))
    r=replace(s.ranges[0],details={**s.ranges[0].details,'endpoint_broken':True})
    result=resolve_objectives((sponsor,),{'H1':replace(s,ranges=(r,))},{'H1':bars},bars[-1].end,100,'BUY')
    assert len(result.candidates)==1 and result.candidates[0].objective_price_ticks==116


def test_ambiguous_latest_owner_versions_do_not_crash_or_borrow_range():
    bars,s,sponsor=fixture()
    conflicting=replace(s.ranges[0],version_id='v2',endpoint_ticks=109)
    s=replace(s,ranges=(*s.ranges,conflicting))
    continuation=replace(sponsor,id='continuation',scope_id=None,reference_id='turn',
        details={'continuation_range_owners':({'range_id':'r','range_version_id':'v','reference_turn_id':'turn'},)})
    result=resolve_objectives((continuation,),{'H1':s},{'H1':bars},bars[-1].end,100,'BUY')
    assert not result.candidates
    assert any('continuation_range_versions_ambiguous' in d['reasons'] for d in result.diagnostics)


def test_ambiguous_owner_cannot_make_second_owner_appear_unique():
    bars,s,sponsor=fixture()
    r=s.ranges[0]
    s=replace(s,ranges=(r,replace(r,version_id='v2',endpoint_ticks=109),replace(r,id='other',version_id='other-v')))
    continuation=replace(sponsor,id='continuation',scope_id=None,reference_id='turn',
        details={'continuation_range_owners':(
            {'range_id':'r','range_version_id':'v','reference_turn_id':'turn'},
            {'range_id':'other','range_version_id':'other-v','reference_turn_id':'turn'})})
    result=resolve_objectives((continuation,),{'H1':s},{'H1':bars},bars[-1].end,100,'BUY')
    assert not result.candidates
    assert any('continuation_range_versions_ambiguous' in d['reasons'] for d in result.diagnostics)

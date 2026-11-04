"""Owner-defined external confirmation: last known pre-touch A/V, not any break."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import pytest
from bishop.v2.types import Bar,Clock,Event,Turn,Level,StrategyPolicy
from bishop.v2.structure import StructureResult
from bishop.v2.stories import _confirm,_StoryStructureView,_last_pre_touch_reference

T=datetime(2026,1,5,tzinfo=timezone.utc)


def fixture(side='BUY',tf='H4',origin_tf='D'):
    def p(x):return x if side=='BUY' else 200-x
    def bar(hour,close=102):
        return Bar('X',tf,T+timedelta(hours=hour),T+timedelta(hours=hour+4),
                   p(102),p(125 if side=='BUY' else 90),p(90 if side=='BUY' else 125),p(close))
    lower=tuple(bar(h) for h in (8,12,16,20,24,28,32,36))
    def turn(ident,index,known,price):
        return Turn(id=ident,instrument='X',tf=tf,kind='H' if side=='BUY' else 'L',price_ticks=p(price),
                    formed_at=lower[index].end,available_at=T+timedelta(hours=known),
                    anchor_bar_id=lower[index].id,confirmation_bar_id=lower[index+1].id)
    old=turn('old',0,16,105);last=turn('last',2,24,110)
    def event(ident,ref,hour):
        at=T+timedelta(hours=hour)
        return Event(id=ident,kind='BREAKOUT',instrument='X',tf=tf,clock=Clock(at,at,at),
                     side=side,reference_id=ref.id,price_ticks=ref.price_ticks)
    old_break=event('a_old',old,32);external=event('z_external',last,36)
    origin=Bar('X',origin_tf,T+timedelta(hours=24),T+timedelta(hours=48),100,140,60,p(110))
    level=Level(id='kl',instrument='X',tf=origin_tf,kind='V' if side=='BUY' else 'A',side=side,price_ticks=100,formed_at=T,available_at=T)
    reaction=Event(id='reaction',kind='KL_REJECTION',instrument='X',tf=origin_tf,clock=origin.clock,side=side,
                   reference_id=level.id,price_ticks=100,details={'level_tf':origin_tf})
    structure=StructureResult((old,last),(),(),(old_break,external),())
    parent=StructureResult((),(level,),(),(),())
    return reaction,origin,lower,structure,{origin_tf:parent},old,last,external


@pytest.mark.parametrize('kind',['KL_REJECTION','PRIOR_CANDLE_SWEEP'])
@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('tf,origin_tf',[('H4','D'),('D','W')])
@pytest.mark.parametrize('indexed',[False,True])
def test_only_last_pre_touch_av_confirms_rejection(side,tf,origin_tf,indexed,kind):
    reaction,origin,lower,structure,parents,old,last,external=fixture(side,tf,origin_tf)
    prior=Bar('X',origin_tf,T,T+timedelta(hours=24),100,140,100,110)
    reaction=replace(reaction,kind=kind,reference_id=prior.id if kind=='PRIOR_CANDLE_SWEEP' else reaction.reference_id)
    origin_bars=(prior,origin) if kind=='PRIOR_CANDLE_SWEEP' else (origin,)
    view=_StoryStructureView(structure,lower) if indexed else structure
    answer=_confirm(reaction,origin,tf,lower,view,origin_bars,parents,reference_profile='last_pre_touch')
    assert answer[2].id==external.id
    assert answer[4]['frozen_reference_id']==last.id
    assert answer[4]['knowledge_cutoff']==T+timedelta(hours=24)
    assert answer[0]>=origin.available_at
    assert _confirm(reaction,origin,tf,lower,structure,origin_bars,parents)[2].reference_id==old.id
    missing=replace(structure,events=structure.events[:1])
    assert _confirm(reaction,origin,tf,lower,missing,origin_bars,parents,reference_profile='last_pre_touch') is None


def test_post_touch_and_future_turns_do_not_rewrite_frozen_reference():
    reaction,origin,lower,structure,parents,old,last,external=fixture()
    child=replace(last,id='child',formed_at=lower[4].end,available_at=lower[5].end,anchor_bar_id=lower[4].id)
    future=replace(last,id='future',formed_at=last.formed_at+timedelta(hours=1),available_at=T+timedelta(days=10))
    altered=replace(structure,turns=(*structure.turns,child,future))
    args=(reaction,origin,'H4',lower)
    assert _confirm(*args,altered,(origin,),parents,reference_profile='last_pre_touch')==_confirm(*args,structure,(origin,),parents,reference_profile='last_pre_touch')


def test_tied_anchor_is_held_without_hash_choice_and_other_segment_is_excluded():
    reaction,origin,lower,structure,parents,old,last,external=fixture()
    touch=lower[4]
    duplicate=replace(last,id='different_tied_anchor',price_ticks=111)
    assert _last_pre_touch_reference(touch,lower,replace(structure,turns=(*structure.turns,duplicate)),'BUY')[0] is None
    changed=tuple(replace(b,segment_id='old') if b.id==last.anchor_bar_id else b for b in lower)
    assert _last_pre_touch_reference(touch,changed,structure,'BUY')[0].id==old.id


def test_policy_requires_explicit_supported_reference_rule():
    assert StrategyPolicy().bias_reference_profile=='last_pre_touch'
    with pytest.raises(ValueError):StrategyPolicy(bias_reference_profile='nearest_break')


def test_complete_story_emits_frozen_and_confirmed_links_or_explicit_wait():
    from bishop.v2.stories import find_stories
    reaction,origin,lower,structure,parents,old,last,external=fixture()
    bars={'D':(origin,),'H4':lower}
    policy=StrategyPolicy(origin_tfs=('D',),entry_tfs=('H4',),bias_reference_profile='last_pre_touch')
    result=find_stories(bars,{**parents,'H4':structure},policy)
    assert len(result.stories)==1
    assert result.stories[0].confirmation_id==external.id
    assert result.stories[0].details['frozen_external_reference_id']==last.id
    assert any(e.kind=='BIAS_REFERENCE_FROZEN' and e.reference_id==last.id for e in result.events)
    assert any(e.kind=='REACTION_CONFIRMATION_LINK' and e.details['kind']=='FROZEN_LAST_PRE_TOUCH_AV' for e in result.events)
    pending=find_stories(bars,{**parents,'H4':replace(structure,events=structure.events[:1])},policy)
    assert not pending.stories
    assert any(e.kind=='BIAS_WAIT_EXTERNAL_BREAK' and e.evidence_status=='UNRESOLVED' for e in pending.events)


def test_wait_event_remains_after_later_external_confirmation_arrives():
    from bishop.v2.stories import find_stories
    reaction,origin,lower,structure,parents,old,last,external=fixture()
    later_at=origin.end+timedelta(hours=8)
    later=replace(external,clock=Clock(later_at,later_at,later_at))
    policy=StrategyPolicy(origin_tfs=('D',),entry_tfs=('H4',),bias_reference_profile='last_pre_touch')
    bars={'D':(origin,),'H4':lower}
    pending=find_stories(bars,{**parents,'H4':replace(structure,events=structure.events[:1])},policy)
    confirmed=find_stories(bars,{**parents,'H4':replace(structure,events=(*structure.events[:1],later))},policy)
    waits=lambda r:[e for e in r.events if e.kind=='BIAS_WAIT_EXTERNAL_BREAK']
    assert waits(pending)==waits(confirmed) and waits(pending)
    assert len(confirmed.stories)==1 and confirmed.stories[0].available_at==later_at


def test_actual_ohlc_wick_does_not_confirm_but_close_through_frozen_av_does():
    from bishop.v2.structure import analyze
    from bishop.v2.stories import find_stories
    closes=(100,110,105,108,106,106,107,107,109)
    bars=[];op=100
    for i,cl in enumerate(closes):
        hour=i*4
        hi=max(op,cl)+1;lo=min(op,cl)-1
        if hour==24:lo=99
        if hour==28:hi=110
        bars.append(Bar('X','H4',T+timedelta(hours=hour),T+timedelta(hours=hour+4),op,hi,lo,cl))
        op=cl
    origin=Bar('X','D',T+timedelta(hours=24),T+timedelta(hours=48),106,111,99,109)
    level=Level(id='origin-kl',instrument='X',tf='D',kind='V',side='BUY',price_ticks=100,formed_at=T,available_at=T)
    policy=StrategyPolicy(origin_tfs=('D',),entry_tfs=('H4',),bias_reference_profile='last_pre_touch')
    parent=StructureResult((),(level,),(),(),())
    def replay(lower):
        return find_stories({'D':(origin,),'H4':lower},{'D':parent,'H4':analyze(lower,policy)},policy)
    assert not replay(tuple(bars[:-1])).stories
    result=replay(tuple(bars))
    assert len(result.stories)==1
    assert result.stories[0].details['frozen_external_reference_ticks']==108
    assert result.stories[0].clock.occurred_from==bars[-1].end


def test_liquidity_sweep_requires_same_external_environment_without_a_key_level_gate():
    reaction,origin,lower,structure,parents,old,last,external=fixture()
    prior=Bar('X','D',T,T+timedelta(hours=24),100,140,100,110)
    liquidity=replace(reaction,kind='PRIOR_CANDLE_SWEEP',reference_id=prior.id)
    answer=_confirm(liquidity,origin,'H4',lower,structure,(prior,origin),parents,reference_profile='last_pre_touch')
    assert answer[2].reference_id==last.id
    assert answer[4]['kind']=='FROZEN_LAST_PRE_TOUCH_AV'
    comparison=_confirm(liquidity,origin,'H4',lower,structure,(prior,origin),parents,reference_profile='source_lineage')
    assert comparison[2].reference_id==old.id

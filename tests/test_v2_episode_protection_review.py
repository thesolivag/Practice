"""Causal protection checks with synthetic prices and real risk planning."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from bishop.v2.entries import _protection_episode_bars,detect_setups
from bishop.v2.risk import plan
from bishop.v2.structure import StructureResult
from bishop.v2.types import Bar,Clock,Event,Instrument,Level,Liquidity,StrategyPolicy

T=datetime(2026,1,5,tzinfo=timezone.utc)
I=Instrument('X','1','1',calendar_id='24x7_utc_v1')

def bar(h,high=103,close=101,segment='0',received=None):
    return Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),100,
               high,95,close,segment_id=segment,
               available_at=T+timedelta(hours=received) if received else None)

def test_linked_intermediate_high_is_protected_without_old_or_future_extremes():
    old,first,extension,reaction,future=bar(0,200),bar(1,105),bar(2,109),bar(3,102,99),bar(4,500)
    episode=_protection_episode_bars((first,),reaction,(old,first,extension,reaction,future))
    assert episode==(first,extension,reaction)
    assert _protection_episode_bars((first,),reaction,(old,first,extension,reaction,future),
        bar_starts=tuple(b.start for b in (old,first,extension,reaction,future)))==episode
    story=SimpleNamespace(details={},destination_ticks=None,destination_ref_id=None)
    risk=plan('SELL',98,reaction.end,'H1',(old,first,extension,reaction),(),(),story,I,
              StrategyPolicy(stop_buffer_units='5',target_profile='fixed3r'),protection_bars=episode)
    assert risk.stop_ticks==114  # Linked109 extreme plus declared5; neither200 nor500.

@pytest.mark.parametrize('broken', ['gap','segment','unpublished'])
def test_incomplete_episode_cannot_be_presented_as_full_origin_protection(broken):
    first,reaction=bar(1),bar(3,102,99)
    middle=bar(2,109,segment='new' if broken=='segment' else '0',received=6 if broken=='unpublished' else None)
    rows=(first,reaction) if broken=='gap' else (first,middle,reaction)
    assert _protection_episode_bars((first,),reaction,rows)==()
    assert _protection_episode_bars((first,),reaction,rows,bar_starts=tuple(b.start for b in rows))==()

def test_normal_bo_carries_episode_lineage_into_real_risk_and_freezes_at_setup():
    pool=Liquidity(id='pool',instrument='X',tf='H4',kind='HIGH',price_ticks=104,
                   formed_at=T+timedelta(hours=4),available_at=T+timedelta(hours=4),
                   form='BAR',details={'role':'IRL'})
    h4level=Level(id='context',instrument='X',tf='H4',kind='A',price_ticks=100,
                  side='SELL',formed_at=T,available_at=T)
    child=Level(id='child',instrument='X',tf='H1',kind='V',price_ticks=98,
                side='BUY',formed_at=T,available_at=T)
    parent=Event(id='parent',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(T,T,T),side='SELL',reference_id=h4level.id)
    first,extension,reaction,confirmation=bar(4,105,104),bar(5,109,104),bar(6,102,99),bar(7,101,97)
    child_break=Event(id='ce',kind='BREAKOUT',instrument='X',tf='H1',
                      clock=Clock(confirmation.end,confirmation.end,confirmation.end),side='SELL',
                      reference_id=child.id,bar_ids=(confirmation.id,))
    structures={'H4':StructureResult((),(h4level,),(pool,),(parent,),()),
                'H1':StructureResult((),(child,),(),(child_break,Event(id='flip',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='H1',clock=Clock(confirmation.end,confirmation.end,confirmation.end),side='SELL',reference_id=child.id)),())}
    story=SimpleNamespace(id='story',side='SELL',available_at=T,clock=Clock(T,T,T),
                          details={},destination_ticks=None,destination_ref_id=None)
    warmup=tuple(bar(h) for h in range(4))
    rows=(*warmup,first,extension,reaction,confirmation)
    policy=StrategyPolicy(entry_tfs=('H1',),origin_tfs=('D',),stop_buffer_units='5',target_profile='fixed3r')
    context_bar=Bar('X','H4',T,T+timedelta(hours=4),100,104,95,101)
    def replay(bs):
        return detect_setups({'H1':bs,'H4':(context_bar,)},structures,(story,),I,policy)
    initial=replay(rows)
    setup=next(s for s in initial.setups if s.model=='confirmation_bo')
    assert setup.stop_ticks==114
    assert setup.details['protection_episode_bar_ids']==(first.id,extension.id,reaction.id,confirmation.id)
    assert all(b.id in setup.evidence_ids for b in (first,extension,reaction))
    later=replay((*rows,bar(8,500)))
    assert next(s for s in later.setups if s.id==setup.id)==setup

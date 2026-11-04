"""A breakout authorizes a later retest of its exact invalidated A/V."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from bishop.v2.entries import detect_setups,_breakout_retest_level
from bishop.v2.simulation import simulate,Costs
from bishop.v2.structure import StructureResult,RoleIndex
from bishop.v2.types import Bar,Clock,Event,Instrument,Level,Liquidity,StrategyPolicy,Order

T=datetime(2026,1,5,tzinfo=timezone.utc)
I=Instrument('X','1','1',calendar_id='24x7_utc_v1')

def fixture(side='BUY',link='turn'):
    def p(x):return x if side=='BUY' else 200-x
    def b(h,o,hi,lo,c):
        return Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),p(o),
                   p(hi if side=='BUY' else lo),p(lo if side=='BUY' else hi),p(c))
    bars=(*(b(h,100,103,95,100) for h in range(4)),b(4,100,103,85,94),b(5,94,111,94,110))
    opposite='SELL' if side=='BUY' else 'BUY'
    level=Level(id='broken',instrument='X',tf='H1',kind='A' if side=='BUY' else 'V',
                price_ticks=p(100),side=opposite,formed_at=T,available_at=T,details={'turn_id':'turn'})
    near=Level(id='unrelated_nearer',instrument='X',tf='H1',kind='V' if side=='BUY' else 'A',
               price_ticks=p(109),side=side,formed_at=T,available_at=T)
    at=bars[-1].end
    event=Event(id='break',kind='BREAKOUT',instrument='X',tf='H1',clock=Clock(at,at,at),side=side,
                price_ticks=p(100),reference_id='turn' if link=='turn' else level.id,bar_ids=(bars[-1].id,))
    flip=Event(id='flip',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='H1',clock=event.clock,
               side=side,reference_id=level.id)
    return bars,level,near,event,flip,b

@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('link',['turn','level'])
def test_exact_broken_reference_beats_nearer_level_and_waits_for_retest(side,link):
    bars,level,near,event,flip,b=fixture(side,link)
    context=Level(id='context',instrument='X',tf='H4',kind='V' if side=='BUY' else 'A',
                  price_ticks=93 if side=='BUY' else 107,side=side,formed_at=T,available_at=T)
    pool=Liquidity(id='pool',instrument='X',tf='H4',kind='LOW' if side=='BUY' else 'HIGH',
                   price_ticks=90 if side=='BUY' else 110,formed_at=T,available_at=T,form='BAR',details={'role':'IRL'})
    parent=Event(id='parent',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(T,T,T),
                 side=side,reference_id=context.id)
    structures={'H1':StructureResult((),(level,near),(),(event,flip),()),
                'H4':StructureResult((),(context,),(pool,),(parent,),())}
    story=SimpleNamespace(id='story',side=side,available_at=T,clock=Clock(T,T,T),details={},
                          destination_ticks=None,destination_ref_id=None)
    policy=StrategyPolicy(entry_tfs=('H1',),source_profile='bishop_confirmation',
                          stop_buffer_units='5',target_profile='fixed3r')
    def replay(rows):
        return detect_setups({'H1':rows,'H4':(Bar('X','H4',T,T+timedelta(hours=4),100,110,80,100),)},
                             structures,(story,),I,policy)
    s=next(s for s in replay(bars).setups if s.model=='confirmation_bo')
    assert s.level_id==level.id and s.entry_ticks==100
    assert s.entry_ticks!=bars[-1].close_ticks and s.entry_ticks!=near.price_ticks
    assert s.order_type=='LIMIT' and s.details['entry_requires_later_retest']
    assert s.details['broken_level_id']==level.id
    order=Order(id='order',setup_id=s.id,instrument='X',tf='H1',model=s.model,side=side,
                kind=s.order_type,clock=s.clock,entry_ticks=s.entry_ticks,stop_ticks=s.stop_ticks,
                target_ticks=s.target_ticks)
    no_touch=b(6,110,112,106,111);touch=b(7,111,113,99,112)
    assert simulate((order,),(*bars,no_touch),I,Costs(),no_touch.end)['observations'][0]['fill_ticks'] is None
    obs=simulate((order,),(*bars,no_touch,touch),I,Costs(),touch.end)['observations'][0]
    assert obs['fill_ticks']=='100' and obs['fill_window']['start']==touch.start
    assert next(x for x in replay((*bars,no_touch,touch)).setups if x.id==s.id)==s
    # Historical reference diagnostics remain even when no setup could emit
    # before a later eligibility clock.
    bad=replace(event,reference_id='missing')
    bad_structures={**structures,'H1':replace(structures['H1'],events=(bad,flip))}
    historical=detect_setups({'H1':bars,'H4':(Bar('X','H4',T,T+timedelta(hours=4),100,110,80,100),)},
        bad_structures,(story,),I,policy,eligibility_start=bars[-1].end+timedelta(hours=1))
    assert not historical.setups
    assert any(row.get('reason')=='missing_breakout_level_link' and row.get('breakout_event_id')==event.id
               for row in historical.support)

@pytest.mark.parametrize('failure', ['missing','duplicate','wrong_price','preflipped','no_flip','future_level','equal_close','wrong_kind','wrong_event','wrong_bar','wrong_occurrence'])
def test_unproven_reference_has_no_nearest_level_fallback(failure):
    bars,level,near,event,flip,b=fixture()
    ce=bars[-1];levels=(level,near);events=(flip,)
    if failure=='missing':event=replace(event,reference_id='absent')
    elif failure=='duplicate':levels=(*levels,replace(level,id='duplicate'))
    elif failure=='wrong_price':event=replace(event,price_ticks=101)
    elif failure=='preflipped':events=(replace(flip,clock=Clock(ce.start,ce.start,ce.start)),)
    elif failure=='no_flip':events=()
    elif failure=='future_level':levels=(replace(level,available_at=ce.end),near)
    elif failure=='equal_close':ce=replace(ce,close_ticks=level.price_ticks)
    elif failure=='wrong_kind':levels=(replace(level,kind='V'),near)
    elif failure=='wrong_event':event=replace(event,instrument='OTHER')
    elif failure=='wrong_bar':event=replace(event,bar_ids=('another_candle',))
    elif failure=='wrong_occurrence':event=replace(event,clock=Clock(ce.start,ce.start,ce.available_at))
    chosen,reason=_breakout_retest_level(event,ce,levels,'BUY',RoleIndex(events).role_at)
    assert chosen is None and reason


def test_future_level_with_same_turn_link_cannot_erase_known_retest():
    bars,level,near,event,flip,b=fixture()
    future=replace(level,id='future_duplicate',formed_at=bars[-1].end,
                   available_at=bars[-1].end+timedelta(hours=1))
    lookup=RoleIndex((flip,)).role_at
    base=_breakout_retest_level(event,bars[-1],(level,near),'BUY',lookup)
    extended=_breakout_retest_level(event,bars[-1],(level,near,future),'BUY',lookup)
    assert base==(level,None) and extended==base

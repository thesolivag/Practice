"""An entry's own engulfing, rather than a prior context excursion, defines risk."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from bishop.v2.entries import detect_setups
from bishop.v2.structure import StructureResult
from bishop.v2.types import Bar,Clock,Event,Instrument,Level,Liquidity,StrategyPolicy

T=datetime(2026,1,5,tzinfo=timezone.utc)

@pytest.mark.parametrize('target_profile',['fixed3r','context_h4_kl'])
@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('delayed',[False,True])
def test_successive_engulfings_keep_separate_stop_candles_and_context(side,delayed,target_profile):
    def price(n): return n if side=='BUY' else 200-n
    def bar(h,o,hi,lo,c):
        return Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),
                   price(o),price(hi if side=='BUY' else lo),
                   price(lo if side=='BUY' else hi),price(c))
    first_ref=bar(4,100,102,85,95)
    first_ce=bar(5,95,110,94,108)
    mitigation=bar(6,105,109,98 if delayed else 99,101)
    second_ce=bar(7,101 if delayed else 100,112,101 if delayed else 100,110)
    following=bar(8,110,113,100,111)
    rows=(*(bar(h,100,102,96,100) for h in range(4)),first_ref,first_ce,mitigation,second_ce)
    context=Level(id='context',instrument='X',tf='H4',kind='V' if side=='BUY' else 'A',
                  price_ticks=price(94),side=side,formed_at=T,available_at=T)
    levels=tuple(Level(id=f'entry{idx}',instrument='X',tf='H1',kind='V' if side=='BUY' else 'A',
                       price_ticks=price(entry),side=side,formed_at=ref.start,available_at=ce.end)
                 for idx,ref,ce,entry in ((1,first_ref,first_ce,100),(2,mitigation,second_ce,99 if delayed else 105)))
    parent=Event(id='parent',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(T,T,T),
                 side=side,reference_id=context.id)
    pool=Liquidity(id='pool',instrument='X',tf='H4',kind='LOW' if side=='BUY' else 'HIGH',
                   price_ticks=price(90),formed_at=T,available_at=T,form='BAR',details={'role':'IRL'})
    objective=Level(id='h4exit',instrument='X',tf='H4',kind='OC',price_ticks=price(130),
                    side='SELL' if side=='BUY' else 'BUY',formed_at=T,available_at=T)
    structures={'H4':StructureResult((),(context,objective),(pool,),(parent,),()),
                'H1':StructureResult((),levels,(),(),())}
    story=SimpleNamespace(id='story',side=side,available_at=T,clock=Clock(T,T,T),details={},
                          destination_ticks=None,destination_ref_id=None)
    instrument=Instrument('X','1','1',calendar_id='24x7_utc_v1')
    policy=StrategyPolicy(source_profile='bishop_confirmation',entry_tfs=('H1',),
                          stop_buffer_units='5',target_profile=target_profile,near_atr_period=2 if delayed else 14,near_atr_fraction='1')
    def replay(bs,lower=None):
        return detect_setups({'H1':bs,'H4':(Bar('X','H4',T,T+timedelta(hours=4),100,110,80,100),)},structures,(story,),instrument,policy,eligibility_start=lower)
    result=replay(rows)
    first=next(s for s in result.setups if s.model=='engulf_av_retest' and s.available_at==first_ce.end)
    second=next(s for s in result.setups if s.model=='engulf_av_retest' and s.available_at==second_ce.end)
    if target_profile=='context_h4_kl':
        assert first.target_ticks==second.target_ticks==objective.price_ticks
        assert second.status=='ELIGIBLE'
        assert second.details['target_plan']['context_objective']['objective_ref_id']==objective.id
    assert first.stop_ticks==(80 if side=='BUY' else 120)
    assert second.stop_ticks==((93 if side=='BUY' else 107) if delayed else (94 if side=='BUY' else 106))
    assert second.details['confirmation_protection_bar_ids']==(mitigation.id,second_ce.id)
    assert first_ref.id in second.evidence_ids  # Context is retained, not used as pattern risk.
    assert first_ref.id not in second.details['protection_evidence_ids']
    assert {o[0] for o in second.details['protected_objects']}==({mitigation.id} if delayed else {mitigation.id,second_ce.id})
    assert all(s.available_at!=second_ce.end for s in replay(rows[:-1]).setups)
    if delayed:
        delayed_result=replay((*rows,following))
        late=next(s for s in delayed_result.setups if s.model=='engulf_irl_retest' and s.available_at==following.end)
        assert late.details['confirmation_protection_bar_ids']==(mitigation.id,second_ce.id,following.id)
        assert late.stop_ticks==second.stop_ticks
        restricted=replay((*rows,following),following.end)
        assert next(s for s in restricted.setups if s.id==late.id)==late
        assert not any(s.available_at<following.end for s in restricted.setups)
    future=bar(9 if delayed else 8,110,180,20,100)
    assert next(s for s in replay((*rows,*((following,) if delayed else ()),future)).setups if s.id==second.id)==second

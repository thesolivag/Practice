"""Publication-causal execution recovery; no remote data or backtest."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import pytest
from bishop.v2.types import Bar,Clock,Order,Instrument
from bishop.v2.simulation import Costs,simulate
from bishop.v2.refinement_evidence import RefinementEvidence
from bishop.v2.types import _freeze

T=datetime(2026,1,1,tzinfo=timezone.utc)
INST=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')


def evidence(coarse=(),ticks=None):
    return RefinementEvidence('proof',tuple(coarse),tuple(b.start for b in coarse),_freeze(ticks or {}),_freeze({}))


def order(side='BUY',entry=100,stop=90,target=120,expires=None,at=T):
    return Order(id='o',setup_id='s',instrument='X',tf='M1',model='test',side=side,
                 kind='LIMIT',clock=Clock(at,at,at),entry_ticks=entry,stop_ticks=stop,
                 target_ticks=target,expires_at=expires)


def test_gap_proof_delays_dependent_fill_and_exit_until_h1_publication():
    # Gap at00:00–00:01: H1 proves entry was untouched. Subsequent fill/TP
    # occurs in01:00's gap-free minutes, after the proof's publication.
    coarse=Bar('X','H1',T,T+timedelta(hours=1),110,115,105,110)
    b1=Bar('X','M1',T+timedelta(hours=1),T+timedelta(hours=1,minutes=1),110,111,95,100)
    b2=Bar('X','M1',b1.end,b1.end+timedelta(minutes=1),100,125,99,121)
    r=simulate((order(),),(b1,b2),INST,Costs(),b2.end,refinement_evidence=evidence((coarse,)))
    assert r['observations'][0]['outcome']=='WIN'
    assert all(e.available_at>=coarse.available_at for e in r['events'] if e.kind!='ORDER_SUBMITTED')


def test_later_h1_bounds_cannot_release_exposure_early_or_backdate_events():
    # The entire H1 stays above BUY100. An order cancelled during the missing
    # minute is only known cancelled once this hour's no-touch proof arrives.
    coarse=Bar('X','H1',T,T+timedelta(hours=1),110,115,105,110)
    b=Bar('X','M1',T+timedelta(minutes=2),T+timedelta(minutes=3),110,111,109,110)
    acts=({'order_id':'o','kind':'CANCEL','available_at':T+timedelta(minutes=1)},)
    early=simulate((order(),),(b,),INST,Costs(),T+timedelta(minutes=30),acts,
                   refinement_evidence=evidence((coarse,)))
    assert early['observations'][0]['outcome']=='CENSORED'
    late=simulate((order(),),(b,),INST,Costs(),coarse.end,acts,refinement_evidence=evidence((coarse,)))
    assert late['observations'][0]['outcome']=='CANCELLED'
    ev=next(e for e in late['events'] if e.kind=='ORDER_CANCELLED')
    assert ev.clock.occurred_to==T+timedelta(minutes=1)
    assert ev.available_at==coarse.available_at


@pytest.mark.parametrize('result',['TARGET_AFTER_ENTRY','FILLED_WITHOUT_EXIT_IN_MINUTE'])
def test_tick_proof_continues_filled_trade_or_closes_only_proven_target(result):
    b=Bar('X','M1',T,T+timedelta(minutes=1),95,105,75,90)
    # SELL100/TP80: low could precede fill, close alone cannot decide.
    ms=int(T.timestamp()*1000)
    ticks=((ms,95),(ms+1,100),(ms+2,79 if result=='TARGET_AFTER_ENTRY' else 90))
    r=simulate((order('SELL',100,110,80),),(b,),INST,Costs(),b.end,
               refinement_evidence=evidence(ticks={b.id:(b.available_at,ticks)}))
    assert r['observations'][0]['outcome']==('WIN' if result=='TARGET_AFTER_ENTRY' else 'OPEN')
    assert all(e.available_at>=b.available_at for e in r['events'] if e.kind!='ORDER_SUBMITTED')


def test_expiry_before_later_missing_interval_is_not_censored():
    at=datetime(2026,6,5,21,tzinfo=timezone.utc)  # FX Friday close
    expires=at+timedelta(hours=24)
    first=datetime(2026,6,7,21,1,tzinfo=timezone.utc)
    b=Bar('X','M1',first,first+timedelta(minutes=1),110,111,109,110)
    inst=Instrument('X','1','1')
    r=simulate((order(at=at,expires=expires),),(b,),inst,Costs(),b.end,
               refinement_evidence=evidence())
    assert r['observations'][0]['outcome']=='EXPIRED'
    assert next(e for e in r['events'] if e.kind=='ORDER_EXPIRED').available_at==expires


@pytest.mark.parametrize('later_bar',[False,True])
def test_position_change_inside_gap_cannot_use_stale_bounds(later_bar):
    first=Bar('X','M1',T,T+timedelta(minutes=1),110,111,109,110)
    coarse=Bar('X','H1',T,T+timedelta(hours=1),110,115,105,110)
    bars=(first,)
    if later_bar:
        bars+=(Bar('X','M1',T+timedelta(minutes=3),T+timedelta(minutes=4),110,111,107,110),)
    action=({'order_id':'o','kind':'AMEND','available_at':first.end,'stop_ticks':108},)
    result=simulate((order(entry=110),),bars,INST,Costs(),coarse.end,action,
                    refinement_evidence=evidence((coarse,)))
    assert result['observations'][0]['outcome']=='CENSORED'
    assert result['observations'][0]['censor_reason']=='MISSING_ACTIVE_DATA'
    assert not any(e.kind=='POSITION_AMENDED' for e in result['events'])

"""Causal later near-KL pool formation, independent of teacher-price fixtures."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import pytest
from bishop.v2.types import Bar,Clock,Event,Level,StrategyPolicy
from bishop.v2.liquidity_forms import later_kl_irl
T=datetime(2026,1,1,tzinfo=timezone.utc)
P=StrategyPolicy()
def bar(hour,high=105,low=95,**kw):
    return Bar('X','H4',T+timedelta(hours=hour),T+timedelta(hours=hour+4),100,high,low,100,**kw)
def event(kind='BREAKOUT',hour=4,side='SELL',**kw):
    at=T+timedelta(hours=hour)
    return Event(id=kind+str(hour)+side,kind=kind,instrument='X',tf='H4',clock=Clock(at,at,at),side=side,scope_id='scope',**kw)
def level(price=110,side='SELL',id='kl',**kw):
    return Level(id=id,instrument='X',tf='H4',kind='A' if side=='SELL' else 'V',price_ticks=price,side=side,formed_at=T,available_at=T,**kw)
def run(bs=None,ls=None,es=None):
    return later_kl_irl(bs or (bar(0),bar(4,high=107)),ls or (level(),),es or (event(),),P)
@pytest.mark.parametrize('side',['BUY','SELL'])
def test_mirrored_later_approach_publishes_at_own_close(side):
    bs=(bar(0),bar(4,high=107,low=93))
    result=run(bs,(level(110 if side=='SELL' else 90,side),),(event(side=side),))
    assert len(result)==1
    pool=result[0]
    assert pool.kind==('HIGH' if side=='SELL' else 'LOW')
    assert pool.available_at==bs[1].available_at
    assert pool.details['reaction_level_id']=='kl' and pool.details['parent_break_id']==event(side=side).id
    assert not run((bs[0],),(level(110 if side=='SELL' else 90,side),),(event(side=side),))
@pytest.mark.parametrize('high',[110,111])
def test_touch_or_cross_cannot_be_inducement(high):
    assert not run((bar(0),bar(4,high=high)))
def test_future_sweep_does_not_change_existing_pool():
    before=run();after=run((bar(0),bar(4,high=107),bar(8,high=115)))
    assert before==tuple(p for p in after if p.available_at<=T+timedelta(hours=8))
def test_publication_delay_is_retained_and_unpublished_previous_is_rejected():
    delayed=bar(4,high=107,available_at=T+timedelta(hours=10))
    assert run((bar(0),delayed))[0].available_at==delayed.available_at
    assert not run((bar(0,available_at=T+timedelta(hours=5)),delayed))
@pytest.mark.parametrize('rows',[(bar(0),bar(8,high=107)),(bar(0),bar(4,high=107,segment_id='new'))])
def test_gap_does_not_link_bars_or_old_parent(rows):
    assert not run(rows)
def test_role_loss_during_formation_blocks_pool_even_if_restored():
    loss=event('LEVEL_ROLE_CHANGE',5,'BUY',reference_id='kl')
    restored=event('LEVEL_ROLE_CHANGE',6,'SELL',reference_id='kl')
    assert not run(es=(event(),loss,restored))
def test_future_parent_and_future_level_cannot_authorize_pool():
    assert not run(es=(event(hour=8),))
    unborn=replace(level(),formed_at=T+timedelta(hours=5),available_at=T+timedelta(hours=5))
    assert not run(ls=(unborn,))
def test_nearest_usable_level_is_selected_before_future_outcome():
    pool=run(ls=(level(120,id='far'),level(110,id='near'),level(90,'BUY',id='wrong')))[0]
    assert pool.details['reaction_level_id']=='near'
def test_same_scope_break_retires_parent_during_approach():
    assert not run(es=(event(),event('RANGE_BROKEN',6,'BUY')))

def test_later_contiguous_pair_cannot_bridge_an_earlier_missing_bar():
    assert not run((bar(0),bar(8),bar(12,high=107)))

"""A terminal close proves post-entry target contact, never both-hit ordering."""
from datetime import datetime, timedelta, timezone
import pytest
from bishop.v2.types import Bar, Clock, Instrument, Order
from bishop.v2.simulation import simulate, Costs

T=datetime(2026,1,1,tzinfo=timezone.utc)
INST=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')


@pytest.mark.parametrize('side,ohlc,entry,stop,target,spread,expected',[
    ('SELL',(139038,139065,139038,139050),139058,139096,139057,0,'WIN'),
    ('BUY',(100,125,95,121),100,90,120,0,'WIN'),
    ('SELL',(100,105,75,79),100,110,80,1,'WIN'),
    # Bid closes at SELL target; ask does not: sequence remains unknown.
    ('SELL',(100,105,75,80),100,110,80,1,'CENSORED'),
    ('BUY',(100,125,95,110),100,90,120,0,'CENSORED'),
    ('SELL',(139035,139044,139022,139038),139039,139127,139026,0,'CENSORED'),
    ('BUY',(100,125,85,121),100,90,120,0,'CENSORED'),
    ('SELL',(100,115,75,79),100,110,80,0,'CENSORED'),
    # Do not broaden this proof into a new same-bar stop convention.
    ('BUY',(100,105,85,95),100,90,120,0,'CENSORED'),
])
def test_terminal_price_proof_is_narrow_and_spread_aware(side,ohlc,entry,stop,target,spread,expected):
    order=Order(id='o',setup_id='s',instrument='X',tf='M1',model='test',side=side,
                kind='LIMIT',clock=Clock(T,T,T),entry_ticks=entry,stop_ticks=stop,target_ticks=target)
    bar=Bar('X','M1',T,T+timedelta(minutes=1),*ohlc)
    result=simulate((order,),(bar,),INST,Costs(spread_ticks=spread),bar.end)
    assert result['observations'][0]['outcome']==expected
    if expected=='WIN':
        target_event=next(e for e in result['events'] if e.kind=='POSITION_TARGET')
        assert target_event.available_at==bar.available_at


def test_terminal_price_is_not_available_before_bar_publication():
    order=Order(id='o',setup_id='s',instrument='X',tf='M1',model='test',side='SELL',
                kind='LIMIT',clock=Clock(T,T,T),entry_ticks=100,stop_ticks=110,target_ticks=80)
    bar=Bar('X','M1',T,T+timedelta(minutes=1),100,105,75,79)
    result=simulate((order,),(bar,),INST,Costs(),T+timedelta(seconds=30))
    assert not any(e.kind=='POSITION_TARGET' for e in result['events'])
    assert result['observations'][0]['outcome']!='WIN'

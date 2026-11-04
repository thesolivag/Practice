"""Independent parent-episode validity at terminal nested confirmation."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from types import SimpleNamespace
import pytest
from bishop.v2.types import Bar,Clock,Event,Instrument,Level,Liquidity,StrategyPolicy
from bishop.v2.structure import StructureResult
import bishop.v2.entries as entries

T=datetime(2026,1,5,tzinfo=timezone.utc)


@pytest.mark.parametrize('same_close',[False,True])
def test_parent_role_loss_after_h1_standing_blocks_later_lower_engulf(monkeypatch,same_close):
    def h1(hour,high=103,low=95,close=101):
        return Bar('X','H1',T+timedelta(hours=hour),T+timedelta(hours=hour+1),100,high,low,close)
    context=Level(id='context',instrument='X',tf='H4',kind='A',price_ticks=100,side='SELL',formed_at=T,available_at=T)
    hourly=Level(id='hourly',instrument='X',tf='H1',kind='A',price_ticks=100,side='SELL',formed_at=T,available_at=T)
    pool=Liquidity(id='pool',instrument='X',tf='H4',kind='HIGH',price_ticks=104,
                   formed_at=T+timedelta(hours=4),available_at=T+timedelta(hours=4),
                   form='BAR',details={'role':'IRL'})
    parent=Event(id='parent',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(T,T,T),
                 side='SELL',scope_id='parent_range',reference_id=context.id)
    first,extension,reaction=h1(4,105,95,104),h1(5,106,95,104),h1(6,102,95,99)
    breakout=Bar('X','H1',T+timedelta(hours=7),T+timedelta(hours=8),99,99,95,97)
    a,b=h1(8,103,95,99),h1(9,105,96,98)
    h1break=Event(id='hourly_break',kind='BREAKOUT',instrument='X',tf='H1',
                  clock=Clock(breakout.end,breakout.end,breakout.end),side='SELL',
                  reference_id=hourly.id,bar_ids=(breakout.id,))
    lower_hour=9 if same_close else 10
    x=Bar('X','M30',T+timedelta(hours=lower_hour),T+timedelta(hours=lower_hour,minutes=30),100,105,99,102)
    y=Bar('X','M30',x.end,T+timedelta(hours=lower_hour+1),102,103,96,98)
    child=Level(id='child',instrument='X',tf='M30',kind='A',price_ticks=101,side='SELL',
                formed_at=x.end,available_at=y.end)
    context_bar=Bar('X','H4',T,T+timedelta(hours=4),100,104,95,101)
    rows={'H4':(context_bar,),'H1':(*tuple(h1(h) for h in range(4)),first,extension,reaction,breakout,a,b),'M30':(x,y)}
    story=SimpleNamespace(id='story',side='SELL',available_at=T,clock=Clock(T,T,T),details={})
    risk_calls=[]
    def risk(*args,**kwargs):
        risk_calls.append(kwargs)
        return SimpleNamespace(stop_ticks=110,target_ticks=90,status='ELIGIBLE',details={'unresolved_reasons':[]})
    monkeypatch.setattr(entries,'plan',risk)
    def replay(extra=()):
        structures={'H4':StructureResult((),(context,),(pool,),(parent,*extra),()),
                    'H1':StructureResult((),(hourly,),(),(h1break,),()),
                    'M30':StructureResult((),(child,),(),(),())}
        return entries.detect_setups(rows,structures,(story,),Instrument('X','1','1',calendar_id='24x7_utc_v1'),
                                     StrategyPolicy(source_profile='nested_confirmation',entry_tfs=('M30',),origin_tfs=('D',)))
    baseline=replay()
    setup=next(s for s in baseline.setups if s.model=='nested_confirmation')
    assert setup.available_at==max(b.available_at,y.available_at)
    assert setup.details['confirmation_protection_bar_ids']==(x.id,y.id)
    assert risk_calls[-1]['protection_bars']==(x,y)
    assert b.id in setup.evidence_ids and a.id in setup.evidence_ids
    saved=rows
    rows={**saved,'M30':(x,)}
    assert not replay().setups  # Lower engulf not published yet.
    rows=saved
    if same_close:
        early_x=replace(x,start=x.start-timedelta(minutes=30),end=x.end-timedelta(minutes=30),available_at=x.available_at-timedelta(minutes=30))
        early_y=replace(y,start=y.start-timedelta(minutes=30),end=y.end-timedelta(minutes=30),available_at=y.available_at-timedelta(minutes=30))
        rows={**saved,'M30':(early_x,early_y)}
        assert not replay().setups  # Cannot precede parent confirmation close.
        delayed_b=replace(b,available_at=b.end+timedelta(minutes=30))
        rows={**saved,'H1':(*saved['H1'][:-1],delayed_b)}
        delayed_setup=next(s for s in replay().setups if s.model=='nested_confirmation')
        assert delayed_setup.available_at==delayed_b.available_at
        failed_at=b.end+timedelta(minutes=15)
        late_loss=Event(id='late_parent_loss',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='H4',
                        clock=Clock(failed_at,failed_at,failed_at),side='BUY',reference_id=context.id)
        assert not replay((late_loss,)).setups
        rows=saved
    loss_at=x.start+timedelta(minutes=15)
    role_loss=Event(id='parent_role_lost',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='H4',
                    clock=Clock(loss_at,loss_at,loss_at),side='BUY',reference_id=context.id)
    actual=replay((role_loss,))
    assert not any(s.model=='nested_confirmation' for s in actual.setups)

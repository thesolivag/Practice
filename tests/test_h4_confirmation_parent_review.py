"""A sibling/internal break cannot steal a declared H4 inducement episode."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
import bishop.v2.entries as entries
from bishop.v2.structure import StructureResult
from bishop.v2.types import Bar,Clock,Event,Instrument,Level,Liquidity,StrategyPolicy

T=datetime(2026,1,5,tzinfo=timezone.utc)


@pytest.mark.parametrize('tf,minutes',[('H2',120),('H1',60),('M45',45),('M30',30)])
@pytest.mark.parametrize('side',['SELL','BUY'])
@pytest.mark.parametrize('replacement',['sibling','unscoped','same_scope','wrong_parent','wrong_level'])
def test_confirmation_preserves_declared_h4_parent_only_while_episode_valid(monkeypatch,tf,minutes,side,replacement):
    step=timedelta(minutes=minutes)
    def price(n):return n if side=='SELL' else 200-n
    def bar(i,high=101,low=98,close=100):
        return Bar('X',tf,T+i*step,T+(i+1)*step,price(100),price(high if side=='SELL' else low),price(low if side=='SELL' else high),price(close))
    warm=tuple(bar(i) for i in range(4))
    first,extension,rejection,confirmation=bar(4,105,98,104),bar(5,103,98,102),bar(6,102,98,99),bar(7,101,96,97)
    h4bar=Bar('X','H4',T-timedelta(hours=4),T,100,price(104 if side=='SELL' else 98),price(98 if side=='SELL' else 104),price(101))
    context=Level(id='context',instrument='X',tf='H4',kind='A' if side=='SELL' else 'V',price_ticks=100,side=side,formed_at=h4bar.start,available_at=T)
    child=Level(id='child',instrument='X',tf=tf,kind='V' if side=='SELL' else 'A',price_ticks=price(98),side='BUY' if side=='SELL' else 'SELL',formed_at=T,available_at=T)
    parent=Event(id='parent',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(T,T,T),side=side,scope_id='root',reference_id=context.id)
    later_at=extension.end
    later=Event(id='later_internal',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(later_at,later_at,later_at),side=side,scope_id='root' if replacement=='same_scope' else None if replacement=='unscoped' else 'sibling')
    pool=Liquidity(id='declared_pool',instrument='X',tf='H4',kind='HIGH' if side=='SELL' else 'LOW',price_ticks=price(104),formed_at=first.start,available_at=first.start,
                   form='BAR',details={'role':'IRL','parent_break_id':'missing_parent' if replacement=='wrong_parent' else parent.id,
                                       'reaction_level_id':'other_level' if replacement=='wrong_level' else context.id})
    end=confirmation.end
    lower_break=Event(id='lower_break',kind='BREAKOUT',instrument='X',tf=tf,clock=Clock(end,end,end),side=side,reference_id=child.id,bar_ids=(confirmation.id,))
    flip=Event(id='flip',kind='LEVEL_ROLE_CHANGE',instrument='X',tf=tf,clock=Clock(end,end,end),side=side,reference_id=child.id)
    story=SimpleNamespace(id='story',side=side,available_at=T,clock=Clock(T,T,T),details={})
    monkeypatch.setattr(entries,'plan',lambda *a,**k:SimpleNamespace(stop_ticks=price(110),target_ticks=price(90),status='ELIGIBLE',details={'unresolved_reasons':[]}))
    def replay(extra=()):
        structures={'H4':StructureResult((),(context,),(pool,),(parent,*extra),()),
                    tf:StructureResult((),(child,),(),(lower_break,flip),())}
        return entries.detect_setups({'H4':(h4bar,),tf:(*warm,first,extension,rejection,confirmation)},structures,(story,),
                                     Instrument('X','1','1',calendar_id='24x7_utc_v1'),StrategyPolicy(entry_tfs=(tf,),origin_tfs=('D',)))
    baseline=[s for s in replay().setups if s.model=='confirmation_bo']
    actual=[s for s in replay((later,)).setups if s.model=='confirmation_bo']
    if replacement in ('sibling','unscoped'):
        assert len(baseline)==len(actual)==1
        assert actual[0]==baseline[0]
        assert parent.id in actual[0].evidence_ids and later.id not in actual[0].evidence_ids
        take=next(e for e in replay((later,)).events if e.kind=='LIQUIDITY_FIRST_TAKEN')
        assert take.id in actual[0].evidence_ids and take.bar_ids==(first.id,)
    elif replacement=='same_scope':
        assert baseline and not actual
    else:
        assert not baseline and not actual


@pytest.mark.parametrize('scope',['sibling','root'])
def test_nested_confirmation_uses_same_declared_parent_linkage(monkeypatch,scope):
    def h1(hour,high=103,low=95,close=101):
        return Bar('X','H1',T+timedelta(hours=hour),T+timedelta(hours=hour+1),100,high,low,close)
    context=Level(id='context',instrument='X',tf='H4',kind='A',price_ticks=100,side='SELL',formed_at=T,available_at=T)
    hourly=Level(id='hourly',instrument='X',tf='H1',kind='A',price_ticks=100,side='SELL',formed_at=T,available_at=T)
    parent=Event(id='parent',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(T,T,T),side='SELL',scope_id='root',reference_id=context.id)
    pool=Liquidity(id='pool',instrument='X',tf='H4',kind='HIGH',price_ticks=104,
                   formed_at=T+timedelta(hours=4),available_at=T+timedelta(hours=4),form='BAR',
                   details={'role':'IRL','parent_break_id':parent.id,'reaction_level_id':context.id})
    later_at=T+timedelta(hours=6)
    later=Event(id='later_internal',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(later_at,later_at,later_at),side='SELL',scope_id=scope)
    first,extension,reaction=h1(4,105,95,104),h1(5,106,95,104),h1(6,102,95,99)
    breakout=Bar('X','H1',T+timedelta(hours=7),T+timedelta(hours=8),99,99,95,97)
    a,b=h1(8,103,95,99),h1(9,105,96,98)
    hourly_break=Event(id='hourly_break',kind='BREAKOUT',instrument='X',tf='H1',clock=Clock(breakout.end,breakout.end,breakout.end),side='SELL',reference_id=hourly.id,bar_ids=(breakout.id,))
    x=Bar('X','M30',T+timedelta(hours=10),T+timedelta(hours=10,minutes=30),100,105,99,102)
    y=Bar('X','M30',x.end,T+timedelta(hours=11),102,103,96,98)
    child=Level(id='child',instrument='X',tf='M30',kind='A',price_ticks=101,side='SELL',formed_at=x.end,available_at=y.end)
    frames={'H4':(Bar('X','H4',T-timedelta(hours=4),T,100,104,95,101),),
            'H1':(*(h1(h) for h in range(4)),first,extension,reaction,breakout,a,b),'M30':(x,y)}
    story=SimpleNamespace(id='story',side='SELL',available_at=T,clock=Clock(T,T,T),details={})
    monkeypatch.setattr(entries,'plan',lambda *a,**k:SimpleNamespace(stop_ticks=110,target_ticks=90,status='ELIGIBLE',details={'unresolved_reasons':[]}))
    def replay(extra=()):
        structures={'H4':StructureResult((),(context,),(pool,),(parent,*extra),()),
                    'H1':StructureResult((),(hourly,),(),(hourly_break,),()),'M30':StructureResult((),(child,),(),(),())}
        return entries.detect_setups(frames,structures,(story,),Instrument('X','1','1',calendar_id='24x7_utc_v1'),
                                     StrategyPolicy(source_profile='nested_confirmation',entry_tfs=('M30',),origin_tfs=('D',)))
    baseline=next(s for s in replay().setups if s.model=='nested_confirmation')
    actual=tuple(s for s in replay((later,)).setups if s.model=='nested_confirmation')
    if scope=='sibling':
        assert actual==(baseline,)
        assert parent.id in actual[0].evidence_ids and later.id not in actual[0].evidence_ids
    else:
        assert not actual

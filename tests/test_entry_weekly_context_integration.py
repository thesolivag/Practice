"""Submission context refresh must not rewrite the initial source story."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import bishop.v2.entries as entries
from bishop.v2.risk import plan
from bishop.v2.structure import StructureResult
from bishop.v2.types import Bar, Clock, Event, Instrument, Level, Liquidity, StrategyPolicy

T = datetime(2026,5,8,21,tzinfo=timezone.utc)


@pytest.mark.parametrize('weekly_side,allow,initially_blocked,expected',[
    ('BUY',True,False,'ALIGNED'), ('SELL',True,False,'COUNTER_WEEKLY'),
    ('BUY',False,True,'ALIGNED'), ('SELL',False,False,None),
])
def test_direct_submission_uses_same_clock_weekly_context(monkeypatch,weekly_side,allow,initially_blocked,expected):
    bars=tuple(Bar('X','H4',T+timedelta(hours=h),T+timedelta(hours=h+4),
                   100,110+h,90-h,105) for h in (0,4,8))
    level=Level(id='level',instrument='X',tf='H4',kind='V',price_ticks=95,
                side='BUY',formed_at=T,available_at=T)
    parent=Event(id='break',kind='BREAKOUT',instrument='X',tf='H4',side='BUY',
                 clock=Clock(bars[0].start,bars[0].end,bars[0].end),bar_ids=(bars[0].id,))
    pool=Liquidity(id='pool',instrument='X',tf='H4',kind='LOW',price_ticks=98,
                   formed_at=bars[-1].end,available_at=bars[-1].end,form='BAR',
                   details={'role':'IRL','breakout_id':parent.id,'reaction_level_id':level.id})
    original=SimpleNamespace(id='old',instrument='X',origin_tf='H4',side='BUY',available_at=T,
        clock=Clock(T,T,T),destination_ticks=None,destination_ref_id=None,
        details={'initial_weekly_relation':'COUNTER_WEEKLY','counterweekly_target_guard_required':True,
                 'owner_selection':'BLOCKED_COUNTERWEEKLY' if initially_blocked else 'CANDIDATE'})
    weekly=SimpleNamespace(id='new_weekly',instrument='X',origin_tf='W',side=weekly_side,
        available_at=bars[-1].end,clock=Clock(bars[-1].end,bars[-1].end,bars[-1].end),
        destination_ticks=None,destination_ref_id=None,details={'scope_type':'ROOT'})
    before=deepcopy(original)
    observed=[]
    def risk(*args,**kwargs):
        effective=args[7]
        if effective.id==original.id and args[2]==pool.available_at:observed.append(effective)
        return SimpleNamespace(stop_ticks=80,target_ticks=130,status='ELIGIBLE',details={'unresolved_reasons':[]})
    monkeypatch.setattr(entries,'plan',risk)
    result=entries.detect_setups({'H4':bars},
        {'H4':StructureResult((),(level,),(pool,),(parent,),())},(original,weekly),
        Instrument('X','1','1',calendar_id='24x7_utc_v1'),
        StrategyPolicy(source_profile='owner_aggressive',entry_tfs=('H4',),allow_counterweekly=allow))
    selected=[s for s in result.setups if s.story_id==original.id and pool.id in s.liquidity_ids]
    assert original==before
    if expected is None:
        assert not selected and not observed
    else:
        assert len(selected)==1 and len(observed)==1
        assert selected[0].details['entry_weekly_relation']==expected
        assert selected[0].details['entry_weekly_context']['story_ids']==('new_weekly',)
        assert observed[0].details['entry_weekly_relation']==expected
        assert observed[0].details['initial_weekly_relation']=='COUNTER_WEEKLY'


@pytest.mark.parametrize('relation,retracement,initial,target,status',[
    ('ALIGNED',False,'COUNTER_WEEKLY',130,'ELIGIBLE'),
    ('ALIGNED',True,'COUNTER_WEEKLY',110,'ELIGIBLE'),
    ('COUNTER_WEEKLY',False,'ALIGNED',110,'ELIGIBLE'),
    ('UNKNOWN',False,'COUNTER_WEEKLY',110,'ELIGIBLE'),
    ('CONFLICTED',False,'ALIGNED',130,'UNRESOLVED'),
])
def test_real_risk_refreshes_guard_and_preserves_retracement(relation,retracement,initial,target,status):
    level=Level(id='obstacle',instrument='X',tf='H1',kind='A',price_ticks=110,
                side='SELL',formed_at=T,available_at=T)
    pool=Liquidity(id='external',instrument='X',tf='H1',kind='HIGH',price_ticks=130,
                   formed_at=T,available_at=T)
    active=SimpleNamespace(id='range',version_id='v',available_at=T,status='DEFINED',
        details={'endpoint_stage':'CONFIRMED_DELIVERY'},direction='BUY',origin_ticks=80,
        endpoint_ticks=130,protected_liquidity_id=None,endpoint_liquidity_id=pool.id)
    story=SimpleNamespace(destination_ticks=150,destination_ref_id='dest',details={
        'entry_weekly_relation':relation,'initial_weekly_relation':initial,
        'counterweekly_target_guard_required':initial=='COUNTER_WEEKLY','retracement':retracement})
    result=plan('BUY',100,T,'H1',(),(level,),(pool,),story,Instrument('X','1','1'),
                StrategyPolicy(risk_profile='fixed11',target_profile='entry_erl'),ranges=(active,))
    assert result.target_ticks==target and result.status==status
    if relation=='CONFLICTED':
        assert 'entry_weekly_context_conflicted' in result.details['unresolved_reasons']

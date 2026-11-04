"""Selecting nested entry confirmation must not silently change Bishop's bias rules."""
from dataclasses import replace
from datetime import timedelta
import pytest
from test_frozen_bias_reference import fixture,T
from bishop.v2.types import Clock,Event,StrategyPolicy
from bishop.v2.stories import _role,_StoryStructureView,find_stories


@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('indexed',[False,True])
def test_nested_uses_same_closed_role_change_as_bishop_without_an_invented_impulse_gate(side,indexed):
    reaction,origin,lower,structure,parents,*_=fixture(side)
    parent=parents['D'];level=parent.levels[0]
    level=replace(level,side='SELL' if side=='BUY' else 'BUY',kind='A' if side=='BUY' else 'V')
    at=T+timedelta(hours=20)
    change=Event(id='role_change',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='D',
                 clock=Clock(at,at,at),side=side,reference_id=level.id)
    parent=replace(parent,levels=(level,),events=(change,))
    view=_StoryStructureView(parent,(origin,)) if indexed else parent
    assert _role(level,view,origin.start,'nested_confirmation')==_role(level,view,origin.start,'bishop_confirmation')
    assert _role(level,view,origin.start,'nested_confirmation') is not None
    assert _role(level,view,origin.start,'core_course') is None
    assert _role(level,view,origin.start,'plug_and_play') is None
    results=[]
    for profile in ('bishop_confirmation','nested_confirmation'):
        result=find_stories({'D':(origin,),'H4':lower},{'D':parent,'H4':structure},
                            StrategyPolicy(source_profile=profile,origin_tfs=('D',),entry_tfs=('M30',)))
        assert len(result.stories)==1
        results.append([(s.side,s.origin_tf,s.confirmation_tf,s.confirmation_id,s.level_id,
                         s.details['frozen_external_reference_id'],s.available_at) for s in result.stories])
    assert results[0]==results[1]

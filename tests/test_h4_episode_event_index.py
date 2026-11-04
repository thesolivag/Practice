"""Indexed H4 episode checks preserve all original causal rejection reasons."""
from datetime import datetime,timedelta,timezone
import pytest
from bishop.v2.entries import (_EpisodeEventIndex,_reaction_episode_reason,
    _direct_episode_reason,_first_take_for_reaction)
from bishop.v2.types import Bar,Clock,Event,Level,Liquidity
T=datetime(2026,1,5,tzinfo=timezone.utc)
L=Level(id='level',instrument='X',tf='H4',kind='V',side='BUY',price_ticks=99,formed_at=T,available_at=T)
P=Event(id='parent',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(T,T,T),side='BUY',scope_id='scope')
POOL=Liquidity(id='pool',instrument='X',tf='H4',kind='LOW',price_ticks=98,formed_at=T,available_at=T)
def bar(h):return Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),100,105,95,101)
def event(ident,kind,hour,*,ref='level',scope=None,side='SELL',status='KNOWN'):
    at=T+timedelta(hours=hour)
    return Event(id=ident,kind=kind,instrument='X',tf='H4',clock=Clock(at,at,at),side=side,
                 reference_id=ref,scope_id=scope,evidence_status=status)
@pytest.mark.parametrize('extra',[
    (),
    (event('role','LEVEL_ROLE_CHANGE',2),),
    (event('same_clock','LEVEL_UNAVAILABLE',1),),
    (event('scope','RANGE_BROKEN',2,scope='scope',ref=None),),
    (event('fresh','BREAKOUT',2,scope='scope',ref=None,side='BUY'),),
    (event('unknown','BREAKOUT',2,scope='scope',ref=None,side='BUY',status='UNKNOWN'),),
    (event('future','LEVEL_ROLE_CHANGE',9),),
    # Original input order, not timestamp order, determines the first reason.
    (event('late','LEVEL_ROLE_CHANGE',3),event('early','LEVEL_UNAVAILABLE',2)),
])
def test_episode_index_and_cached_first_take_match_original_scan(extra):
    unrelated=(event('other','LEVEL_UNAVAILABLE',1,ref='other',scope='other'),)
    events=(*unrelated,*extra);index=_EpisodeEventIndex(events);rows=tuple(bar(h) for h in range(5));first=rows[0]
    for candidate in rows:
        reaction=(first,L,P,(POOL,))
        assert _reaction_episode_reason(reaction,candidate,index)==_reaction_episode_reason(reaction,candidate,events)
        assert _direct_episode_reason(P,candidate.available_at,index,L)==_direct_episode_reason(P,candidate.available_at,events,L)
        assert _direct_episode_reason(P,candidate.available_at,index)==_direct_episode_reason(P,candidate.available_at,events)
        raw=_first_take_for_reaction(POOL,candidate,rows,L,P,events)
        assert _first_take_for_reaction(POOL,candidate,rows,L,P,index,first_candidate=first)==raw

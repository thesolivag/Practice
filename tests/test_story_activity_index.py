from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from bishop.v2.entries import _StoryActivityIndex,_is_active


def test_activity_index_matches_full_scan_at_every_terminal_boundary():
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    kinds=('STORY_SUSPENDED','STORY_RETIRED','STORY_INVALIDATED','STORY_FLIPPED',
           'DESTINATION_REACHED','STORY_DESTINATION_REACHED','REACTION','STORY_CONFIRMED')
    events=[]
    for n,kind in enumerate(kinds):
        for indirect in (False,True):
            events.append(SimpleNamespace(kind=kind,available_at=start+timedelta(hours=n+2),
                reference_id='other' if indirect else str(n),
                details={'story_id':str(n)} if indirect else {}))
    # Unsorted input, duplicate terminal links and an earlier terminal boundary.
    events.append(SimpleNamespace(kind='STORY_RETIRED',available_at=start+timedelta(hours=1),
                                  reference_id='0',details={'story_id':'0'}))
    events=tuple(reversed(events));index=_StoryActivityIndex(events)
    for name in (*map(str,range(len(kinds))),'other','untouched'):
        story=SimpleNamespace(id=name)
        for minutes in range(0,601,15):
            at=start+timedelta(minutes=minutes)
            assert index.active(story,at)==_is_active(story,at,events)


def test_expired_warmup_stories_cannot_emit_in_the_scan_window():
    at=datetime(2026,1,1,tzinfo=timezone.utc)
    story=SimpleNamespace(id='old',available_at=at)
    event=SimpleNamespace(kind='STORY_INVALIDATED',available_at=at+timedelta(hours=2),
                          reference_id=story.id,details={})
    index=_StoryActivityIndex((event,))
    assert index.can_emit(story,None)
    assert index.can_emit(story,at+timedelta(hours=1))
    assert not index.can_emit(story,event.available_at)
    assert not index.can_emit(story,event.available_at+timedelta(hours=1))
    assert index.can_emit(SimpleNamespace(id='open',available_at=at),event.available_at)


def test_indexed_risk_objects_preserve_complete_entry_outputs(monkeypatch):
    import random
    from bishop.v2 import entries
    from bishop.v2.aggregation import aggregate
    from bishop.v2.structure import analyze
    from bishop.v2.stories import find_stories
    from bishop.v2.types import Bar,Instrument,StrategyPolicy
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    randomizer=random.Random(41);price=1000;bars=[]
    for i in range(72):
        close=price+randomizer.choice((-12,-8,-4,4,8,12))
        bars.append(Bar('X','H1',start+timedelta(hours=i),start+timedelta(hours=i+1),
                        price,max(price,close)+3,min(price,close)-3,close));price=close
    instrument=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    policy=StrategyPolicy(origin_tfs=('H4',),entry_tfs=('H1',),risk_profile='context_liquidity',
                          target_profile='fixed3r',source_profile='source_all')
    by_tf={tf:aggregate(bars,tf,instrument,bars[-1].end)['bars'] for tf in ('H1','H2','H4','D','W')}
    structures={tf:analyze(bs,policy) for tf,bs in by_tf.items()}
    stories=find_stories(by_tf,structures,policy)
    args=(by_tf,structures,stories,instrument,policy)
    kwargs=dict(story_events=stories.events,eligibility_start=start+timedelta(hours=48))
    optimized=entries.detect_setups(*args,**kwargs)
    assert optimized.setups
    monkeypatch.setattr(entries._RiskObjectIndex,'at',lambda self,*_: (self.levels,self.liquidity))
    monkeypatch.setattr(entries._StoryActivityIndex,'can_emit',lambda *args:True)
    assert entries.detect_setups(*args,**kwargs)==optimized

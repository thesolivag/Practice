"""Publication-index optimizations retain normal entry candidates and retirement evidence."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from types import SimpleNamespace
import random
import pytest
import bishop.v2.entries as entries
from bishop.v2.types import Bar

T=datetime(2026,1,5,tzinfo=timezone.utc)


class ReferenceEligibility:
    def __init__(self,rows):self.rows=tuple(rows)
    def for_story(self,reaction_after,parent_after):
        rows=tuple(r for r in self.rows if r[0].available_at>=reaction_after and r[2].available_at>=parent_after)
        return rows,tuple(r[0].end for r in rows)


def original_latest(rows,candle):
    visible=[r for r in rows if (r[0].id==candle.id or r[0].end<=candle.start)
             and r[0].available_at<=candle.available_at]
    return max(visible,key=lambda r:(r[0].end,r[0].available_at,r[1].id),default=None)


def test_compressed_parent_query_preserves_exact_latest_including_distinct_tied_bars():
    rng=random.Random(991);rows=[];bars=[]
    for hour in range(12):
        for variant in range(2):
            start=T+timedelta(hours=hour)
            bar=Bar('X','H1',start,start+timedelta(hours=1),100,105,95,100+variant,
                    available_at=start+timedelta(hours=1+(hour%3)))
            bars.append(bar)
            for level in ('a','b'):
                for parent in range(5):
                    rows.append((bar,SimpleNamespace(id=level),
                                 SimpleNamespace(id=f'p{parent}',available_at=T+timedelta(hours=parent)),('pool',)))
    rng.shuffle(rows);rows.sort(key=lambda r:(r[0].end,r[0].available_at,r[1].id))
    index=entries._ReactionEligibilityIndex(rows);reference=ReferenceEligibility(rows)
    for born in (0,8,2,15,5):
        for parent_after in (0,4,1,7):
            args=(T+timedelta(hours=born),T+timedelta(hours=parent_after))
            selected,ends=index.for_story(*args);full,_=reference.for_story(*args)
            for candle in bars:
                assert entries._latest_reaction(selected,ends,candle)==original_latest(full,candle)
                # A next candle sees a just-closed reaction; same-clock but
                # different bars cannot substitute in the containing candle.
                next_bar=replace(candle,start=candle.end,end=candle.end+timedelta(hours=1),
                                 available_at=candle.available_at+timedelta(hours=1))
                assert entries._latest_reaction(selected,ends,next_bar)==original_latest(full,next_bar)


def test_first_parent_priority_is_original_input_order_not_newest_parent_receipt():
    bar=Bar('X','H1',T,T+timedelta(hours=1),100,105,95,101)
    level=SimpleNamespace(id='level')
    rows=tuple((bar,level,SimpleNamespace(id=ident,available_at=T+timedelta(minutes=minutes)),('pool',))
               for ident,minutes in (('first',10),('newest',50),('middle',30)))
    index=entries._ReactionEligibilityIndex(rows)
    for minutes,expected in ((0,'first'),(20,'newest'),(40,'newest'),(60,None)):
        selected,_=index.for_story(T,T+timedelta(minutes=minutes))
        assert (selected[0][2].id if selected else None)==expected


def test_queries_do_not_rescan_thousands_of_parent_publication_properties():
    class Published:
        reads=0
        def __init__(self,clock):self.clock=clock
        @property
        def available_at(self):
            type(self).reads+=1
            return self.clock
    bar=Bar('X','H1',T,T+timedelta(hours=1),100,105,95,101)
    rows=tuple((bar,SimpleNamespace(id='level'),Published(T+timedelta(minutes=i%60)),('pool',)) for i in range(6000))
    index=entries._ReactionEligibilityIndex(rows)
    assert Published.reads==len(rows)
    for minutes in range(200):index.for_story(T,T+timedelta(minutes=minutes))
    assert Published.reads==len(rows)


def test_story_start_bisect_is_logarithmic_and_receipt_discontinuity_keeps_full_scan():
    class Publications:
        reads=0
        def __len__(self):return 100000
        def __getitem__(self,i):
            self.reads+=1
            return T+timedelta(minutes=i)
    times=Publications()
    assert entries._story_bar_start(times,T+timedelta(minutes=50321),True)==50321
    assert times.reads<=18
    before=times.reads
    assert entries._story_bar_start(times,T+timedelta(minutes=50321),False)==0
    assert times.reads==before


@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('replacement',['sibling','same_scope'])
@pytest.mark.parametrize('delayed',[False,True])
def test_complete_normal_entry_results_equal_full_history_reference(monkeypatch,side,replacement,delayed):
    from test_h4_confirmation_parent_review import test_confirmation_preserves_declared_h4_parent_only_while_episode_valid
    detect=entries.detect_setups
    def compared(*args,**kwargs):
        frames,structures,stories,instrument,policy=args
        # Force a real non-monotone historical receipt case without changing
        # the current setup's candles; this must retain the original full scan.
        if delayed:
            hourly=frames['H1']
            frames={**frames,'H1':(replace(hourly[0],available_at=hourly[-1].end+timedelta(hours=1)),*hourly[1:])}
        # Both loops must retain original neighboring candle indexes when
        # earlier publications are skipped for a later-born story.
        stories=tuple(SimpleNamespace(**{**vars(s),'available_at':T+timedelta(hours=2)}) for s in stories)
        args=(frames,structures,stories,instrument,policy)
        actual=detect(*args,**kwargs)
        with monkeypatch.context() as plain:
            plain.setattr(entries,'_ReactionEligibilityIndex',ReferenceEligibility)
            plain.setattr(entries,'_story_bar_start',lambda *a:0)
            expected=detect(*args,**kwargs)
        assert actual==expected
        return actual
    monkeypatch.setattr(entries,'detect_setups',compared)
    test_confirmation_preserves_declared_h4_parent_only_while_episode_valid(monkeypatch,'H1',60,side,replacement)

"""The hot nested witness query must preserve first-tie and receipt-clock semantics."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import random
from bishop.v2.entries import _NestedWitnessIndex
from test_entry_runtime_indexes import ReferenceWitnesses

T=datetime(2026,1,5,tzinfo=timezone.utc)


def row(ident,reaction,parent):
    return (SimpleNamespace(id=ident,available_at=T+timedelta(hours=reaction)),
            'level',SimpleNamespace(available_at=T+timedelta(hours=parent)),('pool',))


def test_parent_threshold_does_not_reorder_equal_reaction_clocks():
    rows=(row('first_original',10,3),row('later_original',10,8),row('older_reaction',9,12))
    index=_NestedWitnessIndex(rows)
    assert index.query(T,T)[0].id=='first_original'
    assert index.query(T,T+timedelta(hours=4))[0].id=='later_original'
    assert index.query(T,T+timedelta(hours=9))[0].id=='older_reaction'
    assert index.query(T+timedelta(hours=10),T+timedelta(hours=9)) is None
    assert index.query(T,T+timedelta(hours=13)) is None


def test_query_equals_full_filter_max_with_ties_delays_rewinds_and_empty_population():
    rng=random.Random(1429)
    rows=[row(str(i),rng.randrange(35),rng.randrange(35)) for i in range(450)]
    rng.shuffle(rows)
    for population in ((),tuple(rows)):
        actual=_NestedWitnessIndex(population);reference=ReferenceWitnesses(population)
        for reaction in (35,0,30,8,24,2,19):
            for parent in (0,35,20,8,1,31,15):
                args=(T+timedelta(hours=reaction),T+timedelta(hours=parent))
                assert actual.query(*args)==reference.query(*args)


def test_repeated_queries_never_rescan_candidate_properties():
    class Published:
        reads=0
        def __init__(self,clock):self.clock=clock
        @property
        def available_at(self):
            type(self).reads+=1
            return self.clock
    rows=tuple((Published(T+timedelta(minutes=i%140)),None,
                Published(T+timedelta(minutes=i%230)),('pool',)) for i in range(6000))
    index=_NestedWitnessIndex(rows)
    assert Published.reads==2*len(rows)
    for i in range(200):
        index.query(T+timedelta(minutes=i),T+timedelta(minutes=230-i))
    # Query does only a binary threshold lookup and one precomputed-clock test.
    assert Published.reads==2*len(rows)

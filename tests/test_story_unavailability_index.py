"""Indexed gap diagnostics retain publication ordering and original cause."""
from datetime import datetime,timedelta,timezone
from bishop.v2.types import Bar,Clock,Event,Level,StrategyPolicy
from bishop.v2.structure import StructureResult
from bishop.v2.stories import _reaction_candidates
T=datetime(2026,1,5,tzinfo=timezone.utc)
L=Level(id='level',instrument='X',tf='D',kind='V',side='BUY',price_ticks=100,formed_at=T,available_at=T)
B=Bar('X','D',T+timedelta(days=1),T+timedelta(days=2),100,105,95,102)
P=StrategyPolicy(origin_tfs=('D',),source_profile='bishop_confirmation')
def event(ident,days,reason):
    at=T+timedelta(days=days)
    return Event(id=ident,kind='LEVEL_UNAVAILABLE',instrument='X',tf='D',clock=Clock(at,at,at),reference_id=L.id,details={'reason':reason})
def inspect(events):
    return _reaction_candidates({'D':(B,)},{'D':StructureResult((),(L,),(),events,())},P)
def test_future_unavailability_does_not_erase_known_reaction():
    baseline=inspect(())
    assert baseline[0] and inspect((event('future',3,'DATA_GAP'),))==baseline

def test_diagnostic_preserves_earliest_cause_with_unsorted_tied_receipts(monkeypatch):
    a=event('a',0,'DATA_GAP');z=event('z',0,'OTHER');later=event('later',1,'OTHER')
    reactions,support=inspect((later,z,a))
    assert not reactions
    row=next(x for x in support if x.get('level_id')==L.id)
    assert row['unavailability_event_id']=='a' and row['reason']=='level_unavailable_after_data_gap'
    assert inspect((a,z,later,event('future',3,'OTHER')))==(reactions,support)
    import bishop.v2.stories as stories
    monkeypatch.setattr(stories,'_indexed_structures',lambda structures,bars_by_tf=None:structures)
    assert inspect((later,z,a))==(reactions,support)

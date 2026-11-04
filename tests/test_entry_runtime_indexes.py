"""Performance indexes preserve complete candidate populations and publication order."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from types import SimpleNamespace
import random
import pytest
from bishop.v2.types import Bar,Liquidity
import bishop.v2.entries as entries

T=datetime(2026,1,5,tzinfo=timezone.utc)


class ReferencePools:
    def __init__(self,pools):self.pools=pools
    def select(self,tf,side,at,after,segment_start,*,parent_id=None):
        return tuple(p for p in self.pools if p.tf==tf and p.formed_at>=segment_start
            and p.available_at>=segment_start and p.available_at<=at and p.formed_at>=after
            and (p.form not in ('BAR','PRIOR_PERIOD','SESSION') or p.details.get('role')=='IRL')
            and p.kind==('LOW' if side=='BUY' else 'HIGH')
            and (parent_id is None or parent_id in (p.details.get('parent_break_id'),p.details.get('breakout_id'))))


class ReferenceWitnesses:
    def __init__(self,rows):self.rows=tuple(rows)
    def query(self,reaction_after,parent_after):
        return max((row for row in self.rows if row[0].available_at>=reaction_after
                    and row[2].available_at>=parent_after),
                   key=lambda row:row[0].available_at,default=None)


class ReferencePairs:
    def __init__(self,frames):self.frames=frames
    def standing_after(self,side,segment,at):
        return tuple((a,b) for a,b in zip(self.frames.get('H1',()),self.frames.get('H1',())[1:])
            if a.start>=at and a.segment_id==b.segment_id==segment and
            ((b.low_ticks<a.low_ticks and b.high_ticks<a.high_ticks and b.close_ticks>a.low_ticks) if side=='BUY'
             else (b.high_ticks>a.high_ticks and b.low_ticks>a.low_ticks and b.close_ticks<a.high_ticks)))
    def engulf_after(self,tf,side,segment,at):
        return tuple((a,b) for a,b in zip(self.frames.get(tf,()),self.frames.get(tf,())[1:])
            if b.end>=at and a.end==b.start and a.segment_id==b.segment_id==segment and entries._engulfs(a,b,side))


def test_pool_index_preserves_shuffled_input_and_tied_formation_with_delayed_publication():
    pools=[]
    for i in range(80):
        formed=T+timedelta(hours=i//3)
        pools.append(Liquidity(id=f'p{i}',instrument='X',tf='H4' if i%3 else 'H1',
            kind='LOW' if i%2 else 'HIGH',price_ticks=100+i,formed_at=formed,
            available_at=formed+timedelta(hours=i%5),form=('BAR','SERIES','TURN_LEG','SESSION')[i%4],
            details={'role':'IRL' if i%3 else 'ERL','parent_break_id':f'parent{i%4}'}))
    random.Random(231).shuffle(pools)
    actual=entries._PoolSelectionIndex(pools);reference=ReferencePools(pools)
    # Include rewinds, exact-clock boundaries, parent subsets and absence.
    for hour in (30,4,16,0,27,8):
        for tf in ('H4','H1','D'):
            for side in ('BUY','SELL'):
                for parent in (None,'parent1','missing'):
                    args=(tf,side,T+timedelta(hours=hour),T+timedelta(hours=3),T+timedelta(hours=2))
                    assert actual.select(*args,parent_id=parent)==reference.select(*args,parent_id=parent)


def test_nested_pair_index_matches_unindexed_adjacent_scans_across_gaps_and_receipt_delays():
    rng=random.Random(445);frames={}
    for tf,minutes in (('H1',60),('M30',30)):
        bars=[]
        for i in range(90):
            start=T+timedelta(minutes=minutes*(i+(i>=30)))
            o=rng.randrange(95,106);c=rng.randrange(95,106)
            bars.append(Bar('X',tf,start,start+timedelta(minutes=minutes),o,max(o,c)+rng.randrange(1,5),
                            min(o,c)-rng.randrange(1,5),c,segment_id=f'segment{i//20}',
                            available_at=start+timedelta(minutes=minutes,hours=i%7)))
        frames[tf]=tuple(bars)
    actual=entries._NestedPairIndex(frames);reference=ReferencePairs(frames)
    for side in ('BUY','SELL'):
        for segment in ('segment0','segment1','segment2','segment3','segment4','unknown'):
            for hour in (0,2,14,40,99):
                at=T+timedelta(hours=hour)
                assert actual.standing_after(side,segment,at)==reference.standing_after(side,segment,at)
                assert actual.engulf_after('M30',side,segment,at)==reference.engulf_after('M30',side,segment,at)


@pytest.mark.parametrize('same_close',[False,True])
def test_complete_nested_results_equal_reference_scans_with_parent_role_loss_and_delayed_receipts(monkeypatch,same_close):
    from test_nested_parent_episode_review import test_parent_role_loss_after_h1_standing_blocks_later_lower_engulf
    detect=entries.detect_setups
    def compared(*args,**kwargs):
        frames,structures,stories,instrument,policy=args
        mirrored={tf:tuple(replace(b,open_ticks=200-b.open_ticks,high_ticks=200-b.low_ticks,
                         low_ticks=200-b.high_ticks,close_ticks=200-b.close_ticks) for b in bars)
                  for tf,bars in frames.items()}
        ids={a.id:b.id for tf in frames for a,b in zip(frames[tf],mirrored[tf])}
        flip=lambda side: 'BUY' if side=='SELL' else 'SELL' if side=='BUY' else None
        structures_buy={tf:replace(r,
            levels=tuple(replace(l,price_ticks=200-l.price_ticks,side=flip(l.side),kind='V' if l.kind=='A' else 'A' if l.kind=='V' else l.kind,
                                 bar_ids=tuple(ids.get(i,i) for i in l.bar_ids)) for l in r.levels),
            liquidity=tuple(replace(p,price_ticks=200-p.price_ticks,kind='LOW' if p.kind=='HIGH' else 'HIGH',
                                    bar_ids=tuple(ids.get(i,i) for i in p.bar_ids)) for p in r.liquidity),
            events=tuple(replace(e,side=flip(e.side),price_ticks=200-e.price_ticks if e.price_ticks is not None else None,
                                 bar_ids=tuple(ids.get(i,i) for i in e.bar_ids)) for e in r.events))
            for tf,r in structures.items()}
        stories_buy=tuple(SimpleNamespace(**{**vars(s),'side':flip(s.side)}) for s in stories)
        with monkeypatch.context() as buy:
            buy.setattr(entries,'plan',lambda *a,**k:SimpleNamespace(stop_ticks=90,target_ticks=110,status='ELIGIBLE',details={'unresolved_reasons':[]}))
            actual_buy=detect(mirrored,structures_buy,stories_buy,instrument,policy,**kwargs)
            buy.setattr(entries,'_PoolSelectionIndex',ReferencePools)
            buy.setattr(entries,'_NestedPairIndex',ReferencePairs)
            buy.setattr(entries,'_NestedWitnessIndex',ReferenceWitnesses)
            assert actual_buy==detect(mirrored,structures_buy,stories_buy,instrument,policy,**kwargs)
        actual=detect(*args,**kwargs)
        if actual.setups:assert actual_buy.setups

        with monkeypatch.context() as plain:
            plain.setattr(entries,'_PoolSelectionIndex',ReferencePools)
            plain.setattr(entries,'_NestedPairIndex',ReferencePairs)
            plain.setattr(entries,'_NestedWitnessIndex',ReferenceWitnesses)
            expected=detect(*args,**kwargs)
        assert actual==expected
        return actual
    monkeypatch.setattr(entries,'detect_setups',compared)
    test_parent_role_loss_after_h1_standing_blocks_later_lower_engulf(monkeypatch,same_close)

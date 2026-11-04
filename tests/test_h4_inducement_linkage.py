"""Declared inducement belongs to its breakout and KL, before any outcome."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import bishop.v2.entries as entries
from bishop.v2.structure import StructureResult
from bishop.v2.types import Bar, Clock, Event, Instrument, Level, Liquidity, StrategyPolicy

T = datetime(2026, 1, 5, tzinfo=timezone.utc)


@pytest.mark.parametrize('lineage', [
    {'breakout_id': 'second'},
    {'parent_break_id': 'second'},
    {'breakout_id': 'second', 'parent_break_id': 'second'},
])
def test_direct_h4_keeps_declared_parent_and_farther_kl(monkeypatch, lineage):
    bars = tuple(Bar('X', 'H4', T + timedelta(hours=h), T + timedelta(hours=h+4),
                     100, 110+h, 90-h, 105) for h in (0, 4, 8))
    levels = tuple(Level(id=ident, instrument='X', tf='H4', kind='V', price_ticks=price,
                         side='BUY', formed_at=T, available_at=T)
                   for ident, price in (('near', 100), ('declared', 95)))
    breaks = tuple(Event(id=ident, kind='BREAKOUT', instrument='X', tf='H4',
                         clock=Clock(bar.start, bar.end, bar.available_at), side='BUY',
                         reference_id='near', bar_ids=(bar.id,))
                   for ident, bar in zip(('first', 'second'), bars))
    pool = Liquidity(id='declared_pool', instrument='X', tf='H4', kind='LOW',
                     price_ticks=98, formed_at=bars[-1].end, available_at=bars[-1].end,
                     form='BAR', bar_ids=(bars[-1].id,),
                     details={'role': 'IRL', 'reaction_level_id': 'declared', **lineage})
    structure = StructureResult((), levels, (pool,), breaks, ())
    story = SimpleNamespace(id='story', side='BUY', available_at=T, clock=Clock(T,T,T),
                            details={}, destination_ticks=None, destination_ref_id=None)
    monkeypatch.setattr(entries, 'plan', lambda *args, **kwargs:
                        SimpleNamespace(stop_ticks=80, target_ticks=130, status='ELIGIBLE',
                                        details={'unresolved_reasons': []}))
    result = entries.detect_setups({'H4': bars}, {'H4': structure}, (story,),
                                  Instrument('X', '1', '1', calendar_id='24x7_utc_v1'),
                                  StrategyPolicy(source_profile='owner_aggressive', entry_tfs=('H4',)))
    selected = [s for s in result.setups if pool.id in s.liquidity_ids]
    assert len(selected) == 1
    assert selected[0].level_id == 'declared'
    assert 'second' in selected[0].evidence_ids
    assert 'first' not in selected[0].evidence_ids
    # A future feed gap cannot erase an already available direct setup.
    future = Bar('X', 'H4', T+timedelta(hours=20), T+timedelta(hours=24),
                 105, 115, 100, 110, segment_id='after_gap')
    extended = entries.detect_setups({'H4': (*bars, future)}, {'H4': structure}, (story,),
                                    Instrument('X', '1', '1', calendar_id='24x7_utc_v1'),
                                    StrategyPolicy(source_profile='owner_aggressive', entry_tfs=('H4',)))
    assert tuple(s for s in extended.setups if s.available_at <= bars[-1].available_at) == result.setups


def test_contradictory_parent_tags_fail_closed():
    pool = SimpleNamespace(details={'breakout_id': 'first', 'parent_break_id': 'second'})
    assert not entries._pool_parent_matches(pool, SimpleNamespace(id='first'))
    assert not entries._pool_parent_matches(pool, SimpleNamespace(id='second'))


def _episode_event(ident, kind, hour, side='BUY', scope='root', reference='declared'):
    at = T + timedelta(hours=hour)
    return Event(id=ident, kind=kind, instrument='X', tf='H4', clock=Clock(at, at, at),
                 side=side, scope_id=scope, reference_id=reference)


def _episode_replay(monkeypatch, extra_events=(), child=False, story_hour=0, extra_bars=()):
    tf = 'H2' if child else 'H4'
    step = 2 if child else 4
    bars = tuple(Bar('X', tf, T+timedelta(hours=h), T+timedelta(hours=h+step),
                     100, 110+h, 90-h, 105) for h in range(0, 12, step))
    level = Level(id='declared', instrument='X', tf=tf, kind='V', price_ticks=95,
                  side='BUY', formed_at=T, available_at=T)
    origin = bars[1] if child else bars[0]
    parent = Event(id='parent', kind='BREAKOUT', instrument='X', tf=tf,
                   clock=Clock(origin.start, origin.end, origin.available_at),
                   side='BUY', scope_id='child' if child else 'root',
                   reference_id=level.id, bar_ids=(origin.id,))
    pool = Liquidity(id='episode_pool', instrument='X', tf=tf, kind='LOW',
                     price_ticks=98, formed_at=bars[-1].end, available_at=bars[-1].end,
                     form='BAR', details={'role':'IRL', 'breakout_id':parent.id,
                                          'reaction_level_id':level.id})
    structures = {tf: StructureResult((), (level,), (pool,), (parent, *extra_events) if not child else (parent,), ())}
    frames = {tf: (*bars, *extra_bars)}
    if child:
        h4bar = Bar('X', 'H4', T, T+timedelta(hours=4), 100, 110, 90, 105)
        h4parent = Event(id='h4parent', kind='BREAKOUT', instrument='X', tf='H4',
                         clock=Clock(h4bar.start, h4bar.end, h4bar.available_at),
                         side='BUY', scope_id='root', bar_ids=(h4bar.id,))
        structures['H4'] = StructureResult((), (), (), (h4parent, *extra_events), ())
        frames['H4'] = (h4bar,)
    story = SimpleNamespace(id='story', side='BUY', available_at=T+timedelta(hours=story_hour), clock=Clock(T,T,T),
                            details={}, destination_ticks=None, destination_ref_id=None)
    monkeypatch.setattr(entries, 'plan', lambda *args, **kwargs:
                        SimpleNamespace(stop_ticks=80, target_ticks=130, status='ELIGIBLE',
                                        details={'unresolved_reasons': []}))
    result = entries.detect_setups(frames, structures, (story,),
                                  Instrument('X','1','1',calendar_id='24x7_utc_v1'),
                                  StrategyPolicy(source_profile='owner_aggressive',entry_tfs=(tf,)))
    return result, tuple(s for s in result.setups if pool.id in s.liquidity_ids)


@pytest.mark.parametrize('events,reason', [
    ((_episode_event('lost','LEVEL_ROLE_CHANGE',6,'SELL'),
      _episode_event('restored','LEVEL_ROLE_CHANGE',8)), 'direct_level_role_lost'),
    ((_episode_event('broken','RANGE_BROKEN',8,'SELL'),), 'direct_scope_broken'),
    ((_episode_event('new','BREAKOUT',8),), 'direct_replaced_by_fresh_break'),
])
def test_delayed_direct_h4_cannot_revive_retired_episode(monkeypatch, events, reason):
    assert len(_episode_replay(monkeypatch)[1]) == 1
    result, selected = _episode_replay(monkeypatch, events)
    assert not selected
    assert any(row.get('pool_id') == 'episode_pool' and row.get('reason') == reason
               for row in result.support)


def test_future_or_other_scope_change_does_not_erase_direct_placement(monkeypatch):
    baseline = _episode_replay(monkeypatch)[1]
    future = (_episode_event('later','RANGE_BROKEN',16,'SELL'),
              _episode_event('later_role','LEVEL_ROLE_CHANGE',16,'SELL'))
    assert _episode_replay(monkeypatch, future)[1] == baseline
    unrelated = (_episode_event('other','RANGE_BROKEN',8,'SELL',scope='other'),)
    assert _episode_replay(monkeypatch, unrelated)[1] == baseline


def test_h2_direct_cannot_borrow_retired_h4_parent(monkeypatch):
    baseline = _episode_replay(monkeypatch, child=True)[1]
    assert len(baseline) == 1
    assert baseline[0].available_at >= T+timedelta(hours=4)
    assert baseline[0].details['h4_breakout_closed_at'] == (T+timedelta(hours=4)).isoformat()
    result, selected = _episode_replay(monkeypatch,
                                     (_episode_event('h4_new','BREAKOUT',8),), child=True)
    assert not selected
    assert any(row.get('reason') == 'direct_replaced_by_fresh_break'
               for row in result.support)


def test_consumed_liquidity_blocks_delayed_submission_but_preserves_prior_order(monkeypatch):
    sweep = Bar('X','H4',T+timedelta(hours=12),T+timedelta(hours=16),100,110,85,105)
    baseline = _episode_replay(monkeypatch)[1]
    assert len(baseline) == 1
    assert _episode_replay(monkeypatch, extra_bars=(sweep,))[1] == baseline
    result, selected = _episode_replay(monkeypatch, story_hour=16, extra_bars=(sweep,))
    assert not selected
    assert any(row.get('reason') == 'direct_liquidity_already_taken'
               for row in result.support)

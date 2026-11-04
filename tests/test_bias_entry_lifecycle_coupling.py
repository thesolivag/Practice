"""The displayed bias and entry contexts share causal retirement boundaries."""
from datetime import datetime, timedelta, timezone
import random
import pytest
from bishop.bias_snapshot import snapshot
from bishop.v2.aggregation import aggregate
from bishop.v2.entries import _StoryActivityIndex, detect_setups
from bishop.v2.stories import find_stories
from bishop.v2.structure import analyze
from bishop.v2.types import Bar, Clock, Event, Instrument, StrategyPolicy, jsonable

T = datetime(2026, 1, 5, tzinfo=timezone.utc)


def fixture():
    rng = random.Random(0)
    price = 1000
    bars = []
    for hour in range(192):
        close = price + rng.choice((-12, -8, -4, 4, 8, 12))
        bars.append(Bar('X', 'H1', T + timedelta(hours=hour), T + timedelta(hours=hour+1),
                        price, max(price, close)+3, min(price, close)-3, close))
        price = close
    instrument = Instrument('X', '1', '1', calendar_id='24x7_utc_v1', anchor_id='utc_epoch_v1')
    # Fixed risk/target isolate lifecycle coupling from target qualification;
    # no source outcome, fitted tolerance or execution assumption is involved.
    policy = StrategyPolicy(origin_tfs=('H4',), entry_tfs=('H1',),
                            source_profile='bishop_confirmation',
                            risk_profile='fixed11', target_profile='fixed3r')
    def replay(count):
        observed = bars[:count]
        frames = {tf: aggregate(observed, tf, instrument, observed[-1].end)['bars']
                  for tf in ('H1', 'H2', 'H4', 'D', 'W')}
        structures = {tf: analyze(rows, policy) for tf, rows in frames.items()}
        stories = find_stories(frames, structures, policy)
        return observed[-1].end, frames, structures, stories
    return instrument, policy, replay


def view(instrument, policy, stories, at, extra=()):
    return snapshot(jsonable(dict(as_of=at, instrument=instrument, policy=policy,
        status='COMPUTED_UNVALIDATED', story_context_evaluated=True,
        stories=stories.stories, story_events=(*stories.events, *extra), coverage={})))


def test_cross_scope_reassessment_keeps_the_same_contexts_in_bias_and_entries_without_hindsight():
    instrument, policy, replay = fixture()
    at, _, _, prefix = replay(47)
    _, frames, structures, full = replay(192)
    event = next(e for e in prefix.events if e.kind == 'OPPOSITE_STORY_CONFIRMED'
                 and e.available_at == at)
    # The observation is already known in the prefix, with exactly the same
    # identity as the later report; future candles did not create this fact.
    assert event in full.events
    stories = {s.id: s for s in prefix.stories}
    old = stories[event.reference_id]
    successor = stories[event.details['successor_story_id']]
    assert old.origin_tf == successor.origin_tf == 'H4'
    assert old.details['scope_type'] == successor.details['scope_type'] == 'ROOT'
    assert old.scope_id != successor.scope_id and old.side != successor.side
    assert _StoryActivityIndex(prefix.events).active(old, at)
    row = next(r for r in view(instrument, policy, prefix, at)['rows'] if r['tf'] == 'H4')
    assert row['state'] == 'CONFLICT' and row['side'] is None
    assert {old.id, successor.id} <= set(row['story_ids'])
    entries = detect_setups(frames, structures, full, instrument, policy, story_events=full.events)
    assert any(s.story_id == old.id and s.available_at >= at and s.status == 'ELIGIBLE'
               for s in entries.setups)


@pytest.mark.parametrize('kind', ['STORY_FLIPPED', 'STORY_INVALIDATED', 'STORY_DESTINATION_REACHED'])
def test_explicit_retirement_boundaries_apply_to_bias_and_entry_activity_together(kind):
    instrument, policy, replay = fixture()
    at, _, _, prefix = replay(47)
    opposite = next(e for e in prefix.events if e.kind == 'OPPOSITE_STORY_CONFIRMED'
                    and e.available_at == at)
    old = next(s for s in prefix.stories if s.id == opposite.reference_id)
    later = at + timedelta(minutes=1)
    event = Event(id='explicit_retirement', kind=kind, instrument='X', tf='H4',
                  side=old.side, reference_id=old.id, clock=Clock(later, later, later))
    activity = _StoryActivityIndex((*prefix.events, event))
    assert activity.active(old, at) and not activity.active(old, later)
    assert old.id not in {s['story_id'] for s in view(instrument, policy, prefix, at)['excluded']}
    excluded = {s['story_id']: s['reasons'] for s in view(instrument, policy, prefix, later, (event,))['excluded']}
    assert excluded[old.id] == [kind]

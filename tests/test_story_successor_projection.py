"""Compact research projection preserves every decision-driving lifecycle fact."""
import random
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import pytest
from bishop.v2.aggregation import aggregate
from bishop.v2.structure import analyze
from bishop.v2.types import Bar, Instrument, StrategyPolicy
from bishop.v2.entries import detect_setups
from bishop.v2 import stories as module

T = datetime(2026, 1, 5, tzinfo=timezone.utc)
DIAGNOSTICS = {'OPPOSITE_STORY_CONFIRMED', 'STORY_RETRACEMENT_EVIDENCE'}


class NaiveTemporalIndex:
    """Reference implementation of the former chronological scans."""
    def __init__(self, stories, reactions):
        self.stories = stories
        self.reactions = reactions

    def weekly_before(self, story):
        rows = [s for s in self.stories if s.instrument == story.instrument
                and s.origin_tf == 'W' and s.available_at < story.available_at]
        return rows[-1] if rows else None

    def opposite_after(self, story):
        return (s for s in self.stories if s.instrument == story.instrument
                and s.side != story.side and s.available_at > story.available_at)

    def first_flip(self, story):
        for successor in self.opposite_after(story):
            reaction = self.reactions[successor.origin_id]
            if (successor.origin_tf == story.origin_tf
                    and successor.details.get('scope_type') == story.details.get('scope_type')
                    and story.details.get('scope_type') in ('ROOT', 'CHILD')
                    and reaction.kind == 'KL_REJECTION'
                    and reaction.reference_id == story.destination_ref_id):
                return successor
        return None


def test_temporal_index_preserves_clock_ties_instruments_scopes_and_first_flip():
    rows = []
    reactions = {}
    for i, (hour, side, tf, scope, reference, instrument) in enumerate((
            (0, 'BUY', 'W', 'ROOT', 'kl0', 'X'),
            (0, 'SELL', 'W', 'ROOT', 'kl1', 'X'),
            (1, 'BUY', 'D', 'ROOT', 'kl2', 'X'),
            (2, 'SELL', 'D', 'LOCAL', 'destination', 'X'),
            (2, 'SELL', 'D', 'ROOT', 'destination', 'Y'),
            (3, 'SELL', 'D', 'ROOT', 'other', 'X'),
            (4, 'SELL', 'D', 'ROOT', 'destination', 'X'),
            (4, 'SELL', 'D', 'ROOT', 'destination', 'X'))):
        ident = str(i)
        rows.append(SimpleNamespace(id=ident, origin_id=ident, instrument=instrument,
                    side=side, origin_tf=tf, details={'scope_type':scope},
                    destination_ref_id='destination', available_at=T+timedelta(hours=hour)))
        reactions[ident] = SimpleNamespace(kind='KL_REJECTION', reference_id=reference)
    indexed = module._StoryTemporalIndex(rows, reactions)
    naive = NaiveTemporalIndex(rows, reactions)
    for story in rows:
        assert indexed.weekly_before(story) == naive.weekly_before(story)
        assert tuple(indexed.opposite_after(story)) == tuple(naive.opposite_after(story))
        assert indexed.first_flip(story) == naive.first_flip(story)
    assert indexed.weekly_before(rows[2]).id == '1'
    assert indexed.first_flip(rows[2]).id == '6'


def fixture():
    randomizer = random.Random(41)
    price = 1000
    bars = []
    for i in range(192):
        close = price + randomizer.choice((-12, -8, -4, 4, 8, 12))
        bars.append(Bar('X', 'H1', T+timedelta(hours=i), T+timedelta(hours=i+1),
                        price, max(price, close)+3, min(price, close)-3, close))
        price = close
    instrument = Instrument('X', '1', '1', calendar_id='24x7_utc_v1', anchor_id='utc_epoch_v1')
    policy = StrategyPolicy(origin_tfs=('H4',), entry_tfs=('H1',), source_profile='source_all',
                            risk_profile='fixed11', target_profile='fixed3r')
    frames = {tf: aggregate(bars, tf, instrument, bars[-1].end)['bars']
              for tf in ('H1', 'H2', 'H4', 'D', 'W')}
    structures = {tf: analyze(rows, policy) for tf, rows in frames.items()}
    return instrument, policy, frames, structures


@pytest.mark.parametrize('compact', [False, True])
def test_indexed_lifecycle_matches_former_scans_without_changing_ids(monkeypatch, compact):
    instrument, policy, frames, structures = fixture()
    actual = module.find_stories(frames, structures, policy, include_successor_diagnostics=not compact)
    monkeypatch.setattr(module, '_StoryTemporalIndex', NaiveTemporalIndex)
    expected = module.find_stories(frames, structures, policy, include_successor_diagnostics=not compact)
    assert actual.stories and len({s.side for s in actual.stories}) == 2
    assert actual == expected


def test_projection_preserves_complete_setups_stops_targets_and_terminal_events():
    instrument, policy, frames, structures = fixture()
    full = module.find_stories(frames, structures, policy)
    compact = module.find_stories(frames, structures, policy, include_successor_diagnostics=False)
    assert any(e.kind in DIAGNOSTICS for e in full.events)
    assert compact.stories == full.stories
    assert compact.reactions == full.reactions
    assert compact.support == full.support
    assert compact.events == tuple(e for e in full.events if e.kind not in DIAGNOSTICS)
    full_entries = detect_setups(frames, structures, full, instrument, policy, story_events=full.events)
    compact_entries = detect_setups(frames, structures, compact, instrument, policy, story_events=compact.events)
    assert full_entries.setups
    assert compact_entries == full_entries


def test_projection_flag_cannot_silently_accept_truthy_strings():
    with pytest.raises(ValueError, match='must be boolean'):
        module.find_stories({}, {}, include_successor_diagnostics='false')

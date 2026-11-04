"""Explicit mixed H1-context / real M1-derived child detection.

No minute is synthesized. Complete child candles only; partial M1 coverage
remains reported. Episode segment labels use actual missing-observation
intervals shared by H1 and M30, never coincident numeric segment counters.
"""
from bisect import bisect_right
from dataclasses import replace
from datetime import timedelta

from .aggregation import aggregate
from .execution_feed import prepare_execution_feed
from .types import stable_id, utc


def _intervals(coarse, fine):
    rows = [(utc(t), utc(t)+timedelta(hours=1)) for t in coarse.get('missing', ())]
    rows += [(utc(t), utc(t)+timedelta(minutes=1)) for t in fine.get('missing', ())]
    merged = []
    for lo, hi in sorted(rows):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return tuple(merged)


def shared_segments(bars, intervals, baseline):
    """A candle spanning a known fine gap cannot share a child episode ID."""
    ends = [hi for _, hi in intervals]
    output = []
    crossing = []
    for bar in bars:
        position = bisect_right(ends, bar.start)
        overlaps = position < len(intervals) and intervals[position][0] < bar.end
        if overlaps:
            segment = stable_id('mixed_gap_crossing', bar.id)
            crossing.append(bar.id)
        else:
            anchor = ends[position-1] if position else baseline
            segment = stable_id('mixed_observed_epoch', anchor)
        # Segment is provenance, not OHLC or economic identity; Bar.id is unchanged.
        revised = replace(bar, segment_id=segment)
        assert revised.id == bar.id
        output.append(revised)
    return tuple(output), crossing


def prepare_detection_frames(spec, detection, base, bars_by_tf, scan_start, as_of):
    if not base or base[0].tf != 'H1':
        raise ValueError('Mixed detection currently requires declared H1 context')
    fine, validation = prepare_execution_feed(spec, detection, base, scan_start, as_of)
    if fine['manifest']['base_tf'] != 'M1':
        raise ValueError('Mixed child detection requires real M1 input')
    calendar = detection.get('manifest', {}).get('calendar', detection['instrument'].calendar_id)
    lower = aggregate(fine['bars'], 'M30', fine['instrument'], as_of, calendar=calendar)
    intervals = _intervals(detection['coverage'], fine['coverage'])
    baseline = base[0].start
    h1, crossing = shared_segments(bars_by_tf['H1'], intervals, baseline)
    m30, child_crossing = shared_segments(lower['bars'], intervals, baseline)
    if child_crossing:
        raise ValueError('A supposedly complete M30 candle crosses missing fine input')
    updated = dict(bars_by_tf, H1=h1, M30=m30)
    audit = dict(scope='MIXED_H1_CONTEXT_REAL_M1_CHILD_DETECTION',
                 source_validation=validation, hashes=fine['hashes'], coverage=fine['coverage'],
                 child_timeframes=['M30'], child_bars=len(m30),
                 parent_bars_crossing_fine_or_coarse_gaps=crossing,
                 uncertainty_intervals=[[a.isoformat(), b.isoformat()] for a,b in intervals],
                 segment_policy='PHYSICAL_MISSING_INTERVAL_EPOCHS; crossing parent bars are non-shareable',
                 context_policy='W/D/H4 remain independently observed H1 aggregates; H1 structure is recomputed with mixed episode barriers',
                 no_imputation=True)
    return updated, {'M30': lower['coverage']}, audit

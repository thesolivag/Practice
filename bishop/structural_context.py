"""Same-timeframe structural direction, distinct from reaction/confirmation stories.

Source locators: course9 339.4–402.4 (D direction versus opposing H4
reaction), Bishop bias/entries55.5–73.5 (recent M/W breakouts), course18
745–807 (BOS versus continuation). Latest-event aggregation is an explicit
presentation policy, not teacher acceptance or an order authorization.
"""
from .v2.types import utc, jsonable

BREAKS = frozenset(('BREAKOUT', 'BOS', 'SWEEP_BOS', 'EXTERNAL_BREAK'))


def summarize(structures, as_of):
    at = utc(as_of)
    output = {}
    for tf, structure in structures.items():
        events = [e for e in structure.events if e.kind in BREAKS and e.side in ('BUY', 'SELL')
                  and e.evidence_status == 'KNOWN' and e.available_at <= at]
        last = max((e.available_at for e in events), default=None)
        recent = [e for e in events if e.available_at == last]
        sides = {e.side for e in recent}
        versions = {}
        for r in structure.ranges:
            if r.available_at <= at and (r.id not in versions or r.available_at >= versions[r.id].available_at):
                versions[r.id] = r
        roots = [r for r in versions.values() if r.parent_id is None and r.status != 'BROKEN']
        output[tf] = dict(
            tf=tf, state='CONFLICT' if len(sides) > 1 else 'DIRECTIONAL' if sides else 'NO_CONFIRMED_BREAK',
            side=next(iter(sides)) if len(sides) == 1 else None,
            available_at=last.isoformat() if last else None,
            recent_breaks=jsonable(tuple(sorted(recent, key=lambda e: e.id))),
            active_root_ranges=[dict(id=r.id, side=r.direction, status=r.status, protected_turn_id=r.protected_turn_id,
                                     origin_ticks=r.origin_ticks, available_at=r.available_at.isoformat())
                                for r in sorted(roots, key=lambda r: r.id)],
            qualification='Recent closed structural break on this timeframe; setup confirmation is separate.')
    return output


def current_segment_readiness(contexts, structures, bars_by_tf, base, coverage, as_of):
    """Prove current structural observations independently of older missing data.

    No gap is removed or called a market holiday. Structure analysis resets
    turns/ranges at aggregation gaps. This proof additionally requires every
    latest break bar and its referenced turning-point bar after the last base
    gap, with complete expected base coverage through the requested horizon.
    It is used only by the bias presentation path, never order authorization.
    """
    if not base:
        return
    at = utc(as_of)
    segment = base[-1].segment_id
    start = next(b.start for b in base if b.segment_id == segment)
    end = base[-1].end
    missing = [utc(t) for t in coverage.get('missing', []) if utc(t) >= start]
    for tf, context in contexts.items():
        structure = structures[tf]
        bars = {b.id: b for b in bars_by_tf.get(tf, ())}
        turns = {t.id: t for t in structure.turns}
        events = {e.id: e for e in structure.events}
        reasons = []
        checked = []
        if missing:
            reasons.append('MISSING_EXPECTED_BASE_SLOTS_IN_CURRENT_SEGMENT_OR_TAIL')
        if not context['recent_breaks']:
            reasons.append('NO_CONFIRMED_BREAK')
        for observation in context['recent_breaks']:
            event = events[observation['id']]
            event_bars = [bars.get(identifier) for identifier in event.bar_ids]
            turn = turns.get(event.reference_id)
            anchor = bars.get(turn.anchor_bar_id) if turn else None
            if not event_bars or any(b is None or not b.complete or b.start < start or b.end > end or b.available_at > at for b in event_bars):
                reasons.append('BREAK_NOT_PROVEN_IN_CURRENT_SEGMENT')
            if turn is None or anchor is None or not anchor.complete or turn.available_at > event.available_at or anchor.start < start or anchor.end > end:
                reasons.append('REFERENCE_NOT_PROVEN_IN_CURRENT_SEGMENT')
            checked.append(dict(event_id=event.id, bar_ids=list(event.bar_ids),
                                reference_id=event.reference_id,
                                reference_bar_id=anchor.id if anchor else None))
        context['current_segment'] = dict(ready=not reasons, scope='CURRENT_SEGMENT_ONLY',
                                          start=start.isoformat(), observed_end=end.isoformat(),
                                          as_of=at.isoformat(), reasons=sorted(set(reasons)),
                                          checked_evidence=checked,
                                          historical_missing_slots=coverage.get('missing_slots', 0))

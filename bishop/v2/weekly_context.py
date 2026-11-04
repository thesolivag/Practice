"""Contemporaneous weekly context without rewriting historical story facts.

The source permits counterweekly D/H4 trades with nearer objectives (session
study WN455–480, DR394–421); this helper does not impose a Weekly veto. Latest
confirmed ROOT-batch ranking is an explicit implementation choice, not verified
mentor scope selection. A destination touch is not positive directional reversal.
"""
from .types import utc


POLICY = 'latest_confirmed_weekly_ROOT_batch_v1_OUR_CHOICE'
TERMINAL = frozenset(('STORY_INVALIDATED', 'STORY_SUSPENDED', 'STORY_RETIRED'))


def resolve(stories, events, at, instrument):
    """Resolve only published ROOT stories and known retirement observations.

    Select the latest clock before testing retirement: a retired current batch
    cannot resurrect older, opposing context. Same-clock stories retain all IDs;
    their IDs never decide direction. Inputs are not modified.
    """
    at = utc(at)
    candidates = tuple(s for s in stories
                       if getattr(s, 'origin_tf', None) == 'W' and s.instrument == instrument
                       and s.details.get('scope_type') == 'ROOT'
                       and utc(s.available_at) <= at)
    result = dict(status='UNKNOWN', side=None, story_ids=(), available_at=None,
                  policy=POLICY)
    if not candidates:
        return result
    latest = max(utc(s.available_at) for s in candidates)
    batch = tuple(s for s in candidates if utc(s.available_at) == latest)
    result.update(story_ids=tuple(sorted(s.id for s in batch)), available_at=latest.isoformat())
    sides = {s.side for s in batch}
    if len(sides) > 1:
        result['status'] = 'CONFLICTED'
        return result
    if sides not in ({'BUY'}, {'SELL'}):
        return result
    identifiers = set(result['story_ids'])
    for event in events:
        if (event.kind in TERMINAL and latest <= utc(event.available_at) <= at
                and (event.reference_id in identifiers
                     or event.details.get('story_id') in identifiers)):
            return result
    result.update(status='KNOWN', side=next(iter(sides)))
    return result

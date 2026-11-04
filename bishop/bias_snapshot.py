"""Current bias view derived from causal stories, without selecting a favorable candidate.

This is a presentation layer, not a new strategy rule. Same-timeframe structure
is separate from reaction/confirmation setup stories. Opposing setup stories
remain a setup conflict. Partial input does not become a neutral market bias.
"""
from .v2.types import utc

TERMINAL = frozenset(('STORY_DESTINATION_REACHED', 'STORY_FLIPPED',
                      'STORY_INVALIDATED', 'STORY_SUSPENDED'))
# An opposite confirmation at another scope is a reassessment observation.
# It does not prove that this story's protected scope has reversed. Match the
# entry activity contract: coexistence remains visible until an explicit flip,
# structural invalidation or another declared retirement boundary is known.


def snapshot(result):
    at = utc(result['as_of'])
    symbol = result['instrument']['symbol']
    events = {}
    for event in result.get('story_events', []):
        if event['kind'] in TERMINAL and utc(event['clock']['available_at']) <= at:
            events.setdefault(event['reference_id'], []).append(event['kind'])
    groups = {}
    excluded = []
    for story in result.get('stories', []):
        if story['instrument'] != symbol or utc(story['clock']['available_at']) > at:
            continue
        reasons = list(events.get(story['id'], []))
        if story.get('state', 'CONFIRMED') != 'CONFIRMED':
            reasons.append(story['state'])
        if story.get('details', {}).get('owner_selection') == 'BLOCKED_COUNTERWEEKLY':
            reasons.append('BLOCKED_COUNTERWEEKLY')
        if reasons:
            excluded.append({'story_id': story['id'], 'reasons': sorted(set(reasons))})
        else:
            groups.setdefault(story['origin_tf'], []).append(story)
    contexts = result.get('structural_context', {})
    confirmed_mode = result.get('story_context_evaluated') is True or result.get('scope') == 'CONFIRMED_BIAS_ONLY'
    waiting = [e for e in result.get('story_events', ()) if e['kind']=='BIAS_WAIT_EXTERNAL_BREAK'
               and utc(e['clock']['available_at'])<=at]
    tfs = set(result.get('policy', {}).get('origin_tfs', [])) | set(groups)
    rows = []
    for tf in sorted(tfs):
        stories = sorted(groups.get(tf, []), key=lambda s: (s['clock']['available_at'], s['id']))
        sides = {s['side'] for s in stories}
        coverage = result.get('coverage', {}).get('timeframes', {}).get(tf, {})
        incomplete = result.get('status') not in ('COMPUTED_UNVALIDATED', 'COMPUTED')
        if incomplete:
            state, side = 'DATA_INCOMPLETE', None
        elif len(sides) > 1:
            state, side = 'CONFLICT', None
        elif sides:
            state, side = 'DIRECTIONAL', next(iter(sides))
        else:
            state, side = 'NO_CONFIRMED_BIAS', None
        story_state, story_side = state, side
        if result.get('story_context_evaluated') is False:
            story_state, story_side = 'NOT_EVALUATED', None
        structural = contexts.get(tf)
        segment_ready = bool(result.get('scope') == 'BIAS_ONLY' and structural
                             and structural.get('current_segment', {}).get('ready'))
        story_proof=result.get('story_context_readiness',{}).get(tf)
        if confirmed_mode:
            segment_ready=bool(story_proof and story_proof.get('ready'))
            proof_failed=bool(stories and story_proof is not None and not story_proof.get('ready'))
            if (incomplete and not segment_ready) or proof_failed:
                state,side='DATA_INCOMPLETE',None
            elif len(sides)>1:
                state,side='CONFLICT',None
            elif sides:
                state,side='DIRECTIONAL',next(iter(sides))
            else:
                pending=any(e.get('details',{}).get('origin_tf',e.get('tf'))==tf for e in waiting)
                state,side=('WAIT_EXTERNAL_BREAK' if pending else 'NO_CONFIRMED_BIAS'),None
            story_state,story_side=state,side
        elif structural is not None and (not incomplete or segment_ready):
            state, side = structural['state'], structural['side']
        rows.append(dict(instrument=symbol, tf=tf, state=state, side=side,
                         basis='CONFIRMED_STORIES' if confirmed_mode or structural is None else 'SAME_TIMEFRAME_STRUCTURE',
                         setup_story_state=story_state, setup_story_side=story_side,
                         structural_context=structural,
                         story_context_readiness=story_proof,
                         active_story_count=sum(g['count'] for g in result.get('active_story_groups',()) if g['origin_tf']==tf) if 'active_story_groups' in result else len(stories),
                         waiting_external_break=[e for e in waiting if e.get('details',{}).get('origin_tf',e.get('tf'))==tf],
                         historical_data_incomplete=incomplete,
                         coverage_scope='CURRENT_SEGMENT_ONLY' if incomplete and segment_ready else 'REQUESTED_WINDOW',
                         story_ids=[s['id'] for s in stories],
                         routes=sorted({s['route'] for s in stories}),
                         level_ids=sorted({s['level_id'] for s in stories if s.get('level_id')}),
                         coverage=coverage))
    return dict(instrument=symbol, as_of=at.isoformat(), rows=rows, excluded=excluded,
                qualification=('Confirmed reaction-to-break story reading; entry and teacher agreement remain separate.' if confirmed_mode else 'Unvalidated structural direction; setup confirmation and teacher agreement are separate.'))


def changes(previous, current):
    """Only direction/state transitions create previews; new IDs alone do not."""
    old = {r['tf']: r for r in (previous or {}).get('rows', [])}
    output = []
    for row in current['rows']:
        before = old.get(row['tf'])
        if before and (before['state'], before['side']) == (row['state'], row['side']):
            continue
        output.append(dict(kind='BIAS_CHANGED', instrument=current['instrument'],
                           tf=row['tf'], side=row['side'], state=row['state'],
                           previous_state=before['state'] if before else None,
                           previous_side=before['side'] if before else None,
                           coverage_scope=row.get('coverage_scope', 'REQUESTED_WINDOW'),
                           as_of=current['as_of'], story_ids=row['story_ids']))
    return output

from copy import deepcopy
import pytest
from reports.replay_teacher_candidates_isolated import independent_orders


def fixture():
    setup = dict(id='a', instrument='GBPUSD', side='SELL', tf='H1', model='confirmation_bo',
        level_id='level', clock=dict(occurred_from='2026-01-01T01:00:00Z',
        occurred_to='2026-01-01T01:00:00Z', available_at='2026-01-01T01:00:00Z'),
        entry_ticks=100, stop_ticks=110, target_ticks=80, order_type='LIMIT',
        expires_at='2026-01-02T01:00:00Z', status='ELIGIBLE', story_id='story')
    return dict(case={'side': 'SELL'}, summary={'as_of': '2026-01-01T02:00:00Z'}, result=dict(
        setups=[setup], stories=[dict(id='story', details={})], story_events=[]))


def test_isolated_deduplicates_contexts_preserves_blocks_and_known_cancellation():
    saved = fixture()
    duplicate = {**deepcopy(saved['result']['setups'][0]), 'id': 'b'}
    blocked = {**deepcopy(duplicate), 'id': 'c', 'story_id': 'blocked'}
    saved['result']['setups'].extend([duplicate, blocked])
    saved['result']['stories'].append(dict(id='blocked', details={'owner_selection': 'BLOCKED_COUNTERWEEKLY'}))
    for clock in ['2026-01-01T01:30:00Z', '2026-01-01T03:00:00Z']:
        saved['result']['story_events'].append(dict(reference_id='story', kind='STORY_INVALIDATED',
            clock={'available_at': clock}, details={}))
    original = deepcopy(saved)
    orders, actions, excluded = independent_orders(saved)
    assert len(orders) == 1
    assert len(actions) == 1
    assert actions[0]['available_at'] == '2026-01-01T01:30:00+00:00'
    assert excluded == {'DUPLICATE_CONTEXT': 1, 'BLOCKED_COUNTERWEEKLY': 1}
    assert saved == original


def test_future_candidate_is_rejected():
    saved = fixture()
    saved['summary']['as_of'] = '2026-01-01T00:00:00Z'
    with pytest.raises(ValueError, match='Future setup'):
        independent_orders(saved)

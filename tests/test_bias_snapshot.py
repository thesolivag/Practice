from copy import deepcopy
from bishop.bias_snapshot import snapshot, changes

AT = '2026-06-24T12:00:00Z'


def story(identifier, side='SELL', available=AT):
    return dict(id=identifier, instrument='GBPUSD', side=side, origin_tf='D',
                clock={'available_at': available}, state='CONFIRMED', route='kl_structural',
                level_id='daily-kl', details={})


def result(stories, events=()):
    return dict(as_of=AT, instrument={'symbol': 'GBPUSD'},
                policy={'origin_tfs': ['D']}, status='COMPUTED_UNVALIDATED',
                stories=stories, story_events=events, coverage={})


def test_opposing_stories_are_conflict_not_cherry_picked_agreement():
    row = snapshot(result([story('sell'), story('buy', 'BUY')]))['rows'][0]
    assert row['state'] == 'CONFLICT' and row['side'] is None


def test_unavailable_opposite_story_cannot_flip_bias():
    row = snapshot(result([story('sell'), story('buy', 'BUY', '2026-06-24T13:00:00Z')]))['rows'][0]
    assert row['side'] == 'SELL'


def test_terminal_event_is_applied_only_when_available():
    event = dict(kind='STORY_INVALIDATED', reference_id='sell', clock={'available_at': '2026-06-24T13:00:00Z'})
    data = result([story('sell')], [event])
    assert snapshot(data)['rows'][0]['side'] == 'SELL'
    event['clock']['available_at'] = AT
    assert snapshot(data)['rows'][0]['state'] == 'NO_CONFIRMED_BIAS'


def test_missing_data_does_not_publish_direction_or_market_neutrality():
    data = result([story('sell')])
    data['status'] = 'PARTIAL_UNVALIDATED'
    row = snapshot(data)['rows'][0]
    assert row['state'] == 'DATA_INCOMPLETE' and row['side'] is None


def test_owner_blocked_story_is_excluded_and_notified_ids_do_not_cause_spam():
    blocked = story('blocked', 'BUY')
    blocked['details']['owner_selection'] = 'BLOCKED_COUNTERWEEKLY'
    first = snapshot(result([story('sell'), blocked]))
    assert first['rows'][0]['side'] == 'SELL'
    second = deepcopy(first)
    second['rows'][0]['story_ids'] = ['different-same-direction']
    assert changes(first, second) == []
    second['rows'][0].update(side='BUY')
    assert len(changes(first, second)) == 1


def test_store_keeps_latest_snapshot_and_suppresses_duplicate_bias_previews():
    from bishop.paper_store import Store
    store = Store()
    data = {**result([story('sell')]), 'schema': 'test', 'input': {}}
    store.persist_result(data, 'first')
    assert len(store.list('outbox')) == 1
    store.persist_result(data, 'first')
    newer = deepcopy(data)
    newer['as_of'] = '2026-06-24T13:00:00Z'
    store.persist_result(newer, 'second')
    assert len(store.list('outbox')) == 1
    older = deepcopy(data)
    older['as_of'] = '2026-06-24T11:00:00Z'
    store.persist_result(older, 'old')
    assert store.list('bias_snapshots')[0]['as_of'] == '2026-06-24T13:00:00+00:00'
    assert len(store.list('outbox')) == 1


def test_bias_only_scan_bypasses_entries_and_has_distinct_run_identity(monkeypatch):
    from datetime import datetime, timezone
    from bishop.v2.engine import run
    from bishop.v2.types import Instrument, StrategyPolicy
    from bishop.v2.simulation import Costs
    import bishop.v2.engine as engine
    instrument = Instrument('X', '1', '1', calendar_id='24x7_utc_v1', anchor_id='utc_epoch_v1')
    feed = dict(instrument=instrument, bars=())
    at = datetime(2026, 6, 24, tzinfo=timezone.utc)
    policy = StrategyPolicy(entry_tfs=('H1',), origin_tfs=('D',))
    full = run(feed, as_of=at, policy=policy, costs=Costs())
    def forbidden(*args, **kwargs):
        raise AssertionError('Bias scan entered setup detection')
    monkeypatch.setattr(engine, 'detect_setups', forbidden)
    monkeypatch.setattr(engine, 'find_stories', forbidden)
    bias = run(feed, as_of=at, policy=policy, costs=Costs(), bias_only=True)
    assert bias['scope'] == 'BIAS_ONLY'
    assert bias['run_id'] != full['run_id']
    assert not bias['setups'] and not bias['orders']
    assert bias['story_context_evaluated'] is False
    assert 'H1' not in bias['structural_context']
    assert bias['teacher_acceptance'] == 'NOT_REPLAYED'


def test_cross_scope_opposite_confirmation_reassesses_without_retiring_old_story():
    # build_story_contract: an unrelated opposite scope can coexist; a newer
    # confirmed candidate alone must not imply a protected-scope reversal.
    event = dict(kind='OPPOSITE_STORY_CONFIRMED', reference_id='old-buy',
                 clock={'available_at': AT})
    view = snapshot(result([story('old-buy', 'BUY'), story('new-sell')], [event]))
    assert view['rows'][0]['state'] == 'CONFLICT'
    assert view['rows'][0]['side'] is None
    assert set(view['rows'][0]['story_ids']) == {'old-buy', 'new-sell'}
    assert view['excluded'] == []


def test_explicit_scope_flip_still_retires_old_story_for_current_view():
    event = dict(kind='STORY_FLIPPED', reference_id='old-buy',
                 clock={'available_at': AT})
    view = snapshot(result([story('old-buy', 'BUY'), story('new-sell')], [event]))
    assert view['rows'][0]['side'] == 'SELL'
    assert view['excluded'] == [{'story_id': 'old-buy', 'reasons': ['STORY_FLIPPED']}]


def test_persisted_closed_hour_is_reused_but_revised_input_is_not_silently_accepted(tmp_path, monkeypatch):
    import json
    from hashlib import sha256
    from bishop import scan_bias
    from bishop.paper_store import Store
    from bishop.v2.types import stable_id
    raw = tmp_path/'source.csv'
    raw.write_text('already frozen input\n')
    manifest = dict(symbol='GBPUSD', venue='ICMARKETS')
    metadata = tmp_path/'manifest.json'
    metadata.write_text(json.dumps(manifest))
    store = Store()
    data = {**result([story('sell')]), 'schema':'test', 'scope':'BIAS_ONLY',
            'input':dict(sha256=sha256(raw.read_bytes()).hexdigest(),manifest=stable_id('manifest',manifest))}
    store.persist_result(data,'2026-06-24T12:00:00+00:00',namespace='bias-scan-GBPUSD')
    monkeypatch.setattr('bishop.runtime.application_store',lambda:store)
    def no_recompute(*args,**kwargs):
        raise AssertionError('A persisted closed hour must not be recomputed')
    monkeypatch.setattr(scan_bias,'run',no_recompute)
    args=['--input',str(raw),'--manifest',str(metadata),'--as-of',AT,'--out',str(tmp_path/'out'),'--persist','--structural-only']
    scan_bias.main(args)
    assert json.loads((tmp_path/'out/engine.json').read_text())['as_of']==AT
    raw.write_text('revised source\n')
    import pytest
    with pytest.raises(ValueError,match='different input'):
        scan_bias.main(args)

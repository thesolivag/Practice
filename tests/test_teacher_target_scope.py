from reports.audit_teacher_target_scope import audit


def test_target_inventory_excludes_unpublished_versions_and_wrong_direction():
    before = '2026-01-01T00:00:00Z'
    now = '2026-01-02T00:00:00Z'
    future = '2026-01-03T00:00:00Z'
    saved = dict(case={'id': 'example', 'tf': 'H1'}, summary={'input_sha256': 'frozen'}, result={
        'setups': [dict(side='SELL', tf='H1', model='bo', clock={'available_at': now},
                        entry_ticks=100, stop_ticks=110, target_ticks=80, details={})],
        'diagnostics': {'structures': {'H4': {'ranges': [
            dict(id='range', available_at=before, direction='SELL', endpoint_ticks=80),
            dict(id='range', available_at=future, direction='SELL', endpoint_ticks=60),
            dict(id='opposite', available_at=before, direction='BUY', endpoint_ticks=70),
            dict(id='behind', available_at=before, direction='SELL', endpoint_ticks=120),
        ]}}}})
    report = audit(saved)
    assert report['plans'][0]['published_directional_ranges']['H4'] == [
        dict(id='range', available_at=before, direction='SELL', endpoint_ticks=80)]
    assert report['strict_status'] == 'UNRESOLVED'
    assert report['source_price_used_for_selection'] is False

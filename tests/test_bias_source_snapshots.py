from reports.replay_bias_source_snapshots import probe


def test_trade_direction_is_not_a_substitute_for_unlabeled_source_bias():
    source = dict(case_id='source', pair='EURUSD', side=None, trade_side='BUY', bias_tf=None,
                  snapshot_time='2026-06-24T12:00:00Z')
    row = probe(source, [])
    assert row['status'] == 'SOURCE_BIAS_PENDING'
    assert row['teacher_acceptance'] == 'SOURCE_ASSESSMENT_CLOCK_UNRESOLVED'


def test_no_snapshot_clock_is_invented_from_an_entry_timeframe():
    source = dict(case_id='source', pair='EURUSD', side='BUY', bias_tf='D',
                  entry_tf='H2', snapshot_time=None)
    assert probe(source, [])['status'] == 'SOURCE_SNAPSHOT_TIME_PENDING'


def test_missing_input_does_not_count_as_direction_mismatch():
    source = dict(case_id='source', pair='EURUSD', side='BUY', bias_tf='D',
                  snapshot_time='2026-06-24T12:00:00Z')
    assert probe(source, [])['status'] == 'INPUT_PENDING'

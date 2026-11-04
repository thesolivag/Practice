from reports.audit_teacher_trade_behavior import summarize


def test_alternative_timeframe_and_unselected_candidate_do_not_inherit_win():
    def setup(sid, tf):
        return dict(id=sid, side='SELL', tf=tf, model='confirmation_bo',
            clock={'available_at': '2026-01-01T00:00:00Z'}, entry_ticks=100,
            stop_ticks=110, target_ticks=80, status='ELIGIBLE',
            details={'protected_objects': [('wick', 109, 'pattern_wick')]}, evidence_ids=['wick'])
    saved = dict(case={'id': 'example', 'side': 'SELL', 'tf': 'H1'},
        summary={'input_sha256': 'frozen'}, result=dict(costs={},
        setups=[setup('teacher', 'H1'), setup('alternative', 'H2')],
        orders=[{'setup_id': 'alternative', 'id': 'order'}]))
    execution = dict(scope='HYPOTHETICAL', status='SIMULATED_FROZEN_ORDERS',
        snapshot_as_of='snapshot', as_of='horizon', observations=[{'id': 'order', 'outcome': 'WIN'}])
    report = summarize(saved, execution)
    teacher, alternative = report['plans']
    assert teacher['timeframe_relation'] == 'TEACHER_TIMEFRAME'
    assert teacher['selected_orders'] == []
    assert alternative['timeframe_relation'] == 'ALTERNATIVE_TIMEFRAME'
    assert report['selected_same_direction_outcomes'] == {'WIN': 1}
    assert report['strict_teacher_status'] == 'UNRESOLVED'

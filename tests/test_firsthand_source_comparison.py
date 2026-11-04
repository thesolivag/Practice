from copy import deepcopy
import pytest
from reports.compare_firsthand_source import compare


def fixture():
    observation = dict(case_id='loss', instrument='X', side='BUY', entry_tf='H1',
                       source_observed_window=dict(start_utc='2026-06-09T00:00:00Z',
                                                   end_utc='2026-06-10T00:00:00Z'),
                       drawings=[dict(entry='1.00000', stop='0.99900', target=None,
                                      role='VISIBLE_DRAWING_NOT_VERIFIED_FILL')])
    def setup(ident, price, at='2026-06-09T06:00:00Z', status='ELIGIBLE'):
        return dict(id=ident, tf='H1', side='BUY', model='confirmation_engulfed_oc',
                    story_id='story', clock=dict(available_at=at), entry_ticks=price,
                    stop_ticks=99900, target_ticks=None, status=status,
                    details=dict(unresolved_reasons=['qualified_target_unresolved']))
    report = dict(plan=dict(case_id='loss'), result=dict(
        instrument=dict(symbol='X', tick_size='0.00001', distance_unit='0.0001'),
        setups=[setup('exact_but_unresolved', 100000, status='UNRESOLVED'),
                setup('different', 100005), setup('outside', 100000, '2026-06-10T00:00:00Z')]))
    return report, observation


def test_all_candidates_retained_without_promoting_exact_drawing_or_fitting_tolerance():
    report, observation = fixture()
    result = compare(report, observation)
    assert [r['setup_id'] for r in result['rows']] == ['exact_but_unresolved', 'different']
    assert result['teacher_acceptance'] == 'NOT_AWARDED'
    assert result['rows'][0]['status'] == 'UNRESOLVED'
    assert result['rows'][1]['differences'][0]['signed_difference_units']['entry'] == '0.5'
    assert result['rows'][0]['differences'][0]['signed_difference_units']['target'] is None


def test_wrong_source_instrument_cannot_be_compared():
    report, observation = fixture()
    wrong = deepcopy(observation); wrong['instrument'] = 'Y'
    with pytest.raises(ValueError, match='instrument differ'):
        compare(report, wrong)


def test_missing_source_timeframe_is_reported_separately_from_no_setups():
    report, observation = fixture()
    observation['entry_tf'] = 'M30'
    assert compare(report, observation)['status'] == 'SOURCE_TIMEFRAME_NOT_DETECTED'
    report['result']['setups'] = []
    assert compare(report, observation)['status'] == 'NO_SETUP_IN_SOURCE_WINDOW'

from copy import deepcopy
import pytest
from reports.collect_teacher_execution_m1 import bounded_job


def test_execution_collection_is_single_pair_and_bounded():
    report = dict(case_id='pdf-p27-gbpusd-sell-1', forward_as_of='2026-07-08T11:49:00Z',
        plans=[dict(available_at='2026-06-24T03:00:00Z', selected_orders=[{}])])
    job = bounded_job(report)
    assert job['base_tf'] == 'M1' and job['pair'] == 'GBPUSD'
    assert job['start'] == '2026-06-24T03:00:00+00:00'
    other = deepcopy(report)
    other['case_id'] = 'other'
    with pytest.raises(ValueError):
        bounded_job(other)
    report['forward_as_of'] = '2026-08-01T00:00:00Z'
    with pytest.raises(ValueError):
        bounded_job(report)

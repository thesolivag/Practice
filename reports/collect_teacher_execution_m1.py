"""Bounded read-only M1 collection for the unresolved GBPUSD execution audit."""
import json
from datetime import timedelta
from pathlib import Path
from bishop.collect_teacher_data import HistoricalClient, collect_job, safe_failure
from bishop.v2.types import utc, stable_id


def bounded_job(report):
    if report['case_id'] != 'pdf-p27-gbpusd-sell-1':
        raise ValueError('Only the reviewed GBPUSD case is authorized here')
    start = min(utc(p['available_at']) for p in report['plans'] if p['selected_orders'])
    end = utc(report['forward_as_of'])
    if not start < end <= start + timedelta(days=15):
        raise ValueError('Execution collection must be bounded to at most fifteen days')
    return dict(id=stable_id('execution_m1', report['case_id'], start, end),
        pair='GBPUSD', base_tf='M1', start=start.isoformat(), end=end.isoformat(),
        case_ids=[report['case_id']], purpose='FROZEN_EXECUTION_ONLY_NO_DETECTION')


def main():
    report = json.loads(Path('reports/teacher_isolated_candidates/pdf-p27-gbpusd-sell-1.json').read_text())
    job = bounded_job(report)
    metadata = json.loads(Path('reports/teacher_icmarkets_metadata.json').read_text())['GBPUSD']
    out = Path('data/teacher_execution_m1')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'plan.json').write_text(json.dumps(job, indent=2) + '\n')
    client = None
    try:
        client = HistoricalClient()
        client.connect()
        client.app_auth()
        client.account_auth()
        result = collect_job(client, job, metadata, out)
        status = dict(status='RAW_COLLECTED_UNVALIDATED', **result)
    except Exception as exc:
        status = dict(status='FAILED', **safe_failure(exc))
    finally:
        if client is not None:
            client.close()
    (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(status))
    return 0 if status['status'] == 'RAW_COLLECTED_UNVALIDATED' else 1


if __name__ == '__main__':
    raise SystemExit(main())

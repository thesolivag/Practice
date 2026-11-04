"""Read-only M1 collection for the frozen June5–13 USDCAD portfolio window."""
import json
from pathlib import Path
from bishop.collect_teacher_data import HistoricalClient, collect_job, safe_failure
from bishop.v2.types import stable_id

OUT = Path('data/usdcad_execution_m1')


def main():
    job = dict(id=stable_id('execution_m1', 'USDCAD', '2026-06-05', '2026-06-13'),
               pair='USDCAD', base_tf='M1', start='2026-06-05T00:00:00Z',
               end='2026-06-13T00:00:00Z', case_ids=['video-t3-usdcad-buy-open'],
               purpose='EXECUTION_ONLY_ALL_PORTFOLIO_ORDERS_NO_OUTCOME_SELECTION')
    metadata = json.loads(Path('reports/teacher_icmarkets_metadata.json').read_text())['USDCAD']
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'plan.json').write_text(json.dumps(job, indent=2) + '\n')
    client = None
    try:
        client = HistoricalClient()
        client.connect(); client.app_auth(); client.account_auth()
        result = collect_job(client, job, metadata, OUT)
        status = dict(status='RAW_COLLECTED_UNVALIDATED', **result)
    except Exception as exc:
        status = dict(status='FAILED', **safe_failure(exc))
    finally:
        if client is not None:
            client.close()
    (OUT / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(status))
    return 0 if status['status'] == 'RAW_COLLECTED_UNVALIDATED' else 1


if __name__ == '__main__':
    raise SystemExit(main())

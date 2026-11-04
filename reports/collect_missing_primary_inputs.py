"""Collect the three missing firsthand T3 FX histories with read-only credentials."""
import argparse
import json
from pathlib import Path
from bishop.collect_teacher_data import HistoricalClient, collect_job, safe_failure
from bishop.v2.types import stable_id

CASES = {'AUDCHF': 'video-t3-audchf-buy-loss',
         'NZDCHF': 'video-t3-nzdchf-buy-loss',
         'USDJPY': 'video-t3-usdjpy-buy-manual-exit'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', choices=tuple(CASES), required=True)
    args = parser.parse_args(argv)
    pair = args.pair
    job = dict(id=stable_id('primary_h1', pair, '2025-04-09', '2026-06-13'),
               pair=pair, base_tf='H1', start='2025-04-09T00:00:00Z',
               end='2026-06-13T00:00:00Z', case_ids=[CASES[pair]],
               purpose='PRIMARY_VIDEO_WIN_AND_LOSS_COVERAGE_NOT_OUTCOME_SELECTION')
    metadata = json.loads(Path('reports/teacher_icmarkets_metadata.json').read_text())[pair]
    out = Path('data/primary_missing_inputs') / pair
    out.mkdir(parents=True, exist_ok=True)
    (out / 'plan.json').write_text(json.dumps(job, indent=2) + '\n')
    client = None
    try:
        client = HistoricalClient()
        client.connect(); client.app_auth(); client.account_auth()
        status = dict(status='RAW_COLLECTED_UNVALIDATED',
                      **collect_job(client, job, metadata, out))
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

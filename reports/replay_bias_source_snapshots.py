"""Same-timeframe bias-context diagnostics on saved IC Markets data only.

PDF creation clocks are snapshot probes, never setup clocks or fill clocks.
The report cannot mark a teacher example verified, even on direction agreement.
"""
import argparse
from datetime import timedelta
import json
from pathlib import Path
from bishop import settings
from bishop.bias_snapshot import snapshot
from bishop.v2.engine import run
from bishop.v2.simulation import Costs
from bishop.v2.types import utc
from dataclasses import replace


def inventory(root):
    records = []
    for path in Path(root).rglob('*.csv.manifest.json'):
        manifest = json.loads(path.read_text())
        raw = Path(str(path).removesuffix('.csv.manifest.json') + '.csv.gz')
        if manifest.get('base_tf') == 'H1' and raw.is_file():
            records.append((path, raw, manifest))
    return records


def probe(source, inputs):
    row = dict(case_id=source['case_id'], pair=source['pair'], source_side=source.get('side'),
               source_tf=source.get('bias_tf'), snapshot_time=source.get('snapshot_time'),
               teacher_acceptance='SOURCE_ASSESSMENT_CLOCK_UNRESOLVED')
    if source.get('side') not in ('BUY', 'SELL') or not source.get('bias_tf'):
        return dict(row, status='SOURCE_BIAS_PENDING')
    if not source.get('snapshot_time'):
        return dict(row, status='SOURCE_SNAPSHOT_TIME_PENDING')
    clock = utc(source['snapshot_time'])
    start = clock.replace(minute=0, second=0, microsecond=0) - timedelta(days=35)
    candidates = []
    for path, raw, manifest in inputs:
        if manifest.get('symbol') != source['pair']:
            continue
        if manifest.get('symbol_mapping_status') == 'SURROGATE_QUOTE_CURRENCY_DIFFERENT':
            continue
        if manifest.get('calendar_id') == 'unresolved_broker_schedule':
            continue
        if (utc(manifest['requested_start']) <= start and utc(manifest['requested_end']) >= clock):
            candidates.append((manifest.get('rows', 0), str(path), path, raw, manifest))
    if not candidates:
        return dict(row, status='INPUT_PENDING', reason='No matching H1 snapshot with declared calendar and bounded warmup coverage')
    _, _, path, raw, manifest = min(candidates)
    policy = replace(settings.strategy_policy(settings.DEFAULTS), origin_tfs=('D', 'H4'))
    try:
        result = run(raw, manifest, as_of=clock, history_start=start, policy=policy,
                     costs=Costs(), bias_only=True)
        view = snapshot(result)
    except (ValueError, KeyError, RuntimeError) as exc:
        return dict(row, status='INPUT_UNRESOLVED', error_type=type(exc).__name__, reason=str(exc)[:300], input_path=str(raw))
    current = next(r for r in view['rows'] if r['tf'] == source['bias_tf'])
    if current['state'] != 'DIRECTIONAL':
        status = 'CONTEXT_UNRESOLVED'
    else:
        status = 'AGREES_AT_SNAPSHOT' if current['side'] == source['side'] else 'DIFFERS_AT_SNAPSHOT'
    return dict(row, status=status, input_path=str(raw), manifest_path=str(path),
                input_sha256=result['input'].get('sha256'), engine_status=result['status'],
                history_start=start.isoformat(), structural_direction=current['side'],
                structural_state=current['state'], structural_context=current['structural_context'],
                setup_story_state=current['setup_story_state'],
                interpretation='Same-TF structural direction only; does not establish source-object identity, setup agreement, entry agreement or profitability.')


def main():
    from collections import Counter
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', default='reports/bias_validation/snapshot_inventory.json')
    a = p.parse_args()
    annotations = json.loads(Path('reports/bias_validation/source_annotations.json').read_text())
    inputs = inventory('data/teacher_icmarkets_runs')
    results = []
    for source in annotations['examples']:
        row = probe(source, inputs)
        results.append(row)
        print(row['case_id'], row['status'], flush=True)
    output = dict(scope='SOURCE_CREATION_SNAPSHOT_DIRECTION_ONLY',
                  fixture_sha256=annotations['fixture_sha256'],
                  qualification='No teacher setup clocks verified. Direction agreement is not teacher-example acceptance.',
                  counts=dict(Counter(r['status'] for r in results)), examples=results)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2) + '\n')


if __name__ == '__main__':
    main()

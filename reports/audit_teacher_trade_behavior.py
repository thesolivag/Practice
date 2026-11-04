"""Replay frozen orders and compare trade behavior across confirmation timeframes.

No new detection, candidate promotion, outcome-based selection, or teacher match
claim. Alternative timeframes remain separate from the demonstrated timeframe.
"""
import argparse
from collections import Counter
from datetime import timedelta
import gzip
import json
from pathlib import Path
from reports.replay_collected_teacher_examples_v2 import digest, forward_outcomes
from bishop.v2.types import utc


def summarize(saved, execution):
    case, result = saved['case'], saved['result']
    orders = {o['setup_id']: o for o in result['orders']}
    observations = {o['id']: o for o in execution.get('observations', [])}
    groups = {}
    for setup in result['setups']:
        if setup['side'] != case['side']:
            continue
        key = (setup['tf'], setup['model'], setup['clock']['available_at'],
               setup['entry_ticks'], setup['stop_ticks'], setup['target_ticks'])
        group = groups.setdefault(key, dict(tf=setup['tf'], model=setup['model'],
            available_at=setup['clock']['available_at'],
            timeframe_relation='TEACHER_TIMEFRAME' if setup['tf'] == case['tf'] else 'ALTERNATIVE_TIMEFRAME',
            entry_ticks=setup['entry_ticks'], stop_ticks=setup['stop_ticks'],
            target_ticks=setup['target_ticks'], contexts=0, selected_orders=[],
            context_status_counts={}, stop_protection_shortfalls=[],
            protection_evidence_present=False))
        group['contexts'] += 1
        status = setup['status']
        group['context_status_counts'][status] = group['context_status_counts'].get(status, 0) + 1
        details = setup['details']
        group['protection_evidence_present'] |= bool(details.get('protected_objects'))
        for shortfall in details.get('protection_shortfall', []):
            if shortfall not in group['stop_protection_shortfalls']:
                group['stop_protection_shortfalls'].append(shortfall)
        if setup['id'] in orders:
            order = orders[setup['id']]
            group['selected_orders'].append(dict(order_id=order['id'],
                observation=observations.get(order['id']),
                evidence_ids=setup['evidence_ids'],
                protected_objects=details.get('protected_objects', [])))
    plans = list(groups.values())
    return dict(case_id=case['id'], teacher_tf=case['tf'], direction=case['side'],
        strict_teacher_status='UNRESOLVED',
        interpretation='Model hypothetical outcomes; unselected candidates have no execution outcome. '
            'Alternative timeframe is not an exact teacher confirmation. Protection evidence is not teacher validation.',
        frozen_order_scope=execution['scope'], forward_status=execution['status'],
        snapshot_as_of=execution['snapshot_as_of'], forward_as_of=execution['as_of'],
        costs=result['costs'], input_sha256=saved['summary']['input_sha256'],
        plan_counts_by_timeframe=dict(Counter(p['tf'] for p in plans)),
        selected_same_direction_outcomes=dict(Counter(
            (o['observation'] or {}).get('outcome', 'MISSING_OBSERVATION')
            for p in plans for o in p['selected_orders'])), plans=plans)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('traces', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for path in args.traces:
        with gzip.open(path, 'rt') as stream:
            saved = json.load(stream)
        plan = dict(saved['plan'])
        if digest(plan['input_path']) != saved['summary']['input_sha256']:
            raise ValueError('Frozen trace input changed')
        metadata = json.loads(Path(plan['manifest_path']).read_text())
        # Historical planning used a later exploratory cutoff. Use the actual
        # detector snapshot, never that stale cutoff, for frozen-order execution.
        plan['as_of'] = saved['summary']['as_of']
        plan['forward_as_of'] = min(utc(metadata['requested_end']),
            utc(plan['as_of']) + timedelta(days=14)).isoformat()
        execution = forward_outcomes(saved['result'], plan, metadata)
        report = summarize(saved, execution)
        (args.output / (report['case_id'] + '.json')).write_text(json.dumps(report, indent=2) + '\n')
        print(report['case_id'], json.dumps(report['plan_counts_by_timeframe']),
              json.dumps(report['selected_same_direction_outcomes']), report['forward_status'])


if __name__ == '__main__':
    main()

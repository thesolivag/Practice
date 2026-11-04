"""Refine ambiguous frozen candidate execution without changing strategy detection."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
from bishop.v2.aggregation import aggregate
from bishop.v2.feed import load_feed
from bishop.v2.simulation import simulate, Costs
from bishop.v2.types import Order, Clock, jsonable, utc
from reports.replay_collected_teacher_examples_v2 import digest
from reports.replay_teacher_candidates_isolated import independent_orders


def compare_coarse(coarse, fine):
    left = {b.start: b for b in coarse}
    right = {b.start: b for b in fine}
    mismatches = []
    fields = ('open_ticks', 'high_ticks', 'low_ticks', 'close_ticks')
    for start in sorted(left.keys() & right.keys()):
        a, b = left[start], right[start]
        if any(getattr(a, k) != getattr(b, k) for k in fields):
            mismatches.append(dict(start=start.isoformat(), coarse={k: getattr(a, k) for k in fields},
                                   fine_aggregate={k: getattr(b, k) for k in fields}))
    return dict(compared_bars=len(left.keys() & right.keys()),
                missing_fine_aggregates=[t.isoformat() for t in sorted(left.keys() - right.keys())],
                mismatches=mismatches,
                status='CONSISTENT' if left and left.keys() <= right.keys() and not mismatches else 'UNRESOLVED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with gzip.open(args.trace, 'rt') as stream:
        saved = json.load(stream)
    previous = json.loads(args.previous.read_text())
    if previous['case_id'] != saved['case']['id'] or previous['input_sha256'] != saved['summary']['input_sha256']:
        raise ValueError('Prior report does not match frozen detector input')
    old = {o['order_id']: o['observation'] for p in previous['plans'] for o in p['selected_orders']
           if o['observation'] and o['observation']['outcome'] == 'CENSORED'}
    orders, actions, _ = independent_orders(saved)
    orders = [Order(**{**o, 'clock': Clock(**o['clock'])}) for o in orders if o['id'] in old]
    if len(orders) != len(old) or not orders:
        raise ValueError('Ambiguous candidate identity mismatch or empty selection')
    meta = json.loads(args.manifest.read_text())
    coarse_meta = json.loads(Path(saved['plan']['manifest_path']).read_text())
    for key in ('symbol', 'tick_size', 'distance_unit', 'venue', 'price_basis', 'anchor_id', 'calendar_id'):
        if meta[key] != coarse_meta[key]:
            raise ValueError('Execution instrument convention mismatch: ' + key)
    if digest(saved['plan']['input_path']) != saved['summary']['input_sha256']:
        raise ValueError('Frozen detector input changed')
    lower = min(o.available_at for o in orders)
    horizon = utc(previous['forward_as_of'])
    if utc(meta['requested_start']) > lower or utc(meta['requested_end']) < horizon:
        raise ValueError('Finer feed does not cover frozen execution window')
    fine = load_feed(args.feed, meta, horizon, lower)
    coarse = load_feed(saved['plan']['input_path'], coarse_meta, horizon, lower)
    rolled = aggregate(fine['bars'], coarse_meta['base_tf'], fine['instrument'], horizon,
                       calendar=meta['calendar_id'])
    consistency = compare_coarse(coarse['bars'], rolled['bars'])
    execution = jsonable(simulate(orders, fine['bars'], fine['instrument'], Costs(**saved['result']['costs']),
        horizon, actions=actions, calendar=meta['calendar_id']))
    by_id = {o['id']: o for o in execution['observations']}
    records = [dict(order_id=o.id, setup_id=o.setup_id, tf=o.tf, model=o.model,
        entry_ticks=o.entry_ticks, stop_ticks=o.stop_ticks, target_ticks=o.target_ticks,
        prior=old[o.id], refined=by_id[o.id]) for o in orders]
    report = dict(case_id=previous['case_id'], strict_teacher_status='UNRESOLVED',
        scope='FROZEN_INDEPENDENT_CANDIDATE_EXECUTION_NOT_PORTFOLIO_OR_TEACHER_OUTCOME',
        detection_rerun=False, detector_input_sha256=previous['input_sha256'],
        execution_input_sha256=digest(args.feed), execution_tf=meta['base_tf'],
        costs=saved['result']['costs'], coverage=fine['coverage'], coarse_consistency=consistency,
        refinement_status='COMPARABLE' if consistency['status']=='CONSISTENT' else 'FEED_COMPARABILITY_UNRESOLVED',
        outcome_counts=dict(Counter(o['refined']['outcome'] for o in records)), records=records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['case_id'], meta['base_tf'], report['refinement_status'],
          json.dumps(report['outcome_counts']), 'missing slots', fine['coverage']['missing_slots'])


if __name__ == '__main__':
    main()

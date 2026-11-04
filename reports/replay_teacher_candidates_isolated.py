"""Independent hypothetical candidate tests; never modify portfolio selection."""
import argparse
from collections import Counter
from datetime import timedelta
import gzip
import json
from pathlib import Path
from bishop.v2.types import Clock, Order, jsonable, stable_id, utc
from reports.audit_teacher_trade_behavior import summarize
from reports.replay_collected_teacher_examples_v2 import digest, forward_outcomes


def independent_orders(saved):
    result = saved['result']
    snapshot = utc(saved['summary']['as_of'])
    stories = {s['id']: s for s in result['stories']}
    seen = set()
    orders, actions = [], []
    excluded = Counter()
    for setup in sorted(result['setups'], key=lambda s: (utc(s['clock']['available_at']), s['id'])):
        if setup['side'] != saved['case']['side']:
            continue
        if setup['status'] != 'ELIGIBLE':
            excluded['INELIGIBLE'] += 1
            continue
        at = utc(setup['clock']['available_at'])
        if at > snapshot:
            raise ValueError('Future setup in frozen trace')
        if stories[setup['story_id']]['details'].get('owner_selection') == 'BLOCKED_COUNTERWEEKLY':
            excluded['BLOCKED_COUNTERWEEKLY'] += 1
            continue
        key = (setup['instrument'], setup['tf'], setup['side'], setup['model'],
               setup['level_id'], at, setup['entry_ticks'], setup['stop_ticks'],
               setup['target_ticks'], setup['order_type'], setup['expires_at'])
        if key in seen:
            excluded['DUPLICATE_CONTEXT'] += 1
            continue
        seen.add(key)
        order = Order(id=stable_id('isolated_teacher_candidate', *key), setup_id=setup['id'],
            instrument=setup['instrument'], tf=setup['tf'], side=setup['side'], model=setup['model'],
            kind=setup['order_type'], clock=Clock(**setup['clock']), entry_ticks=setup['entry_ticks'],
            stop_ticks=setup['stop_ticks'], target_ticks=setup['target_ticks'],
            expires_at=setup['expires_at'], details={'scope': 'INDEPENDENT_HYPOTHETICAL_NOT_PORTFOLIO'})
        orders.append(jsonable(order))
        for event in result['story_events']:
            available = utc(event['clock']['available_at'])
            if (event['reference_id'] == setup['story_id'] and at <= available <= snapshot
                and (event['kind'] in ('STORY_INVALIDATED', 'STORY_DESTINATION_REACHED',
                                      'STORY_CANCELLED', 'STORY_FLIPPED')
                     or event['details'].get('pending_action') == 'CANCEL_DEPENDENT')):
                actions.append(dict(order_id=order.id, kind='CANCEL',
                                    available_at=available.isoformat(), reason=event['kind']))
    return orders, actions, dict(excluded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('traces', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for path in args.traces:
        with gzip.open(path, 'rt') as stream:
            saved = json.load(stream)
        plan = dict(saved['plan'])
        if digest(plan['input_path']) != saved['summary']['input_sha256']:
            raise ValueError('Frozen input changed')
        metadata = json.loads(Path(plan['manifest_path']).read_text())
        plan['as_of'] = saved['summary']['as_of']
        plan['forward_as_of'] = min(utc(metadata['requested_end']),
            utc(plan['as_of']) + timedelta(days=14)).isoformat()
        orders, actions, excluded = independent_orders(saved)
        hypothetical = {**saved, 'result': {**saved['result'], 'orders': orders, 'actions': actions}}
        execution = forward_outcomes(hypothetical['result'], plan, metadata)
        execution['scope'] = 'INDEPENDENT_CANDIDATES_HYPOTHETICAL_NOT_PORTFOLIO_OR_TEACHER_OUTCOME'
        report = summarize(hypothetical, execution)
        report['excluded_context_counts'] = excluded
        report['interpretation'] = ('Each deduplicated eligible same-direction candidate tested independently. '
            'Exposure cap alone bypassed; owner blocks and known story cancellations preserved. '
            'Overlapping alternatives are not a portfolio or independent performance sample. '
            'No future detection or management inferred; strict teacher identity remains unresolved.')
        (args.output / (report['case_id'] + '.json')).write_text(json.dumps(report, indent=2) + '\n')
        for tf in sorted(report['plan_counts_by_timeframe']):
            outcomes = Counter((o['observation'] or {}).get('outcome', 'MISSING_OBSERVATION')
                for p in report['plans'] if p['tf'] == tf for o in p['selected_orders'])
            print(report['case_id'], tf, json.dumps(dict(outcomes)))


if __name__ == '__main__':
    main()

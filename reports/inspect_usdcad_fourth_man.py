"""Inspect the source-clock H1 fourth-man candidates without choosing a winner.

Usage: python reports/inspect_usdcad_fourth_man.py CASE.json.gz OUTPUT.json
Requires the optional inspection dependency: pip install ijson.
Only reads an already completed GitHub replay; does not run the engine.
"""
import gzip

import ijson
from ijson.common import ObjectBuilder
import json
import sys
from collections import Counter
from pathlib import Path


def inspect(path):
    # Stream the large audit; never load unrelated structural diagnostics.
    report = {'plan': {}, 'result': {k: [] for k in ('setups', 'orders', 'observations')}}
    result = report['result']
    result['selection'] = {'rejected': []}
    destinations = {'plan': None, 'result.setups.item': result['setups'],
                    'result.orders.item': result['orders'],
                    'result.observations.item': result['observations'],
                    'result.selection.rejected.item': result['selection']['rejected']}
    builder = None
    capture = None
    with gzip.open(path, 'rb') as stream:
        for prefix, event, value in ijson.parse(stream, use_float=True):
            if builder is None and prefix in destinations and event == 'start_map':
                builder, capture = ObjectBuilder(), prefix
            if builder is not None:
                builder.event(event, value)
                if prefix == capture and event == 'end_map':
                    if capture == 'plan':
                        report['plan'] = builder.value
                    else:
                        destinations[capture].append(builder.value)
                    builder = None
                    capture = None
    candidates = [s for s in result['setups']
                  if s['tf'] == 'H1' and s['side'] == 'BUY'
                  and s['model'] == 'confirmation_standing_extreme'
                  and s['clock']['available_at'] == '2026-06-12T16:00:00+00:00']
    ids = {s['id'] for s in candidates}
    orders = [o for o in result['orders'] if o['setup_id'] in ids]
    order_ids = {o['id'] for o in orders}
    rejected = [r for r in result['selection']['rejected'] if r['setup_id'] in ids]
    plans = Counter((s['entry_ticks'], s['stop_ticks'], s['target_ticks'], s['status'])
                    for s in candidates)
    return {
        'scope': 'SOURCE_CLOCK_CANDIDATES_NOT_TEACHER_ACCEPTANCE',
        'plan': report['plan'],
        'candidate_count': len(candidates),
        'plans': [dict(entry_ticks=e, stop_ticks=s, target_ticks=t, status=status, count=n)
                  for (e, s, t, status), n in sorted(plans.items(), key=lambda p: str(p[0]))],
        'orders': orders,
        'observations': [o for o in result['observations'] if o['id'] in order_ids],
        'rejections': rejected,
        'candidates': candidates,
        'source_caveat': 'Bishop showed H1 standing confirmation then an additional M30 engulfing; '
                         'his displayed final stop is not a standalone H1 stop box.',
    }


if __name__ == '__main__':
    evidence = inspect(sys.argv[1])
    Path(sys.argv[2]).write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({k: evidence[k] for k in ('candidate_count', 'plans', 'orders', 'observations')}, indent=2))

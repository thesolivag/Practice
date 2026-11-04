"""Inventory published range objectives without choosing a target by source price.

Consumes saved Actions traces only. Availability is necessary, not sufficient:
objects here are not asserted standing, same-segment, or teacher-identical.
"""
import argparse
import gzip
import json
from pathlib import Path

from bishop.v2.types import utc


def audit(saved):
    result = saved['result']
    case = saved['case']
    groups = {}
    for setup in result['setups']:
        if setup['side'] != 'SELL' or setup['tf'] != case['tf']:
            continue
        key = (setup['model'], setup['clock']['available_at'], setup['entry_ticks'],
               setup['stop_ticks'], setup['target_ticks'])
        groups.setdefault(key, []).append(setup)
    plans = []
    for key, setups in sorted(groups.items(), key=lambda item: repr(item[0])):
        model, clock, entry, stop, target = key
        published = {}
        for tf, structure in result['diagnostics']['structures'].items():
            versions = {}
            for obj in structure['ranges']:
                if utc(obj['available_at']) <= utc(clock):
                    previous = versions.get(obj['id'])
                    if previous is None or utc(obj['available_at']) >= utc(previous['available_at']):
                        versions[obj['id']] = obj
            published[tf] = [obj for obj in versions.values()
                             if obj['direction'] == 'SELL' and obj['endpoint_ticks'] < entry]
        plans.append(dict(model=model, available_at=clock, entry_ticks=entry,
                          stop_ticks=stop, selected_target_ticks=target,
                          context_count=len(setups),
                          context_destinations=sorted({(s['details'].get('story_destination_ticks'),
                              s['details'].get('story_destination_ref_id')) for s in setups}, key=repr),
                          published_directional_ranges=published))
    return dict(case_id=case['id'], input_sha256=saved['summary']['input_sha256'],
                strict_status='UNRESOLVED',
                scope='Published objectives only; no consumption, segment, or teacher-identity acceptance',
                source_price_used_for_selection=False, plans=plans)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('traces', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for path in args.traces:
        with gzip.open(path, 'rt') as stream:
            report = audit(json.load(stream))
        (args.output / (report['case_id'] + '.json')).write_text(json.dumps(report, indent=2) + '\n')
        print(report['case_id'], len(report['plans']), 'distinct plans audited')


if __name__ == '__main__':
    main()

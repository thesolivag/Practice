"""Report every source-window candidate and raw price differences; never award a match."""
import argparse
from collections import Counter
from decimal import Decimal
import gzip
from hashlib import sha256
import json
from pathlib import Path
from bishop.v2.types import utc


def compare(report, observation):
    case_id = observation['case_id']
    if report['plan']['case_id'] != case_id:
        raise ValueError('Source observation and replay case differ')
    result = report['result']
    if result['instrument']['symbol'] != observation['instrument']:
        raise ValueError('Source observation and replay instrument differ')
    window = observation['source_observed_window']
    start, end = utc(window['start_utc']), utc(window['end_utc'])
    if end <= start:
        raise ValueError('A positive source-observed window is required')
    tick = Decimal(str(result['instrument']['tick_size']))
    unit = Decimal(str(result['instrument']['distance_unit']))
    candidates = [s for s in result['setups'] if s['side'] == observation['side']
                  and start <= utc(s['clock']['available_at']) < end]
    rows = []
    for setup in candidates:
        prices = {name: str(Decimal(setup[name + '_ticks']) * tick)
                  if setup.get(name + '_ticks') is not None else None
                  for name in ('entry', 'stop', 'target')}
        differences = []
        for drawing in observation.get('drawings', []):
            deltas = {name: str((Decimal(prices[name]) - Decimal(str(drawing[name]))) / unit)
                      if prices[name] is not None and drawing.get(name) is not None else None
                      for name in prices}
            differences.append(dict(source_drawing=drawing, signed_difference_units=deltas))
        rows.append(dict(setup_id=setup['id'], tf=setup['tf'], model=setup['model'],
                         available_at=setup['clock']['available_at'], status=setup['status'],
                         expected_tf=setup['tf'] == observation['entry_tf'], prices=prices,
                         differences=differences, story_id=setup['story_id'],
                         evidence_ids=setup.get('evidence_ids', []),
                         unresolved_reasons=setup.get('details', {}).get('unresolved_reasons', []),
                         target_evidence=setup.get('details', {}).get('target_plan'),
                         selected_target_ticks=setup.get('target_ticks')))
    expected = [r for r in rows if r['expected_tf']]
    status = ('NO_SETUP_IN_SOURCE_WINDOW' if not rows else
              'SOURCE_TIMEFRAME_NOT_DETECTED' if not expected else
              'SOURCE_TIMEFRAME_PLANS_UNRESOLVED' if not any(r['status'] == 'ELIGIBLE' for r in expected)
              else 'CANDIDATES_REQUIRE_CAUSAL_SOURCE_COMPARISON')
    return dict(case_id=case_id, scope='SOURCE_WINDOW_CANDIDATES_NOT_TEACHER_ACCEPTANCE',
                teacher_acceptance='NOT_AWARDED', status=status, source_observation=observation,
                candidates=len(rows), expected_tf_candidates=len(expected),
                model_counts=dict(Counter(r['tf'] + ':' + r['model'] for r in rows)),
                unresolved_reasons=dict(Counter(reason for r in expected for reason in r['unresolved_reasons'])),
                rows=rows, limitations=[
                    'Visible chart-tool time is not independently verified as a fill time.',
                    'Every source-side candidate in the declared window is retained, including unresolved plans.',
                    'Differences are bot minus drawing in the declared instrument distance unit; no tolerance is fitted.',
                    'A changed demonstration target is not necessarily the original order target.',
                    'Detection-only replay cannot establish execution or reproduce a discretionary manual exit.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('replay', type=Path)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    raw = args.replay.read_bytes()
    report = json.loads(gzip.decompress(raw) if args.replay.suffix == '.gz' else raw)
    observations = json.loads(args.observations.read_text())['cases']
    selected = [o for o in observations if o['case_id'] == report['plan']['case_id']]
    if len(selected) != 1:
        raise ValueError('One independently source-observed case required')
    result = compare(report, selected[0])
    result['provenance'] = dict(replay_sha256=sha256(raw).hexdigest(),
                                observations_sha256=sha256(args.observations.read_bytes()).hexdigest())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('case_id', 'status', 'candidates', 'expected_tf_candidates')}))


if __name__ == '__main__':
    main()

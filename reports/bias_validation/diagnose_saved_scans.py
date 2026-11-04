"""Inspect archived Actions output without re-running detection or changing expectations."""
import argparse
from collections import Counter
import json
from pathlib import Path
import zipfile
from bishop.bias_snapshot import snapshot


def diagnose(engine):
    view = snapshot(engine)
    stories = {s['id']: s for s in engine['stories']}
    rows = []
    for row in view['rows']:
        grouped = Counter((stories[sid]['side'], stories[sid]['details'].get('scope_type'))
                          for sid in row['story_ids'])
        successors = [e for e in engine['story_events']
                      if e['kind'] == 'OPPOSITE_STORY_CONFIRMED' and e.get('reference_id') in row['story_ids']]
        rows.append(dict(tf=row['tf'], state=row['state'], side=row['side'], basis=row['basis'], structural_context=row['structural_context'],
                         active_by_scope=[dict(side=side, scope=scope, count=count)
                                          for (side, scope), count in sorted(grouped.items())],
                         opposite_confirmed_events_while_still_displayed=len(successors),
                         oldest_active=min((stories[sid]['clock']['available_at'] for sid in row['story_ids']), default=None),
                         newest_active=max((stories[sid]['clock']['available_at'] for sid in row['story_ids']), default=None)))
    return dict(instrument=view['instrument'], as_of=view['as_of'], engine_status=engine['status'],
                scope=engine['scope'], rows=rows,
                interpretation='Multiple surviving structural hypotheses are not an established single current bias. Local versus parent-story ownership needs source-grounded review. No teacher matching claim.',
                source_clock='PDF creation time only; verified setup assessment time remains unknown')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archives', nargs='+')
    p.add_argument('--out', required=True)
    p.add_argument('--actions-run', type=int)
    p.add_argument('--engine-commit', default='unknown')
    a = p.parse_args()
    output = []
    for archive in a.archives:
        with zipfile.ZipFile(archive) as z:
            name = next(n for n in z.namelist() if n.endswith('/engine.json'))
            output.append(diagnose(json.loads(z.read(name))))
    Path(a.out).write_text(json.dumps(dict(actions_run=a.actions_run, engine_commit=a.engine_commit, projection_policy='positive_opposite_retirement_v1',
                                         cases=output), indent=2) + '\n')


if __name__ == '__main__':
    main()

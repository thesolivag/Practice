"""Bias-only scan of a declared local IC Markets snapshot; optional isolated persistence.

Acquisition and this scan are separate so a failed scan can reuse the raw data.
No entry detection, broker execution or Telegram delivery is performed.
"""
import argparse
import json
from dataclasses import replace
from pathlib import Path
from . import settings
from .bias_snapshot import snapshot
from .v2.engine import run
from .v2.simulation import Costs
from .v2.types import utc, stable_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--history-start')
    parser.add_argument('--origin-tfs', nargs='+', choices=('M', 'W', 'D', 'H4'))
    parser.add_argument('--persist', action='store_true')
    parser.add_argument('--structural-only',action='store_true',help='Explicit legacy latest-break diagnostic; does not build confirmed story bias')
    parser.add_argument('--bias-reference-profile', choices=('source_lineage', 'last_pre_touch'), default='last_pre_touch', help='Required owner external-break environment; source_lineage is a source-comparison diagnostic')
    args = parser.parse_args(argv)
    if args.persist and not args.structural_only and args.bias_reference_profile != "last_pre_touch":
        raise ValueError("Source-comparison bias is diagnostic only; persistence requires the external-break model")
    manifest = json.loads(Path(args.manifest).read_text())
    if manifest.get('venue') != 'ICMARKETS':
        raise ValueError('Declared IC Markets input required')
    store = None
    reused = False
    clock = utc(args.as_of).isoformat()
    namespace = ('bias-scan-' if args.structural_only else 'confirmed-bias-scan-') + manifest['symbol']
    values = settings.DEFAULTS
    if args.persist:
        from .runtime import application_store
        store = application_store()
        values = store.get_settings()['values']
    policy = settings.strategy_policy(values)
    if not args.structural_only:policy=replace(policy,bias_reference_profile=args.bias_reference_profile)
    if args.origin_tfs:
        policy = replace(policy, origin_tfs=tuple(args.origin_tfs))
    previous = None
    if store is not None:
        from .paper_store import ident
        with store.lock:
            previous = store._get('paper_runs', ident(namespace, clock))
    if previous:
        expected_scope='BIAS_ONLY' if args.structural_only else 'CONFIRMED_BIAS_ONLY'
        if previous['result'].get('scope')!=expected_scope:
            raise ValueError('Closed hour was recorded under a different bias mode')
        saved_policy=previous['result'].get('policy',{}).get('id')
        if (not args.structural_only or saved_policy is not None) and saved_policy!=policy.id:
            raise ValueError('Closed hour was recorded under a different bias policy')
        from hashlib import sha256
        hashes = previous['result'].get('input', {})
        if (hashes.get('sha256') != sha256(Path(args.input).read_bytes()).hexdigest()
                or hashes.get('manifest') != stable_id('manifest', manifest)):
            raise ValueError('This closed hour was recorded against different input; review source revisions')
        result, reused = previous['result'], True
    else:
        result = run(args.input, manifest, as_of=clock, history_start=args.history_start,
                     policy=policy, costs=Costs(), bias_only=args.structural_only,
                     confirmed_story_bias_only=not args.structural_only)
    # Zero costs are explicit and irrelevant here: this path creates no orders.
    view = snapshot(result)
    directory = Path(args.out)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'engine.json').write_text(json.dumps(result, indent=2) + '\n')
    (directory / 'bias.json').write_text(json.dumps(view, indent=2) + '\n')
    if len(json.dumps(result, separators=(',', ':')).encode()) > 2_000_000:
        raise ValueError('Bias snapshot exceeds the application storage budget; retain artifact and review')
    if store is not None and not reused:
        store.persist_result(result, clock, namespace=namespace)
    print(json.dumps(dict(instrument=view['instrument'], as_of=view['as_of'],
                          status=result['status'], scope=result['scope'], persisted=store is not None, reused=reused)))


if __name__ == '__main__':
    main()

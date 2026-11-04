"""Bounded GitHub Actions profiler; never a backtest success claim."""
import argparse
import cProfile
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import pstats
import signal
import time
from bishop import settings
from bishop.v2.engine import run
from bishop.v2.simulation import Costs
from bishop.v2.types import utc


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    manifests=list(Path(a.inputs).rglob('GBPUSD.csv.manifest.json'))
    if len(manifests)!=1:raise ValueError('One frozen GBPUSD feed required')
    manifest=json.loads(manifests[0].read_text());end=utc(manifest['requested_end'])
    policy=replace(settings.strategy_policy(settings.DEFAULTS),entry_tfs=('H4','H3','H2','H1'),risk_profile='owner_fixed11')
    profiler=cProfile.Profile();started=time.monotonic();state='INCOMPLETE'
    def budget(*_):raise TimeoutError('Diagnostic 180-second CPU sampling budget reached')
    signal.signal(signal.SIGALRM,budget)
    signal.alarm(180)
    try:
        profiler.enable()
        result=run(manifests[0].with_name('GBPUSD.csv.gz'),manifest,as_of=end,
                   history_start=end-timedelta(days=63),scan_start=end-timedelta(days=28),
                   policy=policy,costs=Costs(),max_open_orders=10)
        state='COMPLETE';(out/'engine.json').write_text(json.dumps(result))
    except TimeoutError:
        state='PROFILE_BUDGET_REACHED'
    finally:
        profiler.disable();signal.alarm(0)
        profiler.dump_stats(str(out/'engine.prof'))
        with (out/'profile.txt').open('w') as f:
            pstats.Stats(profiler,stream=f).strip_dirs().sort_stats('cumulative').print_stats(45)
            pstats.Stats(profiler,stream=f).strip_dirs().sort_stats('tottime').print_stats(30)
        (out/'status.json').write_text(json.dumps(dict(status=state,seconds=time.monotonic()-started,
            qualification='Performance diagnostic only; not teacher acceptance or a completed trade backtest.')))
        print((out/'status.json').read_text(),flush=True)

if __name__=='__main__':main()

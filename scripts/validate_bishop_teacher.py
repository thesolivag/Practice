"""Bounded source-anchored diagnostic of deployed Bishop configuration.

Reads frozen local data only. Does not fetch, fit tolerances, award teacher
acceptance, write application DB records, or send notifications.
"""
import argparse
from collections import Counter
from datetime import datetime,timedelta,timezone
import gzip
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def stamp(s):return datetime.fromisoformat(s.replace('Z','+00:00'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def replay(case,source_root,out,seconds):
    from bishop.v2.engine import run
    from bishop.v2.feed import load_feed
    from bishop.v2.types import StrategyPolicy
    from bishop.v2.simulation import Costs
    pair=case['instrument'];directory=source_root/'data/primary_missing_inputs'/pair
    status=json.loads((directory/'status.json').read_text())
    data=source_root/status['path'];manifest_path=source_root/status['manifest']
    metadata=json.loads(manifest_path.read_text())
    if digest(data)!=metadata['sha256']:raise ValueError('Frozen source CSV hash mismatch')
    if metadata['symbol']!=pair or metadata['venue']!='ICMARKETS' or metadata['base_tf']!='H1':raise ValueError('Wrong input instrument/provider/resolution')
    # Source-observed day was fixed before any engine output. Allow one further
    # day for diagnostic execution; neither clock is asserted to be a fill time.
    start=stamp(case['source_observed_window']['start_utc']);end=stamp(case['source_observed_window']['end_utc'])
    clock=end+timedelta(days=1);history_start=clock-timedelta(days=35)
    since=clock-timedelta(days=7)
    policy=StrategyPolicy(source_profile='bishop_confirmation',entry_tfs=('H4','H3','H2','H1'))
    plan={'case_id':case['case_id'],'pair':pair,'side':case['side'],'entry_tf':case['entry_tf'],
        'source_window':[start.isoformat(),end.isoformat()],'as_of':clock.isoformat(),
        'history_start':history_start.isoformat(),'scan_start':since.isoformat(),
        'policy_id':policy.id,'profile':'bishop_confirmation','entry_timeframes':list(policy.entry_tfs),
        'compact_story_diagnostics':True,'costs':'EXPLICIT_ZERO_COST','time_budget_seconds':seconds,
        'input_sha256':digest(data),'manifest_sha256':digest(manifest_path),
        'source_expectations_sha256':digest(out/'source_cases.json'),
        'engine_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'bishop/v2').glob('*.py'))},
        'source_feed':'FOREXCOM TradingView','replay_feed':'IC Markets cTrader',
        'acceptance_policy':'NO_AUTOMATIC_ACCEPTANCE; raw alternate-feed diagnostic; no tolerance fitting'}
    write(out/(case['case_id']+'.plan.json'),plan)
    started=time.monotonic()
    def timeout(*args):raise TimeoutError('Bounded teacher diagnostic reached time budget')
    previous=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,seconds)
    try:
        feed=load_feed(data,metadata,clock,history_start)
        result=run(feed,as_of=clock,history_start=history_start,scan_start=since,policy=policy,costs=Costs(),compact_story_diagnostics=True)
        candidates=[s for s in result['setups'] if s['side']==case['side'] and s['tf']==case['entry_tf']
                    and start<=stamp(s['clock']['available_at'])<end]
        orders={o['setup_id']:o for o in result['orders']}
        observations={o['id']:o for o in result['observations']}
        tick=float(metadata['tick_size']);unit=float(metadata['distance_unit'])
        comparisons=[]
        for c in candidates:
            prices={name:None if c.get(name+'_ticks') is None else c[name+'_ticks']*tick for name in ('entry','stop','target')}
            differences=[]
            for drawing in case['drawings']:
                differences.append({'source_pts_seconds':drawing['source_pts_seconds'],'source_role':drawing['role'],
                    'difference_units':{k:None if drawing.get(k) is None or prices[k] is None else round((prices[k]-drawing[k])/unit,6) for k in prices}})
            order=orders.get(c['id'])
            comparisons.append({'setup':c,'prices':prices,'raw_differences_to_every_source_drawing':differences,
                'selected_order':order,'paper_observation':observations.get(order['id']) if order else None})
        # These counts describe engine evidence, not proof it is the source event.
        def inside(obj):return start<=stamp(obj['clock']['available_at'])<end
        relevant_stories=[s for s in result['stories'] if s['side']==case['side'] and inside(s)]
        summary={**plan,'execution_status':'COMPLETED_DIAGNOSTIC','seconds':round(time.monotonic()-started,3),
            'engine_status':result['status'],'coverage':result['coverage'],
            'engine_summary':result['summary'],'source_window_stories':relevant_stories,
            'same_side_tf_window_candidate_count':len(candidates),
            'candidate_models':dict(Counter(c['model'] for c in candidates)),
            'candidate_statuses':dict(Counter(c['status'] for c in candidates)),
            'selected_same_side_tf_window_orders':sum(c['id'] in orders for c in candidates),
            'source_window_story_events':dict(Counter(e['kind'] for e in result['story_events'] if e.get('side')==case['side'] and inside(e))),
            'teacher_acceptance':'NOT_ESTABLISHED','numeric_tolerance':None,
            'blocking_facts':['Source-feed/candle alignment is unverified.','Source drawing anchors are not proven setup/fill clocks.','No unique primary-source event IDs or independently established numeric acceptance tolerances.'],
            'comparisons':comparisons}
        raw={'result':result,'source_case':case,'plan':plan}
        (out/(case['case_id']+'.engine.json.gz')).write_bytes(gzip.compress(json.dumps(raw,allow_nan=False).encode(),mtime=0))
    except TimeoutError as exc:
        summary={**plan,'execution_status':'TIMEOUT_NOT_A_STRATEGY_RESULT','seconds':round(time.monotonic()-started,3),'teacher_acceptance':'NOT_ESTABLISHED','reason':str(exc)}
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    write(out/(case['case_id']+'.summary.json'),summary)
    print(json.dumps({k:summary.get(k) for k in ('case_id','execution_status','seconds','same_side_tf_window_candidate_count','selected_same_side_tf_window_orders','teacher_acceptance')}),flush=True)
    return summary


def prefix_check(source_root,out,seconds):
    """One fixed-history earlier snapshot; no warmup shift can explain changes."""
    from bishop.v2.engine import run
    from bishop.v2.feed import load_feed
    from bishop.v2.types import StrategyPolicy
    from bishop.v2.simulation import Costs
    case=json.loads((out/'source_cases.json').read_text())['cases'][0]
    final=json.loads(gzip.decompress((out/(case['case_id']+'.engine.json.gz')).read_bytes()))
    plan=final['plan'];cutoff=stamp(case['source_observed_window']['end_utc'])
    status=json.loads((source_root/'data/primary_missing_inputs'/case['instrument']/'status.json').read_text())
    metadata=json.loads((source_root/status['manifest']).read_text())
    def timeout(*args):raise TimeoutError('Bounded prefix check')
    previous=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,seconds)
    started=time.monotonic()
    try:
        feed=load_feed(source_root/status['path'],metadata,cutoff,plan['history_start'])
        result=run(feed,as_of=cutoff,history_start=plan['history_start'],scan_start=plan['scan_start'],
            policy=StrategyPolicy(source_profile='bishop_confirmation',entry_tfs=('H4','H3','H2','H1')),
            costs=Costs(),compact_story_diagnostics=True)
        collections={}
        for key in ('setups','orders','execution_events'):
            expected=[x for x in final['result'][key] if stamp(x['clock']['available_at'])<=cutoff]
            early=result[key]
            canonical=lambda rows:json.dumps(rows,sort_keys=True,separators=(',',':'))
            collections[key]={'earlier_count':len(early),'later_published_before_cutoff_count':len(expected),'identical':canonical(early)==canonical(expected),
                'earlier_sha256':hashlib.sha256(canonical(early).encode()).hexdigest(),
                'later_sha256':hashlib.sha256(canonical(expected).encode()).hexdigest()}
        report={'case_id':case['case_id'],'cutoff':cutoff.isoformat(),'fixed_history_start':plan['history_start'],
            'scan_start':plan['scan_start'],'execution_status':'COMPLETED_DIAGNOSTIC','collections':collections,
            'all_compared_collections_identical':all(v['identical'] for v in collections.values()),
            'limitations':['One fixed-history prefix only; this does not establish teacher agreement or eliminate every possible look-ahead bug.']}
    except TimeoutError:
        report={'case_id':case['case_id'],'execution_status':'TIMEOUT_NOT_A_STRATEGY_RESULT'}
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    report['seconds']=round(time.monotonic()-started,3)
    write(out/'prefix_check.json',report)
    print(json.dumps(report),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/teacher_validation/2026-11-05')
    parser.add_argument('--seconds',type=int,default=30)
    parser.add_argument('--prefix-only',action='store_true')
    args=parser.parse_args()
    if args.prefix_only:
        prefix_check(args.source_root,args.output,args.seconds);return
    cases=json.loads((args.output/'source_cases.json').read_text())['cases']
    results=[replay(case,args.source_root,args.output,args.seconds) for case in cases]
    write(args.output/'summary.json',{'scope':'THREE_CASE_DEPLOYED_CONFIGURATION_PILOT','inventory_episodes':17,
        'source_cases':len(cases),'completed_replays':sum(r['execution_status']=='COMPLETED_DIAGNOSTIC' for r in results),
        'teacher_acceptance_rate':None,'reason':'No exact teacher-acceptance denominator is established.',
        'cases':[{k:r.get(k) for k in ('case_id','execution_status','seconds','same_side_tf_window_candidate_count','selected_same_side_tf_window_orders','teacher_acceptance')} for r in results]})


if __name__=='__main__':main()

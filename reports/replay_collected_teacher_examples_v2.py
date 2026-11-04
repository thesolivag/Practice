"""Offline all-fixture inventory and bounded replay of explicitly collected inputs.

No acquisition, network, fixture mutation, fitting or implicit symbol substitution.
Dates choose exploratory windows before outcomes; they are not teacher fill clocks.
The time budget covers detector/forward execution, excluding planning and final hash checks.
"""
import argparse
from collections import Counter
from datetime import timedelta
from decimal import Decimal
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import signal
import time

from bishop.v2.engine import run
from bishop.v2.types import StrategyPolicy, Clock, Order, jsonable, utc
from bishop.v2.simulation import Costs, simulate
from bishop.v2.feed import load_feed
from bishop.replay import evaluate
from bishop.runner import replay_observations

# Independently read snapshot minutes, not setup/fill availability. Kept literal
# here so collected-input replay has no dependency on another runner's datasets.
SNAPSHOTS = {
 'pdf-p08-eurgbp-buy-1':'2026-07-23T18:08:00Z',
 # PDF p22 LEFT Saxo header: Jul13 2026 06:24 UTC+1. Observation ceiling only.
 'pdf-p22-xagusd-sell-1':'2026-07-13T05:24:00Z',
 'pdf-p37-eurgbp-sell-1':'2026-06-01T16:08:00Z',
 'pdf-p54-eurgbp-buy-1':'2026-05-14T19:09:00Z',
 'pdf-p15-usdcad-sell-1':'2026-07-16T13:35:00Z',
 'pdf-p19-gbpjpy-buy-1':'2026-07-15T17:26:00Z',
 'pdf-p19-gbpjpy-buy-2':'2026-07-15T17:26:00Z',
 'pdf-p23-usdchf-sell-1':'2026-07-10T06:43:00Z',
 'pdf-p23-usdchf-sell-2':'2026-07-09T14:41:00Z',
 'pdf-p35-gbpjpy-buy-1':'2026-06-05T12:13:00Z',
 'pdf-p60-gbpaud-sell-1':'2026-05-12T08:52:00Z',
}

# Previously declared source-review search windows; still exploratory, never
# teacher availability/fill clocks. Preserve Friday coverage across weekends.
REVIEW_SCAN_STARTS = {
 'pdf-p08-eurgbp-buy-1':'2026-07-22T00:00:00Z',
 # p21/p22 visible Jul9/10 formation; exploration only, not a fill window.
 'pdf-p22-xagusd-sell-1':'2026-07-09T00:00:00Z',
 'pdf-p37-eurgbp-sell-1':'2026-05-29T00:00:00Z',
 'pdf-p54-eurgbp-buy-1':'2026-05-12T00:00:00Z',
 'pdf-p15-usdcad-sell-1':'2026-07-14T00:00:00Z',
 'pdf-p19-gbpjpy-buy-1':'2026-07-13T00:00:00Z',
 'pdf-p19-gbpjpy-buy-2':'2026-07-13T00:00:00Z',
 'pdf-p23-usdchf-sell-1':'2026-07-08T00:00:00Z',
 'pdf-p23-usdchf-sell-2':'2026-07-08T00:00:00Z',
 'pdf-p35-gbpjpy-buy-1':'2026-06-03T00:00:00Z',
 'pdf-p60-gbpaud-sell-1':'2026-05-08T00:00:00Z',
}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def required_base(tf):
    if tf.startswith('H') and tf[1:].isdigit():
        return 'H1'
    if tf.startswith('M') and tf[1:].isdigit() and int(tf[1:]) % 5 == 0:
        return 'M5'
    return None


def inventory_manifests(directory):
    items=[]
    for path in sorted(Path(directory).rglob('*.csv.manifest.json')):
        data=path.with_name(path.name.removesuffix('.manifest.json')+'.gz')
        try:
            metadata=json.loads(path.read_text())
            items.append({'path':str(data),'manifest_path':str(path),'metadata':metadata,
                          'manifest_sha256':digest(path)})
        except (ValueError,OSError) as exc:
            items.append({'manifest_path':str(path),'error':type(exc).__name__})
    return items


def plan_case(case, inputs, annotation=None):
    plan={'id':case['id'],'pair':case['pair'],'tf':case['tf'],'side':case['side'],
          'strict_status':'UNRESOLVED','base_tf':required_base(case['tf']),
          'clock_kind':'UNRESOLVED','status':'PLANNED'}
    stamp=case.get('chart_snapshot_date')
    if not stamp and annotation is None:
        return dict(plan,status='UNRESOLVED_DATE')
    if not stamp:
        if annotation.get('example_id')!=case['id'] or annotation.get('pair')!=case['pair']:
            return dict(plan,status='UNRESOLVED_CLOCK_ANNOTATION')
        try:
            lo,hi=map(utc,annotation['candidate_event_search'])
            if lo>=hi:raise ValueError('empty exploration')
            stamp=lo.date().isoformat()
        except (ValueError,TypeError,KeyError):
            return dict(plan,status='UNRESOLVED_CLOCK_ANNOTATION')
    try:
        day=utc(stamp+'T00:00:00Z')
    except (ValueError,TypeError):
        return dict(plan,status='UNRESOLVED_DATE')
    precise=SNAPSHOTS.get(case['id'])
    as_of=utc(precise) if precise else day+timedelta(days=1)
    plan.update(as_of=as_of.isoformat(),history_start=(day-timedelta(days=35)).isoformat(),
                scan_start=utc(REVIEW_SCAN_STARTS[case['id']]).isoformat() if case['id'] in REVIEW_SCAN_STARTS else (day-timedelta(days=2)).isoformat(),
                clock_kind='SOURCE_SNAPSHOT_MINUTE_NOT_SETUP_CLOCK' if precise else
                'EXPLORATORY_END_OF_SNAPSHOT_DATE_NOT_TEACHER_CLOCK')
    if not case.get('chart_snapshot_date'):
        plan.update(as_of=hi.isoformat(),scan_start=lo.isoformat(),
                    clock_kind='ANNOTATED_EXPLORATORY_EVENT_SEARCH_NOT_SETUP_OR_FILL_CLOCK',
                    clock_annotation=annotation)
        as_of=hi
    if plan['base_tf'] is None:
        return dict(plan,status='UNSUPPORTED_RESOLUTION')
    matches=[x for x in inputs if not x.get('error') and
             x['metadata'].get('symbol')==case['pair'] and
             case['id'] in x['metadata'].get('case_ids',()) and
             x['metadata'].get('base_tf') in (plan['base_tf'],'M1')]
    if not matches:
        return dict(plan,status='MISSING_EXPLICIT_MATCHING_INPUT')
    valid=[]; problems=[]
    required=('tick_size','distance_unit','calendar_id','anchor_id','calendar_version',
              'asset_class','price_basis','source_id','venue','sha256','requested_start','requested_end')
    for item in matches:
        m=item['metadata']
        if any(not m.get(k) for k in required):
            problems.append('UNRESOLVED_METADATA');continue
        if m['venue']!='ICMARKETS' or m['price_basis']!='BID':
            problems.append('UNRESOLVED_PROVIDER');continue
        if (m.get('surrogate_market') or m.get('market_surrogate') or m.get('is_surrogate') or
                'SURROGATE' in str(m.get('symbol_mapping_status','')).upper() or
                'SURROGATE' in str(m.get('asset_class','')).upper()):
            problems.append('SURROGATE_MARKET_UNRESOLVED');continue
        if (m['anchor_id'] not in ('ny17_wall_v2','utc_epoch_v1') or
            m['calendar_id'] not in ('fx_ny_v1','24x7_utc_v1','explicit_intervals_v1') or
            m.get('unresolved_broker_schedule') or str(m['calendar_version']).upper().startswith('UNRESOLVED') or
            (m['calendar_id']=='explicit_intervals_v1' and not m.get('calendar',{}).get('open_intervals'))):
            problems.append('UNRESOLVED_CALENDAR');continue
        conflict_count=m.get('calendar_conflict_nonzero_or_unknown_volume_rows',0)
        if conflict_count:
            withheld=m.get('calendar_conflict_required_missing_slots',[])
            if not (m.get('calendar_conflicts_handled_as_missing_observations') is True
                    and m.get('calendar_observation_semantics')=='REQUIRED_OBSERVATIONS_WITH_DISPUTED_SLOTS_HYPOTHESIS'
                    and m.get('calendar',{}).get('disputed_slots_are_tradable') is False
                    and isinstance(withheld,list) and len(withheld)==conflict_count
                    and len(set(withheld))==conflict_count):
                problems.append('OBSERVED_CALENDAR_CONFLICT_UNRESOLVED');continue
        if m.get('surrogate_market') or m.get('market_surrogate') or m.get('is_surrogate'):
            problems.append('SURROGATE_MARKET_UNRESOLVED');continue
        try:
            if utc(m['requested_start'])>utc(plan['history_start']) or utc(m['requested_end'])<as_of:
                problems.append('INSUFFICIENT_DECLARED_WINDOW');continue
            if not Path(item['path']).exists():
                problems.append('MISSING_DATA_FILE');continue
            if digest(item['path']) != m['sha256']:
                problems.append('INPUT_HASH_MISMATCH');continue
        except (OSError,ValueError,TypeError):
            problems.append('INVALID_INPUT_METADATA');continue
        valid.append(item)
    if not valid:
        return dict(plan,status=problems[0],input_problems=sorted(set(problems)))
    # Deterministic before outcomes: tightest declared window, then path. Never
    # choose a feed because one output resembles a printed source price.
    chosen=min(valid,key=lambda x:(x['metadata']['base_tf']!=plan['base_tf'],utc(x['metadata']['requested_end'])-utc(x['metadata']['requested_start']),x['manifest_path']))
    return dict(plan,input_path=chosen['path'],manifest_path=chosen['manifest_path'],
                requested_base_tf=plan['base_tf'],base_tf=chosen['metadata']['base_tf'],
                input_sha256=chosen['metadata']['sha256'],manifest_sha256=chosen['manifest_sha256'],
                source_equivalence=chosen['metadata'].get('source_equivalence','ALTERNATE_FEED_UNVERIFIED'),
                input_alternatives=len(valid),selection_policy='required_resolution_then_finer_M1_then_tightest_declared_window_path')


def diagnostic_groups(result, case):
    tick=Decimal(result['instrument']['tick_size']);groups=[]
    for s in result['setups']:
        if s['side']!=case['side'] or s['tf']!=case['tf']:continue
        prices={k:str(Decimal(s[k+'_ticks'])*tick) if s[k+'_ticks'] is not None else None
                for k in ('entry','stop','target')}
        differences={k:str(Decimal(v)-Decimal(str(case[k]))) if v is not None and case.get(k) is not None else None
                     for k,v in prices.items()}
        groups.append({'setup_id':s['id'],'available_at':s['clock']['available_at'],'model':s['model'],
                       'status':s['status'],'story_id':s['story_id'],'level_id':s['level_id'],'evidence_ids':s['evidence_ids'],
                       'prices':prices,'price_differences_from_printed_plan':differences,'risk_details':s['details']})
    return groups


def forward_outcomes(result, plan, metadata):
    """Only extend execution of the exact frozen detector selection, never detect."""
    label='FROZEN_DETECTOR_ORDERS_HYPOTHETICAL_NOT_TEACHER_OUTCOME'
    snapshot=utc(plan['as_of']); horizon=utc(plan['forward_as_of'])
    orders=tuple(Order(**{**o,'clock':Clock(**o['clock'])}) for o in result['orders'])
    if any(o.available_at>snapshot for o in orders):
        raise ValueError('future order in frozen detector selection')
    actions=tuple(a for a in result.get('actions',())
                  if utc(a.get('available_at',a.get('at')))<=snapshot)
    base=dict(scope=label,as_of=horizon.isoformat(),snapshot_as_of=snapshot.isoformat(),
              frozen_order_ids=[o.id for o in orders],known_actions=actions,
              future_detector_calls=0,post_snapshot_management_inferred=False)
    if horizon<=snapshot:return dict(base,status='FORWARD_DISABLED',observations=result['observations'])
    if not orders:return dict(base,status='NO_FROZEN_ORDERS',observations=[])
    feed=load_feed(plan['input_path'],metadata,horizon,plan['history_start'])
    if not any(b.end>snapshot for b in feed['bars']):
        return dict(base,status='NO_POST_SNAPSHOT_DATA',coverage=feed['coverage'],
                    observations=result['observations'])
    execution=simulate(orders,feed['bars'],feed['instrument'],Costs(**result['costs']),horizon,
                       actions=actions,calendar=metadata.get('calendar',metadata['calendar_id']))
    return jsonable(dict(base,status='FORWARD_INPUT_GAPS_CENSORED' if feed['coverage'].get('missing_slots') else
                        'SIMULATED_FROZEN_ORDERS',coverage=feed['coverage'],
                        outcome_counts=dict(Counter(o['outcome'] for o in execution['observations'])),**execution))


class ReplayBudgetExceeded(TimeoutError):
    pass


def _alarm(*_):
    raise ReplayBudgetExceeded('invocation diagnostic time budget exceeded')


def check_frozen(expected):
    for path, value in expected.items():
        if digest(path)!=value:
            raise RuntimeError('frozen replay input/implementation changed: '+str(path))


def execute(fixtures, data_dir, outdir, *, case_ids=(), time_budget_seconds=60, clock_annotations=None, forward_days=14, source_profile="bishop_confirmation"):
    if not isinstance(time_budget_seconds,(int,float)) or isinstance(time_budget_seconds,bool) or not math.isfinite(time_budget_seconds) or time_budget_seconds<0:
        raise ValueError('nonnegative invocation time budget required')
    if type(forward_days) is not int or forward_days<0:raise ValueError('nonnegative integer forward_days required')
    if source_profile not in ('bishop_confirmation','owner_aggressive'):
        raise ValueError('declared confirmation or direct source_profile required')
    fixture_path=Path(fixtures);document=json.loads(fixture_path.read_text())
    cases=document['examples']
    if not cases:raise ValueError('nonempty source inventory required')
    known={c['id'] for c in cases}
    if set(case_ids)-known:raise ValueError('unknown case ID')
    selected=set(case_ids) if case_ids else known
    inputs=inventory_manifests(data_dir)
    annotations={}
    if clock_annotations is not None:
        annotation_doc=json.loads(Path(clock_annotations).read_text())
        annotations={a['example_id']:a for a in annotation_doc['annotations']}
    plans=[plan_case(c,inputs,annotations.get(c['id'])) for c in cases]
    for plan in plans:
        if plan.get('input_path'):
            metadata=json.loads(Path(plan['manifest_path']).read_text())
            plan['forward_as_of']=min(utc(metadata['requested_end']),utc(plan['as_of'])+timedelta(days=forward_days)).isoformat()
            plan['forward_days']=forward_days
    expected={fixture_path:digest(fixture_path)}
    if clock_annotations is not None:expected[Path(clock_annotations)]=digest(clock_annotations)
    for p in sorted(Path('bishop/v2').glob('*.py'))+[Path('bishop/runner.py'),Path('bishop/replay.py'),Path(__file__)]:
        expected[p]=digest(p)
    for plan in plans:
        if plan.get('manifest_path'):
            expected[Path(plan['manifest_path'])]=plan['manifest_sha256']
            expected[Path(plan['input_path'])]=plan['input_sha256']
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    declaration={'scope':'ALTERNATE_FEED_OFFLINE_DIAGNOSTIC_NOT_ACCEPTANCE','fixture_sha256':expected[fixture_path],
                 'source_profile':source_profile,'risk_profile':'context_liquidity',
                 'time_budget_seconds':time_budget_seconds,'budget_scope':'DETECTOR_AND_FORWARD_LOOP_EXCLUDES_PLANNING_AND_FINAL_HASH_CHECKS',
                 'window_policy':'35day_context_source_review_scan_or_2day_snapshot_scan_NOT_VERIFIED_SETUP_CLOCK',
                 'cost_hypothesis':'EXPLICIT_ZERO_COST_DIAGNOSTIC','plans':plans,
                 'implementation_sha256':sha256(''.join(str(k)+':'+v+'\n' for k,v in expected.items() if k.suffix=='.py').encode()).hexdigest()}
    # Publish the entire denominator and declared windows BEFORE any engine call.
    (out/'run_plan.json').write_text(json.dumps(declaration,indent=2,allow_nan=False)+'\n')
    started=time.monotonic();rows=[]
    byid={c['id']:c for c in cases}
    for plan in plans:
        row=dict(plan)
        if plan['id'] not in selected:row['status']='NOT_REQUESTED'
        elif plan['status']=='PLANNED':
            remaining=time_budget_seconds-(time.monotonic()-started) if time_budget_seconds else None
            if remaining is not None and remaining<=0:
                row['status']='NOT_RUN_TIME_BUDGET'
            else:
                check_frozen(expected)
                m=json.loads(Path(plan['manifest_path']).read_text())
                entry_tfs=tuple(dict.fromkeys(('H4','H2','H1',plan['tf'])))
                policy=StrategyPolicy(source_profile=source_profile,risk_profile='context_liquidity',
                                      target_profile='nearest_erl',entry_tfs=entry_tfs,origin_tfs=('W','D','H4'))
                previous=None
                try:
                    if remaining is not None:
                        previous=signal.signal(signal.SIGALRM,_alarm);signal.setitimer(signal.ITIMER_REAL,remaining)
                    result=run(plan['input_path'],m,as_of=plan['as_of'],history_start=plan['history_start'],
                               scan_start=plan['scan_start'],policy=policy,costs=Costs(),max_open_orders=10)
                    check_frozen(expected)
                    if m.get('calendar_conflicts_handled_as_missing_observations'):
                        missing={utc(t) for t in result['coverage']['base'].get('missing',[])}
                        disputed={utc(t) for t in m.get('calendar_conflict_required_missing_slots',[])
                                  if utc(plan['history_start'])<=utc(t)<utc(plan['as_of'])}
                        if not disputed.issubset(missing):
                            raise ValueError('disputed observations must remain explicit input gaps')
                    forward=forward_outcomes(result,plan,m)
                    check_frozen(expected)
                    groups=diagnostic_groups(result,byid[plan['id']])
                    strict=evaluate({'schema_version':document['schema_version'],'examples':[byid[plan['id']]]},replay_observations(result))
                    gaps=result['coverage']['base'].get('missing_slots',0)
                    row.update(status='INPUT_GAP_DIAGNOSTIC' if gaps else 'COMPUTED_DIAGNOSTIC',summary=result['summary'],
                               strict_status=strict['status'],coverage=result['coverage'],plan_group_count=len(groups),
                               forward_status=forward['status'])
                    report=dict(scope=declaration['scope'],plan=plan,
                                source_plan={k:byid[plan['id']].get(k) for k in ('pair','tf','side','entry','stop','target','trigger','source_feed','source_execution_status')},
                                fixture_sha256=expected[fixture_path],
                                implementation_sha256=declaration['implementation_sha256'],policy=result['policy'],
                                costs=result['costs'],summary=result['summary'],coverage=result['coverage'],
                                strict_replay=strict,plan_groups=groups,forward_execution=forward,
                                story_contexts=result['stories'],
                                story_lifecycle_events=result.get('story_events',[]),
                                implementation_diagnostics={
                                    'setup_models':dict(Counter(s['model'] for s in result['setups'])),
                                    'order_models':dict(Counter(o['model'] for o in result['orders'])),
                                    'selection_reasons':dict(Counter(r['reason'] for r in result['selection']['rejected'])),
                                    'retired_direct_reasons':dict(Counter(r.get('reason') for r in result['support'] if r.get('route')=='direct_entry_episode'))},limitations=[
                                    'Snapshot clocks and exploratory windows are not verified teacher setup/fill clocks.',
                                    'IC Markets is alternate data; source feed equivalence is unproved.',
                                    'Zero cost hypothesis is not a profitability claim.',
                                    'No nearest-price candidate is promoted to source acceptance.',
                                    'Withheld disputed session quotes are explicit gaps; conservative context retirement is a research policy, not a Bishop trade rule.',
                                    'Bounded35day detector history may not initialize the source major story.',
                                    'Forward results extend frozen selected orders only; no post-snapshot management is inferred.'])
                    path=out/(plan['id']+'.json.gz');path.write_bytes(gzip.compress((json.dumps(report,allow_nan=False)+'\n').encode(),mtime=0))
                    row['report']=str(path);row['report_sha256']=digest(path)
                except ReplayBudgetExceeded:
                    row['status']='ABORTED_RUNTIME'
                except (ValueError,OSError) as exc:
                    row.update(status='UNRESOLVED_INPUT_OR_CALENDAR',error_type=type(exc).__name__,reason=str(exc))
                finally:
                    if previous is not None:
                        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
        rows.append(row)
        # Persist progress with the full denominator, including not yet evaluated rows.
        pending=[dict(p,status='PENDING',strict_status='UNRESOLVED') for p in plans[len(rows):]]
        (out/'index.json').write_text(json.dumps(dict(scope=declaration['scope'],fixture_count=len(cases),
            strict_counts={s:sum(r.get('strict_status','UNRESOLVED')==s for r in rows+pending) for s in ('PASS','FAIL','UNRESOLVED')},
            results=rows+pending),indent=2,allow_nan=False)+'\n')
    check_frozen(expected)
    return json.loads((out/'index.json').read_text())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clock-annotations',help='explicit opt-in exploratory source-clock sidecar; never fixture promotion')
    parser.add_argument('--source-profile',choices=('bishop_confirmation','owner_aggressive'),default='bishop_confirmation')
    parser.add_argument('--forward-days',type=int,default=14,help='outcome-only horizon of frozen detector orders (0 disables)')
    parser.add_argument('--case',action='append',default=[])
    parser.add_argument('--fixtures',default='tests/bishop_examples.json')
    parser.add_argument('--data-dir',default='data/teacher_icmarkets')
    parser.add_argument('--outdir',default='reports/teacher_replay_collected_v2')
    parser.add_argument('--time-budget-seconds',type=float,default=60,help='Detector/forward loop budget; excludes planning and final hash checks (0 disables)')
    args=parser.parse_args(argv)
    execute(args.fixtures,args.data_dir,args.outdir,case_ids=args.case,time_budget_seconds=args.time_budget_seconds,clock_annotations=args.clock_annotations,forward_days=args.forward_days,source_profile=args.source_profile)
    return 0


if __name__=='__main__':
    raise SystemExit(main())

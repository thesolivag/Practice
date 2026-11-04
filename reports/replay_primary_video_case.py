"""Bounded first-person video replay, separate from student-PDF diagnostics.

Fixed source-visible exploratory window; no outcome-based search, fitted prices,
fixture promotion, broker access or inferred teacher fill times.
"""
import gzip
import cProfile
import pstats
import io
import time
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import signal

import bishop.v2.engine as replay_engine
from bishop.v2.engine import run
from bishop.v2.simulation import Costs
from bishop.v2.types import StrategyPolicy

JOBS={
 'video-t2-eurgbp-sell':('EURGBP','collect_d4c44fb0ef3d2811737e1571','40078316839'),
 'video-t3-audchf-buy-loss':('AUDCHF',None,None),
 'video-t3-nzdchf-buy-loss':('NZDCHF',None,None),
 'video-t3-usdjpy-buy-manual-exit':('USDJPY',None,None),
 'video-t3-gbpcad-buy':('GBPCAD','collect_301365c74eab831b3e361482','40078316839'),
 'video-t3-gbpusd-sell-mixed-accounts':('GBPUSD','collect_0401ebc6fede452bfc611a77','40078316839'),
 'video-t3-usdchf-buy':('USDCHF','collect_f96b706592fd20ebcac40e90','40098655754'),
 'video-t3-usdcad-buy-open':('USDCAD','collect_c058fc002a50237cd6d2dbb0','40098655754'),
}
FIXTURES=Path('tests/bishop_video_breakdown_cases.json')
OUT=Path('reports/primary_video_replay')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=tuple(JOBS),default='video-t3-gbpcad-buy')
    parser.add_argument('--input-status',type=Path,help='Frozen H1 collection status for a newly supplied primary input')
    parser.add_argument('--nested-m30',action='store_true',help='Explicit USDCAD nested H1/M30 detection using frozen real M1')
    parser.add_argument('--detection-status',type=Path,default=Path('data/usdcad_execution_m1/status.json'))
    parser.add_argument('--detection-only',action='store_true',help='Report detected plans without selection or execution')
    parser.add_argument('--target-profile',choices=('nearest_erl','context_objective','context_h4_kl'),default='nearest_erl',
                        help='Explicit target policy; context_objective is partial experimental coverage')
    parser.add_argument('--full-context',action='store_true',help='Use all frozen history, without changing scan clocks or source expectations')
    parser.add_argument('--profile',action='store_true',help='60-second diagnostic CPU profile; not a completed replay')
    parser.add_argument('--profile-entries',action='store_true',help='Profile entry stage for 60 seconds after preprocessing')
    parser.add_argument('--profile-stories',action='store_true',help='Profile story analysis for 60 seconds after structure preprocessing')
    parser.add_argument('--execution-status',type=Path,help='Frozen finer execution collection status; detection feed is unchanged')
    parser.add_argument('--quote-evidence',type=Path,help='Validated raw quote evidence plus H1 no-touch bounds for execution only')
    args=parser.parse_args(argv);CASE_ID=args.case
    pair,stem,input_run=JOBS[CASE_ID]
    if args.input_status:
        supplied=json.loads(args.input_status.read_text())
        if supplied.get('status')!='RAW_COLLECTED_UNVALIDATED':raise ValueError('successful frozen H1 input required')
        MANIFEST=Path(supplied['manifest']);DATA=Path(supplied['path'])
    else:
        if stem is None:raise ValueError('This primary case requires --input-status')
        MANIFEST=Path('data/teacher_icmarkets_runs')/input_run/'data/teacher_icmarkets'/(stem+'.csv.manifest.json')
        DATA=MANIFEST.with_name(stem+'.csv.gz')
    document=json.loads(FIXTURES.read_text())
    cases=[c for c in document['cases'] if c['id']==CASE_ID]
    if len(cases)!=1:raise ValueError('one explicit primary video case required')
    case=cases[0]
    if case.get('provenance')!='PRIMARY_MENTOR_VIDEO' or case.get('participation') not in ('PERSONAL_TRADE_NARRATED','PERSONAL_MULTI_ACCOUNT_TRADE'):
        raise ValueError('firsthand narrated personal trade required')
    videos=json.loads(Path('knowledge-base/study/bishop_frame_manifest.json').read_text())['videos']
    if not any(v['slug']==case['source']['slug'] and v['sha256']==case['source']['sha256'] for v in videos):
        raise ValueError('source video must match frozen source manifest')
    metadata=json.loads(MANIFEST.read_text())
    if metadata['symbol']!=pair or metadata['venue']!='ICMARKETS' or metadata['base_tf']!='H1':
        raise ValueError('declared IC input instrument required')
    if sha256(DATA.read_bytes()).hexdigest()!=metadata['sha256']:
        raise ValueError('frozen input hash mismatch')
    expected={p:sha256(p.read_bytes()).hexdigest() for p in
              (FIXTURES,MANIFEST,DATA,Path(__file__),Path('knowledge-base/study/bishop_frame_manifest.json'),
               *(Path(p) for p in case['source']['frame_paths']),
               Path(case['source']['transcript_path']),*sorted(Path('bishop/v2').glob('*.py')))}
    if args.input_status:expected[args.input_status]=sha256(args.input_status.read_bytes()).hexdigest()
    OUT.mkdir(parents=True,exist_ok=True)
    plan=dict(case_id=CASE_ID,scope='PRIMARY_MENTOR_VIDEO_ALTERNATE_FEED_DIAGNOSTIC',
        source=case['source'],source_case=case,target_profile=args.target_profile,detection_only=args.detection_only,
        source_clock_status='SOURCE_VISIBLE_EXPLORATORY_WINDOW_NOT_VERIFIED_SETUP_OR_FILL_CLOCK',
        as_of='2026-06-13T00:00:00Z',history_start=metadata['requested_start'] if args.full_context else '2026-05-04T00:00:00Z',
        context_history='FULL_FROZEN' if args.full_context else 'BOUNDED_40_DAY',profile_diagnostic=args.profile or args.profile_entries or args.profile_stories,
        scan_start='2026-05-29T00:00:00Z' if pair=='EURGBP' else '2026-06-05T00:00:00Z',input_path=str(DATA),manifest_path=str(MANIFEST),
        frozen_sha256={str(p):v for p,v in expected.items()},costs='EXPLICIT_ZERO_COST',
        limitations=['Source-visible exploratory window is not a teacher fill window.',
                    'Full frozen history still requires coverage checks; bounded history cannot establish full higher-timeframe context.',
                    'IC and FOREXcom chart alignment is unverified.',
                    'A detected pattern/order is not automatically the source trade.',
                    'No source numeric tolerance or expected outcome is fitted.'])
    if pair=='EURGBP':plan['source_formation_window']=['2026-05-29T00:00:00Z','2026-06-06T00:00:00Z']
    detection_spec=None
    if args.nested_m30:
        if CASE_ID!='video-t3-usdcad-buy-open' or not args.full_context:raise ValueError('Nested M30 requires full-context USDCAD source case')
        child=json.loads(args.detection_status.read_text())
        if child.get('status')!='RAW_COLLECTED_UNVALIDATED':raise ValueError('Frozen real M1 child input required')
        detection_spec={'path':child['path'],'manifest':child['manifest']}
        plan['mixed_detection']=detection_spec
        for p in (args.detection_status,Path(child['path']),Path(child['manifest'])):expected[p]=sha256(p.read_bytes()).hexdigest()
    execution_spec=None
    if args.execution_status:
        if CASE_ID!='video-t3-usdcad-buy-open' or not args.full_context:
            raise ValueError('execution refinement requires full-context USDCAD case')
        status=json.loads(args.execution_status.read_text())
        if status['status']!='RAW_COLLECTED_UNVALIDATED':
            raise ValueError('finer execution collection failed')
        execution_spec={'path':status['path'],'manifest':status['manifest']}
        for p in (args.execution_status,Path(status['path']),Path(status['manifest'])):
            expected[p]=sha256(p.read_bytes()).hexdigest()
        plan['execution_refinement']=execution_spec
        plan['frozen_sha256']={str(p):v for p,v in expected.items()}
    if args.quote_evidence:
        if execution_spec is None:raise ValueError('quote evidence requires finer execution feed')
        plan['quote_evidence_directory']=str(args.quote_evidence)
        for p in sorted(args.quote_evidence.iterdir()):
            if p.is_file():expected[p]=sha256(p.read_bytes()).hexdigest()
        plan['frozen_sha256']={str(p):v for p,v in expected.items()}
    plan['frozen_sha256']={str(p):v for p,v in expected.items()}
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    def timeout(*_):raise TimeoutError('bounded primary video replay')
    profiler=cProfile.Profile() if (args.profile or args.profile_entries or args.profile_stories) else None
    stage_times=[]
    original_functions={name:getattr(replay_engine,name) for name in ('analyze','find_stories','detect_setups','simulate')}
    def timed_stage(name,fn):
        def invoke(*a,**k):
            started=time.perf_counter();completed=False
            try:
                answer=fn(*a,**k);completed=True;return answer
            finally:
                stage_times.append({'stage':name,'seconds':round(time.perf_counter()-started,4),'completed':completed})
                (OUT/'stage_times.json').write_text(json.dumps(stage_times,indent=2)+'\n')
        return invoke
    for name,fn in original_functions.items():setattr(replay_engine,name,timed_stage(name,fn))
    if args.profile_entries or args.profile_stories:
        target_name='find_stories' if args.profile_stories else 'detect_setups'
        original_target=getattr(replay_engine,target_name)
        def profiled_stage(*a,**k):
            signal.setitimer(signal.ITIMER_REAL,60);profiler.enable()
            print(target_name.upper()+"_PROFILE_STARTED",flush=True)
            return original_target(*a,**k)
        setattr(replay_engine,target_name,profiled_stage)
    prior=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,60 if args.profile else (600 if args.full_context else 180))
    if profiler and not (args.profile_entries or args.profile_stories):profiler.enable()
    samples=Counter();old_sample_handler=None
    if args.full_context:
        def sample_cpu(signum,frame):
            stack=[]
            while frame is not None:
                stack.append(f'{Path(frame.f_code.co_filename).name}:{frame.f_code.co_name}:{frame.f_lineno}')
                frame=frame.f_back
            samples[' <- '.join(stack[:8])]+=1
        old_sample_handler=signal.signal(signal.SIGPROF,sample_cpu)
        signal.setitimer(signal.ITIMER_PROF,1,1)
    try:
        result=run(str(DATA),metadata,as_of=plan['as_of'],history_start=plan['history_start'],
                   scan_start=plan['scan_start'],policy=StrategyPolicy(source_profile='nested_confirmation' if args.nested_m30 else 'bishop_confirmation',
                   risk_profile='context_liquidity',target_profile=args.target_profile,
                   entry_tfs=('M30',) if args.nested_m30 else ('H4','H3','H2','H1'),origin_tfs=('W','D','H4')),costs=Costs(),
                   include_diagnostics=not args.detection_only,detection_only=args.detection_only,execution_feed=execution_spec,refinement_directory=args.quote_evidence,detection_feed=detection_spec)
        report=dict(plan=plan,teacher_acceptance='NOT_ESTABLISHED',result=result)
        (OUT/(CASE_ID+'.json.gz')).write_bytes(gzip.compress(json.dumps(report).encode(),mtime=0))
        rows=[s for s in result['setups'] if s['tf']=='H2' and s['side']==case['side']]
        standing=[s for s in result['setups'] if s['model']=='confirmation_standing_extreme' and s['side']==case['side']]
        summary=dict(case_id=CASE_ID,execution_status='DETECTION_ONLY_NOT_EXECUTED' if args.detection_only else 'COMPUTED_DIAGNOSTIC',
                     teacher_acceptance='NOT_ESTABLISHED',source=case['source'],
                     summary=result['summary'],coverage=result['coverage'],target_profile=args.target_profile,
                     target_planning_statuses=dict(Counter(s['status'] for s in result['setups'])),
                     unresolved_setup_reasons=dict(Counter(reason for s in result['setups'] for reason in s['details'].get('unresolved_reasons',()))),
                     standing_source_side_candidates=len(standing),standing_timeframes=sorted({s['tf'] for s in standing}),
                     source_side_model_counts=dict(Counter(s['tf']+':'+s['model'] for s in result['setups'] if s['side']==case['side'])),
                     detection_input=result.get('detection_input'),
                     h2_source_side_candidates=len(rows),h2_source_side_models=sorted({s['model'] for s in rows}),
                     selection_rejections=dict(Counter(r['reason'] for r in result['selection']['rejected'])),limitations=plan['limitations'])
    except TimeoutError:
        summary=dict(case_id=CASE_ID,execution_status='ABORTED_RUNTIME',teacher_acceptance='NOT_ESTABLISHED')
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,prior)
        if old_sample_handler is not None:
            signal.setitimer(signal.ITIMER_PROF,0);signal.signal(signal.SIGPROF,old_sample_handler)
            (OUT/'cpu_samples.json').write_text(json.dumps(samples.most_common(),indent=2)+'\n')
        for name,fn in original_functions.items():setattr(replay_engine,name,fn)
        if profiler:
            profiler.disable();profiler.dump_stats(str(OUT/'profile.pstats'))
            stream=io.StringIO()
            if profiler.getstats():
                pstats.Stats(profiler,stream=stream).sort_stats('cumulative').print_stats(45)
            else:
                stream.write('PROFILE_STAGE_NOT_REACHED_BEFORE_RUNTIME_LIMIT\n')
            (OUT/'profile.txt').write_text(stream.getvalue())
    for p,h in expected.items():
        if sha256(p.read_bytes()).hexdigest()!=h:raise ValueError('frozen source/input changed')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('case_id','execution_status','teacher_acceptance')}))
    return 1 if summary['execution_status']=='ABORTED_RUNTIME' else 0


if __name__=='__main__':raise SystemExit(main())

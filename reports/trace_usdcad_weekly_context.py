"""Read-only full-history W/D/H4 context audit for held USDCAD H1 opportunity.

No entry replay, teacher fitting, target selection, or execution override.
"""
from collections import Counter
from dataclasses import replace
import gzip,json,signal
from hashlib import sha256
from pathlib import Path
from bishop.v2.types import StrategyPolicy,jsonable,utc
from bishop.v2.feed import load_feed
from bishop.v2.aggregation import aggregate,expected_slots,calendar_open_lookup
from bishop.v2.structure import analyze
from bishop.v2.impulse import assess
from bishop.v2.continuity import gaps_from_base,invalidate_levels,suspend_stories
from bishop.v2.stories import find_stories
from bishop.v2.weekly_context import resolve
from bishop.structural_context import summarize

OUT=Path('reports/usdcad_weekly_context')
INPUT=Path('data/teacher_icmarkets_runs/40098655754/data/teacher_icmarkets/collect_c058fc002a50237cd6d2dbb0.csv.gz')
MANIFEST=INPUT.with_name(INPUT.name.removesuffix('.csv.gz')+'.csv.manifest.json')
AT='2026-06-12T16:00:00Z'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    m=json.loads(MANIFEST.read_text());assert sha256(INPUT.read_bytes()).hexdigest()==m['sha256']
    plan={'scope':'W_D_H4_CONTEXT_ONLY_NOT_FULL_ENGINE_OR_TEACHER_ACCEPTANCE',
          'as_of':AT,'history_start':m['requested_start'],'input':str(INPUT),
          'input_sha256':m['sha256'],'policy':'latest_confirmed_weekly_ROOT_batch_v1_OUR_CHOICE',
          'entry_execution':'NOT_RUN','limitations':['Weekly-story context with its D and H4 confirmation routes; does not choose among D/H4-origin stories or place orders.','Source chart agreement and full history sufficiency are not presumed.']}
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    def timeout(*_):raise TimeoutError('180-second context budget')
    signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,180)
    policy=StrategyPolicy(source_profile='bishop_confirmation',origin_tfs=('W',),entry_tfs=('H1',))
    feed=load_feed(str(INPUT),m,AT,m['requested_start']);calendar=m['calendar_id'];opened=calendar_open_lookup(calendar)
    rows=[];segment=0;previous=None
    for b in feed['bars']:
        if previous is not None and next(expected_slots(previous.end,b.start,'H1',calendar,open_lookup=opened),None) is not None:segment+=1
        rows.append(replace(b,segment_id=str(segment)));previous=b
    base=tuple(rows);gaps=gaps_from_base(base,policy);frames={};structures={};coverage={}
    for tf in ('W','D','H4'):
        a=aggregate(base,tf,feed['instrument'],AT,calendar=calendar);frames[tf]=a['bars'];coverage[tf]=a['coverage']
        structures[tf]=invalidate_levels(assess(analyze(a['bars'],policy),a['bars'],policy),gaps,policy)
    stories=suspend_stories(find_stories(frames,structures,policy),gaps,frames,policy)
    context=resolve(stories.stories,stories.events,utc(AT),'USDCAD')
    result={'plan':plan,'execution_status':'COMPUTED_CONTEXT_ONLY','weekly_context':context,
            'structural_context':summarize(structures,utc(AT)),
            'coverage':coverage,'base_bars':len(base),'gap_count':len(gaps),
            'stories':stories,'structures':structures,
            'story_counts':dict(Counter((s.origin_tf+':'+s.details.get('scope_type','UNKNOWN')) for s in stories.stories))}
    (OUT/'result.json.gz').write_bytes(gzip.compress(json.dumps(jsonable(result)).encode(),mtime=0))
    summary={k:result[k] for k in ('execution_status','weekly_context','base_bars','gap_count','story_counts','coverage','structural_context')}
    (OUT/'summary.json').write_text(json.dumps(jsonable(summary),indent=2)+'\n');print(json.dumps(context))
    from reports.reprice_usdcad_held import reprice
    (OUT/'held_plan_context_isolation.json').write_text(json.dumps(reprice(context),indent=2)+'\n')
    signal.setitimer(signal.ITIMER_REAL,0)
if __name__=='__main__':main()

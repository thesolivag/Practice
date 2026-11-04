"""Focused Actions-only trace; source snapshot times are not fill times."""
import gzip,json,os
from collections import Counter
from pathlib import Path
from reports.replay_collected_teacher_examples_v2 import inventory_manifests,plan_case,diagnostic_groups,digest
from bishop.v2.engine import run
from bishop.v2.types import StrategyPolicy
from bishop.v2.simulation import Costs
CLOCKS={'pdf-p13-eurnzd-sell-1':'2026-07-17T18:46:00Z',
        'pdf-p27-gbpusd-sell-1':'2026-06-24T11:49:00Z'}
def main():
    case_id=os.environ['INVESTIGATE_CASE']
    case=next(c for c in json.load(open('tests/bishop_examples.json'))['examples'] if c['id']==case_id)
    plan=plan_case(case,inventory_manifests('data/teacher_icmarkets_runs'))
    assert plan['status']=='PLANNED',plan
    meta=json.load(open(plan['manifest_path']))
    out=Path('reports/teacher_missing_runs')/case_id;out.mkdir(parents=True,exist_ok=True)
    summaries=[]
    for label,clock in [('printed_source_snapshot',CLOCKS[case_id]),('research_later_kl_irl',CLOCKS[case_id])]:
        policy=StrategyPolicy(source_profile='bishop_confirmation',risk_profile='context_liquidity',target_profile='nearest_erl',entry_tfs=tuple(dict.fromkeys(('H4','H2','H1',case['tf']))),origin_tfs=('W','D','H4'),research_later_kl_irl=label=='research_later_kl_irl')
        result=run(plan['input_path'],meta,as_of=clock,history_start=plan['history_start'],scan_start=plan['scan_start'],policy=policy,costs=Costs(),include_diagnostics=True)
        groups=diagnostic_groups(result,case)
        summary={'case_id':case_id,'cutoff':label,'as_of':clock,'source_snapshot_not_fill_clock':True,'input_sha256':digest(plan['input_path']),'summary':result['summary'],'same_side_source_tf_groups':len(groups),'story_sides':dict(Counter((s['side'] for s in result['stories']))),'setup_routes':dict(Counter((s['model']+':'+s['tf']+':'+s['side'] for s in result['setups']))),'support_counts':dict(Counter(str(s.get('route',s.get('component')))+':'+str(s.get('status'))+':'+str(s.get('reason','')) for s in result['support']))}
        with gzip.open(out/(label+'.json.gz'),'wt') as f:json.dump({'case':case,'plan':plan,'summary':summary,'result':result},f)
        summaries.append(summary)
    (out/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    print(json.dumps(summaries,indent=2))
if __name__=='__main__':main()

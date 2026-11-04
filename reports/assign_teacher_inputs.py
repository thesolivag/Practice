"""Explicitly associate already-collected windows with covered source cases.

No new prices, clock labels or calendar approvals. Raw sidecars remain frozen.
Selection uses pair, resolution and declared time coverage before any outcomes.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from bishop.v2.types import utc,stable_id
from reports.replay_collected_teacher_examples_v2 import inventory_manifests,plan_case


def assign(fixtures,data_dir,annotations,out_dir):
    fixture=Path(fixtures); original=sha256(fixture.read_bytes()).hexdigest()
    cases=json.loads(fixture.read_text())['examples']
    notes={a['example_id']:a for a in json.loads(Path(annotations).read_text())['annotations']}
    inputs=inventory_manifests(data_dir); output=Path(out_dir)
    records=[{'case_id':i['metadata']['case_assignment']['assigned_case'],'path':i['path'],
              'manifest':i['manifest_path'],'derivation':i['metadata']['case_assignment']}
             for i in inputs if i.get('metadata',{}).get('case_assignment',{}).get('fixture_sha256')==original]
    for case in cases:
        plan=plan_case(case,inputs,notes.get(case['id']))
        if plan['status']!='MISSING_EXPLICIT_MATCHING_INPUT':continue
        eligible=[]
        for item in inputs:
            m=item.get('metadata',{})
            if m.get('symbol')!=case['pair'] or m.get('base_tf')!=plan['base_tf']:continue
            if utc(m['requested_start'])>utc(plan['history_start']) or utc(m['requested_end'])<utc(plan['as_of']):continue
            if sha256(Path(item['path']).read_bytes()).hexdigest()!=m['sha256']:raise ValueError('source hash mismatch')
            eligible.append(item)
        if not eligible:continue
        chosen=min(eligible,key=lambda x:(utc(x['metadata']['requested_end'])-utc(x['metadata']['requested_start']),x['manifest_path']))
        m=chosen['metadata'];ids=sorted(set(m['case_ids'])|{case['id']})
        identity=stable_id('case_assignment',chosen['manifest_sha256'],ids)
        output.mkdir(parents=True,exist_ok=True)
        csv=output/(identity+'.csv.gz');manifest=csv.with_suffix('.manifest.json')
        if csv.exists() or manifest.exists():raise FileExistsError('frozen assignment already exists')
        derivation={'source_manifest':chosen['manifest_path'],'source_manifest_sha256':chosen['manifest_sha256'],
                    'source_data':chosen['path'],'source_data_sha256':m['sha256'],
                    'fixture_sha256':original,'assigned_case':case['id'],
                    'selection':'matching_pair_required_resolution_declared_window_then_path_NO_OUTCOME_OR_PRICE_SELECTION',
                    'clock_kind':plan['clock_kind'],'as_of':plan['as_of'],'history_start':plan['history_start'],
                    'calendar_approval':False,'teacher_acceptance':False}
        csv.write_bytes(Path(chosen['path']).read_bytes())
        manifest.write_text(json.dumps({**m,'case_ids':ids,'raw_collection_status':'CASE_ASSIGNMENT_DERIVATION_NO_PRICE_CHANGES',
                                        'case_assignment':derivation},indent=2)+'\n')
        records.append({'case_id':case['id'],'path':str(csv),'manifest':str(manifest),'derivation':derivation})
    if sha256(fixture.read_bytes()).hexdigest()!=original:raise RuntimeError('source fixtures changed')
    return records


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixtures',default='tests/bishop_examples.json')
    p.add_argument('--data-dir',default='data/teacher_icmarkets_runs')
    p.add_argument('--clock-annotations',default='reports/teacher_clock_annotations.json')
    p.add_argument('--out-dir',default='data/teacher_icmarkets_runs/derived_case_assignments')
    p.add_argument('--report',default='reports/teacher_input_assignments.json')
    a=p.parse_args();records=assign(a.fixtures,a.data_dir,a.clock_annotations,a.out_dir)
    Path(a.report).write_text(json.dumps({'scope':'METADATA_ASSOCIATION_ONLY_NOT_TEACHER_ACCEPTANCE','assignments':records},indent=2)+'\n')
    print('Explicit input associations:',len(records))


if __name__=='__main__':main()

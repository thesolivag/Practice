"""Compact evidence from a completed mixed-input diagnostic; no strategy rerun."""
import argparse
from collections import Counter
from decimal import Decimal
import gzip
from hashlib import sha256
import json
from pathlib import Path
import ijson


def plain(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    if isinstance(value, dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):return [plain(v) for v in value]
    return value


def inspect(path, out, *, run_id):
    with gzip.open(path,'rb') as f:
        if next(ijson.items(f,'result.scope'))!='DETECTION_ONLY_NOT_EXECUTED':
            raise ValueError('This extractor requires a completed detection-only diagnostic')
    counts=Counter(); reasons=Counter(); clocks=Counter(); grouped={}; window_count=0
    with gzip.open(path,'rb') as f:
        for row in ijson.items(f,'result.setups.item'):
            if row['tf']!='M30' or row['model']!='nested_confirmation' or row['side']!='BUY':continue
            counts[row['status']]+=1;clocks[row['clock']['available_at']]+=1
            reasons.update(row.get('details',{}).get('unresolved_reasons',()))
            at=row['clock']['available_at']
            if not '2026-06-12T13:00'<=at<'2026-06-12T18:00':continue
            window_count+=1
            key=tuple(row[k] for k in ('tf','side','entry_ticks','stop_ticks','target_ticks','status','level_id'))+(at,tuple(row.get('details',{}).get('nesting_chain_ids',())))
            if key not in grouped:
                d=row['details']
                detail_keys=('target_plan','selected_target_ticks','target_candidates','target_adjustments',
                    'nesting_chain_ids','parent_entry_tf','standing_reference_bar_id','standing_confirmation_bar_id',
                    'confirmation_protection_bar_ids','confirmation_protection_policy','protected_objects',
                    'unresolved_reasons','entry_weekly_relation','entry_weekly_context','source_profile','lineage_policy')
                grouped[key]=dict(geometry={k:row[k] for k in ('tf','side','entry_ticks','stop_ticks','target_ticks','status','level_id','clock','order_type')},
                                 context_variants=0,sample_setup_id=row['id'],sample_story_id=row['story_id'],
                                 details={k:d[k] for k in detail_keys if k in d})
            grouped[key]['context_variants']+=1
    with gzip.open(path,'rb') as f:plan=next(ijson.items(f,'plan'))
    with gzip.open(path,'rb') as f:audit=next(ijson.items(f,'result.detection_input'))
    if plan.get('case_id')!='video-t3-usdcad-buy-open' or not isinstance(audit,dict) or audit.get('scope')!='MIXED_H1_CONTEXT_REAL_M1_CHILD_DETECTION':
        raise ValueError('Completed explicit USDCAD mixed child diagnostic required')
    report=dict(scope='COMPLETED_MIXED_M30_DIAGNOSTIC_NOT_TEACHER_ACCEPTANCE',actions_run=run_id,
                report_sha256=sha256(Path(path).read_bytes()).hexdigest(),plan=plan,
                child_detection_input=audit,all_nested_buy_status_counts=dict(counts),
                all_unresolved_reasons=dict(reasons),all_nested_buy_submission_counts=dict(clocks),
                source_window='June12 13:00–18:00UTC exploratory only; exact teacher setup/fill clock unresolved',
                window_candidate_count=window_count,window_economic_groups=list(grouped.values()),
                source_outcome='STILL_OPEN_NO_FINAL_TP_SL',orders_and_execution='NOT_RUN_DETECTION_ONLY',
                teacher_acceptance='NOT_ESTABLISHED')
    Path(out).write_text(json.dumps(plain(report),indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('report');p.add_argument('out');p.add_argument('--run-id',required=True,type=int)
    a=p.parse_args();r=inspect(a.report,a.out,run_id=a.run_id)
    print(json.dumps(dict(status_counts=r['all_nested_buy_status_counts'],window_candidate_count=r['window_candidate_count'],economic_groups=len(r['window_economic_groups']))))


if __name__=='__main__':main()

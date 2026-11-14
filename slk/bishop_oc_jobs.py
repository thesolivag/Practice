"""GitHub-only capacity-corrected replay using frozen H1 and saved M1 evidence."""
import argparse,os,time
from pathlib import Path
from dataclasses import replace
from collections import Counter
from slk import bishop_year_jobs as J,bishop_oc_replay as C
from slk.bishop_unknown_jobs import digest,validate_minutes
from bishop.v2.types import utc,jsonable
# Reuse the old artifact orchestration with an explicitly separate replay module.
J.Y=C


def prepare(inputs,minute):
    inputs,minute=Path(inputs),Path(minute)
    J.reuse_snapshot(inputs);manifest=C.load(inputs/'manifest.json')
    manifest['source_snapshot_run']=42371042901
    manifest['execution_policy']='three_candle_oc_h12_single_position_partial_saved_m1_v1'
    manifest['engulfing_rule']='two opposing bodies; third body closes beyond immediateOC; first-close reference'
    manifest['oc_gap_policy']=C.OC_GAP_POLICY
    manifest['entry_timeframes']=['H1','H2']
    manifest['occupancy']='one pending/open opportunity per pair per family; all RR exits share admission'
    manifest['old_results_unchanged']=True
    manifest['quote_gap_reference_note']='Uses candle1 close, same as existing alert definition; records candle2 open offset'
    manifest['minute_source_run']=42499187752
    for pair in manifest['pairs']:
        feed=C.feed_file(inputs/(pair+'.json.gz'));coarse={b.start:b for b in feed['bars']}
        folder=minute/('unknown-'+pair);summary=C.load(folder/'summary.json');fine={}
        for name,sha in summary['evidence_sha256'].items():
            p=folder/'minute-evidence'/name
            if digest(p)!=sha:raise ValueError('Saved minute hash mismatch')
            evidence=C.load(p);at=utc(evidence['coarse']['start'])
            bars=validate_minutes(coarse[at],evidence['m1_rows'],feed['instrument'])
            fine[at.isoformat()]=bars
        path=inputs/'minutes'/(pair+'.json.gz');C.dump(path,fine)
        manifest['markets'][pair]['minute_file_sha256']=digest(path)
        manifest['markets'][pair]['refined_hours']=len(fine)
    C.dump(inputs/'manifest.json',manifest)


_base_feed=C.feed_file

def load_feed(path):
    from bishop.v2.types import Bar
    path=Path(path);feed=_base_feed(path);fine=path.parent/'minutes'/path.name
    manifest=C.load(path.parent/'manifest.json');pair=feed['instrument'].symbol
    if digest(path)!=manifest['markets'][pair]['sha256']:raise ValueError('H1 hash mismatch')
    if digest(fine)!=manifest['markets'][pair]['minute_file_sha256']:raise ValueError('M1 hash mismatch')
    feed['minute_evidence']={utc(k):tuple(Bar(**{f:x for f,x in b.items() if f != 'id'}) for b in v) for k,v in C.load(fine).items()}
    return feed


def pilot(inputs,out):
    root,out=Path(inputs),Path(out);m=C.load(root/'manifest.json');config=C.load(root/'config.json')
    pair='EURUSD';feed=load_feed(root/(pair+'.json.gz'));start=utc(m['start']);end=utc(m['end'])
    clocks=[b.available_at for b in feed['bars'] if start<=b.available_at<=end]
    at=clocks[0];cut=C.prefix(feed,at);began=time.monotonic()
    def step(f):return C.decision(f,C.dataframe(f),at,start,config,C.new_state(),{})
    original=step(feed);assert original==step(cut),'Physical prefix failure'
    poisoned={**feed,'bars':tuple(replace(b,open_ticks=b.open_ticks*2,high_ticks=b.high_ticks*2,low_ticks=b.low_ticks*2,close_ticks=b.close_ticks*2) if b.available_at>at else b for b in feed['bars'])}
    assert original==step(poisoned),'Future poison failure'
    state=C.replay(feed,config,start,clocks[23],checkpoint=out/'checkpoint.json.gz')
    secs=(time.monotonic()-began)/27;estimate=secs*24*31/60
    # Known mini-app reference: independently inspect the corrected detector at
    # its original decision clock. This is qualification evidence, not P&L.
    reference_at=utc('2026-02-18T10:00:00+00:00')
    ref_result,_=C.detect(feed,reference_at,later=True)
    reference=[s for s in ref_result['setups'] if s['details'].get('three_candle_oc')]
    C.dump(out/'engulfing-reference.json',{'pair':pair,'at':reference_at.isoformat(),
        'corrected_setups':reference,'note':'Closed-prefix detection; statuses retain risk/context restrictions.'})
    if not reference:raise RuntimeError('Known EURUSD engulfing reference did not reproduce; stop before full replay')
    C.dump(out/'pilot.json',{'status':'PASS','pair':pair,'hours':24,'prefix_equal':True,'poisoned_equal':True,
        'seconds_per_hour':secs,'estimated_31day_minutes':estimate,'note':'Early pilot is a runtime estimate, not a full-year performance result.'})
    if estimate>300:raise RuntimeError('Monthly replay exceeds runtime budget')


def segment(inputs,pair,number,out,resume):
    C.feed_file=load_feed
    J.segment(inputs,pair,number,out,resume)


def main():
    p=argparse.ArgumentParser();p.add_argument('job',choices=['prepare','pilot','segment','collect'])
    p.add_argument('--inputs',default='year-inputs');p.add_argument('--minute',default='minute')
    p.add_argument('--out',default='result');p.add_argument('--pair');p.add_argument('--number',type=int)
    p.add_argument('--resume');p.add_argument('--results',default='collected');a=p.parse_args()
    if a.job=='prepare':prepare(a.inputs,a.minute)
    elif a.job=='pilot':pilot(a.inputs,a.out)
    elif a.job=='segment':segment(a.inputs,a.pair,a.number,a.out,a.resume)
    else:
        C.feed_file=load_feed
        J.collect(a.inputs,a.results,a.out)
        from slk.bishop_session_costs import build
        build(a.inputs,a.results,Path(a.out)/'sessions')
        from slk.bishop_oc_review_bundle import build_bundle
        build_bundle(a.inputs,a.results,Path(a.out)/'review-bundle')

if __name__=='__main__':main()

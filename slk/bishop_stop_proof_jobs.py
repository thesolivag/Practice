"""Audit saved minute evidence only; no broker, detector, DB or notifications."""
from pathlib import Path
from collections import Counter,defaultdict
import argparse
from slk import bishop_year_replay as Y
from slk.bishop_unknown_jobs import validate_minutes,censor_event,digest,SIM_SHA
from slk.bishop_paper import thaw_order
from bishop.v2.types import utc,jsonable
from bishop.v2.simulation import simulate as original
from bishop.v2.research_stop_simulation import simulate


def audit(root,inputs,out):
    root,inputs,out=Path(root),Path(inputs),Path(out);out.mkdir(parents=True,exist_ok=True)
    if digest(Path(__file__).parents[1]/'bishop/v2/simulation.py')!=SIM_SHA:raise ValueError('Original engine changed')
    report=Y.load(root/'unknown-report/REPORT.json');manifest=Y.load(inputs/'manifest.json')
    details=[];counts=Counter();by_mode=defaultdict(Counter);missing=[]
    for pair,summary in sorted(report['markets'].items()):
        folder=root/('unknown-'+pair)
        if not (folder/'trades.json.gz').exists():missing.append(pair);continue
        if digest(inputs/(pair+'.json.gz'))!=summary['frozen_input_sha256']:raise ValueError('Input hash mismatch')
        feed=Y.feed_file(inputs/(pair+'.json.gz'));inst=feed['instrument'];end=utc(summary['end'])
        evidence={}
        for name,sha in summary['evidence_sha256'].items():
            p=folder/'minute-evidence'/name
            if digest(p)!=sha:raise ValueError('Minute evidence hash mismatch')
            e=Y.load(p);evidence[utc(e['coarse']['start'])]=e
        for a in Y.load(folder/'trades.json.gz'):
            if a['status']!='UNRESOLVED' or a['reason']!='STILL_AMBIGUOUS_WITHIN_ONE_MINUTE':continue
            order=thaw_order(a['order']);bars=[]
            for h in feed['bars']:
                if h.end<=order.available_at or h.available_at>end:continue
                if h.start.isoformat() in a['refined_hours']:
                    bars.extend(validate_minutes(h,evidence[h.start]['m1_rows'],inst))
                else:bars.append(h)
            args=((order,),bars,inst,{},end,a['actions'])
            before=original(*args,calendar=inst.calendar_id);ev=censor_event(before)
            if before['observations'][0]['outcome']!='CENSORED' or not ev or ev.details.get('reason')!='UNRESOLVED_INTRABAR_SEQUENCE':
                raise ValueError('Prior minute ambiguity not reproduced')
            after=simulate(*args,calendar=inst.calendar_id);obs=jsonable(after['observations'][0])
            status='UNCHANGED'
            if obs['outcome']!='CENSORED':
                if obs['outcome']!='LOSS':raise ValueError('Stop-only correction unexpectedly changed non-loss')
                oldfill=a['original'].get('fill_window');newfill=obs.get('fill_window')
                if not oldfill or not newfill or utc(newfill['end'])>utc(oldfill['end']):
                    raise ValueError('Fill escaped originally observed pending management')
                status='PROVEN_LOSS'
            row={'pair':pair,'mode':a['mode'],'order_id':order.id,'status':status,
                 'order':a['order'],'before':jsonable(before['observations'][0]),'after':obs,
                 'events':jsonable(after['events'])}
            details.append(row)
            if pair in report['matched_markets']:
                counts[status]+=1;by_mode[a['mode']][status]+=1
                if status=='PROVEN_LOSS':by_mode[a['mode']]['added_R']+=float(obs['net_r'])
    rows=[]
    for mode,old in sorted(report['original_matched_results'].items()):
        prev=report['unknown_refinement'][mode];delta=by_mode[mode]
        rows.append({'model':mode,'additional_losses':delta['PROVEN_LOSS'],
            'remaining_unknown':prev['new_outcomes'].get('CENSORED',0)-delta['PROVEN_LOSS'],
            'previous_gross_R':old['total_R']+prev['resolved_gross_R'],
            'updated_gross_R':old['total_R']+prev['resolved_gross_R']+delta['added_R']})
    Y.dump(out/'details.json.gz',details)
    Y.dump(out/'REPORT.json',{'status':'PARTIAL' if missing else 'COMPLETE','missing':missing,
        'source_year_run':42371042901,'source_minute_run':42499187752,'counts':counts,'models':rows,
        'scope':'Saved cohort; zero-cost M1 limit entry followed by stop only; live simulator unchanged.'})
    lines=['# Proven limit entry/stop correction',f"Coverage: {'PARTIAL' if missing else 'COMPLETE'}; missing: {missing}",
           '', '| Model | Additional losses | Still unknown | Updated gross R |','|---|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['model']} | {r['additional_losses']} | {r['remaining_unknown']} | {r['updated_gross_R']:.2f} |")
    lines+=['','Only provable M1 entry/SL cases changed. Both-exit touches, opening at/beyond stop, entry/TP-only ambiguity and missing minutes remain unresolved.',
            'Gross zero-cost results; unresolved outcomes excluded. Prior artifacts and live engine unchanged.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',default='saved');p.add_argument('--inputs',default='year-inputs');p.add_argument('--out',default='report');a=p.parse_args();audit(a.results,a.inputs,a.out)

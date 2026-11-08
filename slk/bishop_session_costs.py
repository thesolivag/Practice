"""Session and cost sensitivity of saved orders. No live quotes or execution."""
import argparse,csv
from collections import Counter,defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from bishop.v2.types import utc,jsonable
from slk import bishop_year_replay as Y
from slk.bishop_unknown_jobs import digest
from slk.bishop_monthly_report import amend
NY=ZoneInfo('America/New_York');CLOSED={'WIN','LOSS','BREAK_EVEN'}
COSTS=(0,.5,1,2,3,5)


def session(obs):
    window=obs.get('fill_window')
    if not window:return 'NO_PROVEN_FILL_WINDOW'
    a,b=utc(window['start']),utc(window['end']);hours=set()
    if b<=a:raise ValueError('Invalid fill interval')
    # Intersect half-open observed fill intervals with NY hours (DST-aware).
    while a<b:
        hours.add(a.astimezone(NY).hour);a=min(b,a+timedelta(minutes=1))
    if 17 in hours:return 'ROLLOVER_17_NY'
    if hours & {16,18}:return 'ADJACENT_16_OR_18_NY'
    return 'OTHER_HOURS'


def adjusted(row,inst,cost):
    obs=row['observation']
    if obs['outcome'] not in CLOSED:return None
    fill=Decimal(str(obs['fill_ticks']));stop=Decimal(str(obs['initial_stop_ticks']))
    risk=abs(fill-stop)*inst.tick_size/inst.distance_unit
    if risk<=0:raise ValueError('Invalid cost denominator')
    return float(Decimal(str(obs['net_r']))-Decimal(str(cost))/risk)


def summarize(rows,insts):
    out=[]
    for mode in sorted({r['mode'] for r in rows}):
        for bucket in ('ALL','ROLLOVER_17_NY','ADJACENT_16_OR_18_NY','OTHER_HOURS','NO_PROVEN_FILL_WINDOW'):
            group=[r for r in rows if r['mode']==mode and (bucket=='ALL' or session(r['observation'])==bucket)]
            counts=Counter(r['observation']['outcome'] for r in group)
            for cost in COSTS:
                values=[adjusted(r,insts[r['pair']],cost) for r in group if r['observation']['outcome'] in CLOSED]
                out.append({'model':mode,'fill_window_group':bucket,'hypothetical_round_trip_pips':cost,
                    'orders':len(group),'resolved':len(values),'unknown':counts['CENSORED'],'open':counts['OPEN'],
                    'cancelled':counts['CANCELLED'],'expired':counts['EXPIRED'],
                    'positive_after_cost':sum(v>0 for v in values),'negative_after_cost':sum(v<0 for v in values),
                    'resolved_R_after_cost':sum(values),'mean_R_after_cost':sum(values)/len(values) if values else None})
    return out


def build(inputs,results,out,original=False):
    inputs,results,out=Path(inputs),Path(results),Path(out);out.mkdir(parents=True,exist_ok=True)
    manifest=Y.load(inputs/'manifest.json');cfg=Y.load(inputs/'config.json');rows=[];insts={};missing=[];releases=Counter()
    fixes={};minute_root=results/'minute'
    if original:
        fixes={a['order_id']:a for a in Y.load(results/'proof/details.json.gz') if a['status']=='PROVEN_LOSS'}
    for pair in manifest['pairs']:
        if not manifest['markets'][pair]['kk_full_warmup'] or pair in cfg['avoid_pairs']:continue
        paths=list(results.glob(f'year-*-{pair}/checkpoint.json.gz'))
        if not paths:missing.append(pair);continue
        p=max(paths,key=lambda p:int(p.parent.name.split('-')[1]));state=Y.load(p)
        feed=Y.feed_file(inputs/(pair+'.json.gz'));insts[pair]=feed['instrument']
        required=max(b.available_at for b in feed['bars'] if b.available_at<=utc(manifest['end']))
        if not state['audit'] or utc(state['audit'][-1]['at'])!=required:missing.append(pair);continue
        book=state['book']
        if original:
            summary=Y.load(minute_root/('unknown-'+pair)/'summary.json')
            if digest(p)!=summary['source_checkpoint_sha256']:raise ValueError('Checkpoint hash mismatch')
            for a in Y.load(minute_root/('unknown-'+pair)/'trades.json.gz'):
                if a['status'] in ('RESOLVED','OPEN'):book[a['order_id']]=amend(book[a['order_id']],a)
            for ident in book:
                if ident in fixes:book[ident]=amend(book[ident],fixes[ident],stop=True)
        for r in book.values():
            r['pair']=pair;rows.append(r)
            if r.get('capacity_released_at'):releases[r['mode']]+=1
    stats=summarize(rows,insts)
    if not stats:raise ValueError('No completed common markets')
    with open(out/'session_cost_scenarios.csv','w') as f:
        w=csv.DictWriter(f,fieldnames=list(stats[0]));w.writeheader();w.writerows(stats)
    # Per-month exits keep closed outcome timing separate from fill-session classification.
    monthly=[]
    for month in sorted({str(r.get('closed_at'))[:7] for r in rows if r['observation']['outcome'] in CLOSED}):
        for r in summarize([r for r in rows if r['observation']['outcome'] in CLOSED and str(r['closed_at'])[:7]==month],insts):monthly.append({'close_month_UTC':month,**r})
    if monthly:
        with open(out/'monthly_cost_scenarios.csv','w') as f:
            w=csv.DictWriter(f,fieldnames=list(monthly[0]));w.writeheader();w.writerows(monthly)
    Y.dump(out/'REPORT.json',{'status':'PARTIAL' if missing else 'COMPLETE','missing_common_markets':missing,
        'scope':'original_corrected_cohort_capacity_blocked' if original else 'causal_capacity_replay',
        'capacity_releases':releases,'cost_assumptions_pips':COSTS,'results':stats,
        'limitations':['Hypothetical all-in round-trip price deductions, not measured historical spread/commission/slippage.',
        'No spread-dependent fill/SL/TP changes or swap model. Unknown and open outcomes excluded from R.',
        'Session is observed fill-window overlap, not tick-accurate entry time. 17:00-18:00 NY includes DST.',
        '16:00-17:00 and 18:00-19:00 are separately reported adjacent hours; no optimized filter or news exclusion.',
        'Comparison does not establish performance of a strategy that blocks rollover entries; no freed-capacity counterfactual here.']})
    lines=['# Session and cost sensitivity','', 'Scope: '+('Original corrected trades; capacity blockage still applies.' if original else 'Fresh causal-capacity replay; partial frozen M1 coverage; unresolved outcomes retained.'),
        f'Missing common markets: {missing}.', '',
        'Costs below are explicit sensitivity assumptions, NOT actual broker net performance. Unknown/open outcomes excluded. No news classification or live filter was applied.',
        '', '| Model | Fill-window group | Resolved | Unknown | Gross R | After 1 pip | After 2 pips | After 3 pips |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in stats:
        if r['hypothetical_round_trip_pips']!=0:continue
        costs={s['hypothetical_round_trip_pips']:s['resolved_R_after_cost'] for s in stats if s['model']==r['model'] and s['fill_window_group']==r['fill_window_group']}
        lines.append(f"| {r['model']} | {r['fill_window_group']} | {r['resolved']} | {r['unknown']} | {costs[0]:.2f} | {costs[1]:.2f} | {costs[2]:.2f} | {costs[3]:.2f} |")
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',default='year-inputs');p.add_argument('--results',default='saved');p.add_argument('--out',default='report');p.add_argument('--original',action='store_true');a=p.parse_args();build(a.inputs,a.results,a.out,a.original)

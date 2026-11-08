"""Aggregate immutable saved cohorts and execution corrections; no replay."""
import argparse,csv,copy
from collections import Counter,defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from slk import bishop_year_replay as Y
from slk.bishop_unknown_jobs import digest
from bishop.v2.types import utc
NY=ZoneInfo('America/New_York')
CLOSED={'WIN','LOSS','BREAK_EVEN'}


def close_time(events):
    e=next((e for e in reversed(events) if e['kind'].startswith('POSITION_') and
            e.get('details',{}).get('remaining')=='0'),None)
    if not e:raise ValueError('Missing terminal execution evidence')
    return e['clock']['available_at']


def amend(row,change,stop=False):
    row=copy.deepcopy(row)
    if row['observation']['outcome']!='CENSORED':raise ValueError('Correction would overwrite resolved original')
    if change['order']!=row['order']:raise ValueError('Frozen order differs')
    obs=change['after'] if stop else change['observation']
    row['observation']=obs
    row['closed_at']=close_time(change['events']) if obs['outcome'] in CLOSED else None
    return row


def metric(rows):
    counts=Counter(r['observation']['outcome'] for r in rows)
    vals=[Decimal(str(r['observation']['net_r'])) for r in rows if r['observation']['outcome'] in CLOSED]
    gains=sum((max(v,0) for v in vals),Decimal(0));loss=-sum((min(v,0) for v in vals),Decimal(0))
    return {'orders':len(rows),'wins':counts['WIN'],'losses':counts['LOSS'],
        'break_even':counts['BREAK_EVEN'],'unknown':counts['CENSORED'],'open':counts['OPEN'],
        'cancelled':counts['CANCELLED'],'expired':counts['EXPIRED'],
        'gross_R':float(sum(vals,Decimal(0))),'win_rate':100*counts['WIN']/len(vals) if vals else None,
        'profit_factor':float(gains/loss) if loss else None}


def aggregate(rows,months):
    monthly=[];hourly=[];rollover=[]
    for mode in sorted({r['mode'] for r in rows}):
        group=[r for r in rows if r['mode']==mode];cum=0
        for month in months:
            created=[r for r in group if utc(r['order']['clock']['available_at']).strftime('%Y-%m')==month]
            exits=[r for r in group if r['observation']['outcome'] in CLOSED and utc(r['closed_at']).strftime('%Y-%m')==month]
            filled=[r for r in group if r['observation'].get('fill_window') and utc(r['observation']['fill_window']['end']).strftime('%Y-%m')==month]
            m=metric(exits);cohort=metric(created);cum+=m['gross_R']
            monthly.append({'model':mode,'month_UTC':month,'orders_created':len(created),'fills_observed':len(filled),
                'closed_wins':m['wins'],'closed_losses':m['losses'],'closed_break_even':m['break_even'],
                'realized_gross_R':m['gross_R'],'cumulative_gross_R':cum,
                'entry_cohort_unknown_at_cutoff':cohort['unknown'],'entry_cohort_open_at_cutoff':cohort['open'],
                'entry_cohort_cancelled':cohort['cancelled'],'entry_cohort_expired':cohort['expired']})
        for hour in range(24):
            part=[r for r in group if utc(r['order']['clock']['available_at']).astimezone(NY).hour==hour]
            hourly.append({'model':mode,'submission_hour_NY':hour,**metric(part)})
        for hour in (16,17,18):
            part=[r for r in group if r['observation'].get('fill_window') and utc(r['observation']['fill_window']['start']).astimezone(NY).hour==hour]
            rollover.append({'model':mode,'fill_window_start_hour_NY':hour,**metric(part)})
    return monthly,hourly,rollover


def csv_write(path,rows):
    with open(path,'w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def build(root,out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=True)
    prior=Y.load(root/'minute/unknown-report/REPORT.json');proof=Y.load(root/'proof/REPORT.json')
    if prior['status']!='COMPLETE' or proof['status']!='COMPLETE':raise ValueError('Incomplete source report')
    fixes={a['order_id']:a for a in Y.load(root/'proof/details.json.gz') if a['status']=='PROVEN_LOSS'}
    rows=[];matched=[];used=set();source_hashes={}
    for pair,summary in sorted(prior['markets'].items()):
        p=root/'year'/('year-12-'+pair)/'checkpoint.json.gz'
        if digest(p)!=summary['source_checkpoint_sha256']:raise ValueError('Checkpoint hash mismatch')
        source_hashes[pair]=digest(p);book=Y.load(p)['book']
        for a in Y.load(root/'minute'/('unknown-'+pair)/'trades.json.gz'):
            ident=a['order_id']
            if ident not in book:raise ValueError('Unknown correction order')
            if a['status'] in ('RESOLVED','OPEN'):book[ident]=amend(book[ident],a)
        for ident in list(book):
            if ident in fixes:book[ident]=amend(book[ident],fixes[ident],stop=True);used.add(ident)
        for ident,r in book.items():
            r['pair']=pair;r['order_id']=ident
            if r['observation']['outcome'] in CLOSED and not r.get('closed_at'):raise ValueError('Missing close timestamp')
            rows.append(r)
            if pair in prior['matched_markets']:matched.append(r)
    if used!=fixes.keys():raise ValueError('Unused correction')
    expected={r['model']:r for r in proof['models']}
    totals={mode:metric([r for r in matched if r['mode']==mode]) for mode in expected}
    for mode,s in totals.items():
        if abs(s['gross_R']-expected[mode]['updated_gross_R'])>1e-7 or s['unknown']!=expected[mode]['remaining_unknown']:
            raise ValueError('Corrected total does not reconcile: '+mode)
    for family in ('kk_aligned','recognition'):
        cohorts=[]
        for rr in (1,2,3):
            cohort={r['source_order_id']:(r['order']['entry_ticks'],r['order']['stop_ticks'],r['order']['clock'],r['pair']) for r in matched if r['mode']==family+f'_{rr}R'}
            cohorts.append(cohort)
        if not cohorts[0]==cohorts[1]==cohorts[2]:raise ValueError('RR entry cohorts differ')
    end=utc(next(iter(prior['markets'].values()))['end']);months=[f'2026-{m:02d}' for m in range(1,end.month+1)]
    monthly,hourly,rollover=aggregate(matched,months)
    csv_write(out/'monthly.csv',monthly);csv_write(out/'submission_hours_NY.csv',hourly);csv_write(out/'rollover_fill_windows_NY.csv',rollover)
    flat=[]
    for r in rows:
        o=r['order'];obs=r['observation'];fill=obs.get('fill_window') or {}
        flat.append({'pair':r['pair'],'model':r['mode'],'order_id':r['order_id'],'matched_market':r['pair'] in prior['matched_markets'],
            'entry_time_UTC':o['clock']['available_at'],'fill_window_start':fill.get('start'),'fill_window_end':fill.get('end'),
            'close_observed_UTC':r.get('closed_at'),'outcome':obs['outcome'],'gross_R':obs.get('net_r')})
    csv_write(out/'corrected_orders.csv',flat)
    Y.dump(out/'REPORT.json',{'status':'COMPLETE','source_runs':[42371042901,42499187752,42516446781],
        'cutoff':end,'checkpoint_sha256':source_hashes,'matched_markets':prior['matched_markets'],
        'totals':totals,'monthly':monthly,'submission_hours_NY':hourly,'rollover_fill_windows_NY':rollover})
    lines=['# Corrected monthly Bishop results','',f'Cutoff: {end.isoformat()}. November is partial. 26 common eligible markets.',
        'Gross zero-cost R. Unknown/open outcomes excluded from profit. Three exits are alternatives, not simultaneous allocations.',
        'Months use UTC terminal-event observation time. Original hourly exits retain hourly precision; minute corrections retain minute precision.',
        'Monthly cancellation/expiry/unknown counts below belong to orders CREATED that month, evaluated at the final cutoff—not events occurring that month.',
        'NY hours are DST-aware. Submission-hour results do not establish actual fill-hour profitability. Fill-window rollover buckets are approximate, not tick timestamps. No news/spread costs or rollover filter are simulated.']
    for mode in totals:
        lines+=['',f'## {mode}','','| Month | Created | Fills observed | Closed wins | Closed losses | Gross R | Cumulative R | Unknown* | Open* | Cancelled/expired* |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        for r in monthly:
            if r['model']==mode:lines.append(f"| {r['month_UTC']} | {r['orders_created']} | {r['fills_observed']} | {r['closed_wins']} | {r['closed_losses']} | {r['realized_gross_R']:.2f} | {r['cumulative_gross_R']:.2f} | {r['entry_cohort_unknown_at_cutoff']} | {r['entry_cohort_open_at_cutoff']} | {r['entry_cohort_cancelled']+r['entry_cohort_expired']} |")
    lines+=['','* Entry-month cohorts at final cutoff. CSVs include every submission hour, 16/17/18 NY fill windows, and corrected order ledger. Original reports remain unchanged.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='saved');p.add_argument('--out',default='report');a=p.parse_args();build(a.root,a.out)

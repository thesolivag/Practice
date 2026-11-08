"""Execution-only M1 refinement of a pinned yearly cohort. Never detect new trades."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import time

from slk import bishop_year_replay as Y
from bishop.v2.types import Bar, utc, jsonable
from bishop.v2.simulation import simulate, Costs
from slk.bishop_paper import thaw_order

SOURCE_RUN = 42371042901
SOURCE_SHA = '861549cbd919021905ad721f9799f969a5ceacf8'
SIM_SHA = '78c748e435e09e78b421a78b490ab26747db248381450f67de5d4df2164b6601'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_minutes(coarse, rows, inst):
    """Require every minute and exact rollup; never fill absent prices."""
    bars=[]
    for row in rows:
        at=datetime.fromtimestamp(int(row[0]), timezone.utc)
        prices=[]
        for value in row[1:5]:
            tick=Decimal(str(value))/inst.tick_size
            if not tick.is_finite() or abs(tick-tick.to_integral_value())>Decimal('0.000001'):
                raise ValueError('OFF_GRID_MINUTE')
            prices.append(int(tick.to_integral_value()))
        bars.append(Bar(inst.symbol,'M1',at,at+timedelta(minutes=1),*prices,
                        at+timedelta(minutes=1),inst.source_id))
    bars.sort(key=lambda b:b.start)
    wanted=[coarse.start+timedelta(minutes=i) for i in range(60)]
    if [b.start for b in bars]!=wanted:
        raise ValueError('MISSING_OR_DUPLICATE_MINUTES')
    actual=(bars[0].open_ticks,max(b.high_ticks for b in bars),min(b.low_ticks for b in bars),bars[-1].close_ticks)
    if actual!=(coarse.open_ticks,coarse.high_ticks,coarse.low_ticks,coarse.close_ticks):
        raise ValueError('M1_H1_PRICE_MISMATCH')
    return tuple(bars)


def censor_event(result):
    return next((e for e in result['events'] if e.kind=='EXECUTION_CENSORED'),None)


def refine(row, feed, end, loader, max_hours=128):
    """Replace only ambiguous H1s, reusing the unchanged execution engine."""
    original=jsonable(row)
    order=thaw_order(row['order']);actions=row['actions'];inst=feed['instrument']
    base=tuple(b for b in feed['bars'] if b.end>order.available_at and b.available_at<=end)
    result=simulate((order,),base,inst,Costs(),end,actions,calendar=inst.calendar_id)
    obs=jsonable(result['observations'][0])
    audit={'order_id':order.id,'mode':row['mode'],'original':original['observation'],
           'order':original['order'],'actions':original['actions'],'refined_hours':[],
           'status':'UNRESOLVED','reason':None,'observation':original['observation']}
    if obs!=original['observation']:
        audit['reason']='ORIGINAL_EXECUTION_NOT_REPRODUCED';return audit
    first=censor_event(result)
    # Checkpoints stop collecting cancellations once censored. If refined fill
    # is not proven by that point, later pending management is not recoverable.
    freeze_at=first.available_at if first else end
    replacements={}; by_id={b.id:b for b in base}
    for _ in range(max_hours+1):
        obs=jsonable(result['observations'][0]);event=censor_event(result)
        if obs['outcome']!='CENSORED':
            fill=obs.get('fill_window')
            if not fill or utc(fill['end'])>freeze_at:
                audit['reason']='PENDING_MANAGEMENT_AFTER_ORIGINAL_CENSOR_UNAVAILABLE'
                return audit
            audit.update(status='RESOLVED' if obs['outcome'] in ('WIN','LOSS','BREAK_EVEN') else 'OPEN',
                         observation=obs,reason=None,
                         events=jsonable(result['events']))
            return audit
        if obs.get('censor_reason')!='UNRESOLVED_INTRABAR_SEQUENCE' or not event or not event.bar_ids:
            audit['reason']=obs.get('censor_reason') or 'NO_CENSOR_BAR';return audit
        coarse=by_id.get(event.bar_ids[0])
        if coarse is None:
            audit['reason']='STILL_AMBIGUOUS_WITHIN_ONE_MINUTE';return audit
        if len(replacements)>=max_hours:
            audit['reason']='REFINEMENT_HOUR_BUDGET';return audit
        try:
            fine=loader(coarse)
        except Exception as exc:
            # Do not put broker/DB exception text or credentials in artifacts.
            audit['reason']=str(exc) if isinstance(exc,ValueError) and str(exc) in {
                'OFF_GRID_MINUTE','MISSING_OR_DUPLICATE_MINUTES','M1_H1_PRICE_MISMATCH',
                'BROKER_H1_PRICE_MISMATCH','BROKER_FETCH_UNAVAILABLE','JOB_TIME_BUDGET'} else 'BROKER_FETCH_UNAVAILABLE'
            return audit
        replacements[coarse.id]=fine;audit['refined_hours'].append(coarse.start.isoformat())
        hybrid=tuple(b for h in base for b in replacements.get(h.id,(h,)))
        result=simulate((order,),hybrid,inst,Costs(),end,actions,calendar=inst.calendar_id)
    raise AssertionError('bounded refinement loop')


def broker_rows(pair, coarse, inst):
    """One hour per connection/lease; yield shared feeds between requests."""
    if inst.venue=='deriv':
        from slk.deriv import Feed
        with Feed() as client:
            client.prefetch([pair]);symbol=client.info(pair)['symbol']
            def get(granularity):
                r=client.request({'ticks_history':symbol,'start':int(coarse.start.timestamp()),
                    'end':str(int(coarse.end.timestamp())-1),'style':'candles',
                    'granularity':granularity,'count':60 if granularity==60 else 1})
                return [(c['epoch'],c['open'],c['high'],c['low'],c['close']) for c in r['candles']]
            return get(3600),get(60),{'provider':'deriv','symbol':symbol}
    if inst.venue!='ctrader':raise ValueError('BROKER_FETCH_UNAVAILABLE')
    from slk import db,jobs
    from slk.bishop_year_jobs import research_feed_lock
    from ctrader.client import CTraderClient
    from ctrader import tokens
    # Shared refresh tokens and scanner feed leases are respected. No trade API.
    with research_feed_lock(db,wait=240):
        with jobs.feed_lock(db,wait=0,name='slk_personal_feed') as acquired:
            if not acquired:raise ValueError('BROKER_FETCH_UNAVAILABLE')
            with CTraderClient(env='demo',settings=tokens.default_settings(strict=True),timeout=15) as client:
                client.get_symbols([pair]);info=client.symbol(pair)
                h=client.trendbar_rows(pair,'H1',coarse.start,coarse.end)
                m=client.trendbar_rows(pair,'M1',coarse.start,coarse.end)
                return h,m,{'provider':'ctrader','environment':client.env,
                           'symbol':info['name'],'symbol_id':info['symbol_id']}


class MinuteLoader:
    def __init__(self,pair,inst,root,deadline):
        self.pair,self.inst,self.root,self.deadline=pair,inst,Path(root),deadline
        self.cache={};self.root.mkdir(parents=True,exist_ok=True)
    def __call__(self,coarse):
        if coarse.id in self.cache:
            result=self.cache[coarse.id]
            if isinstance(result,Exception):raise result
            return result
        if time.monotonic()>self.deadline:raise ValueError('JOB_TIME_BUDGET')
        for attempt in range(3):
            try:
                h,rows,meta=broker_rows(self.pair,coarse,self.inst)
                # The frozen source did not retain broker environment metadata;
                # refetch its H1 on the configured original demo provider first.
                expected=(coarse.open_ticks,coarse.high_ticks,coarse.low_ticks,coarse.close_ticks)
                if (len(h)!=1 or int(h[0][0])!=int(coarse.start.timestamp()) or
                    tuple(self.inst.to_ticks(Decimal(str(v))) for v in h[0][1:5])!=expected):
                    raise ValueError('BROKER_H1_PRICE_MISMATCH')
                result=validate_minutes(coarse,rows,self.inst)
                path=self.root/(coarse.start.strftime('%Y%m%dT%H%M')+'.json.gz')
                Y.dump(path,{'metadata':meta,'downloaded_at':datetime.now(timezone.utc),
                    'coarse':coarse,'h1_rows':h,'m1_rows':rows,'validation':'60_MINUTES_EXACT_H1_ROLLUP'})
                self.cache[coarse.id]=result;return result
            except ValueError as exc:
                self.cache[coarse.id]=exc;raise
            except Exception:
                if attempt<2:time.sleep(2*(attempt+1))
        error=ValueError('BROKER_FETCH_UNAVAILABLE');self.cache[coarse.id]=error;raise error


def prepare(root):
    root=Path(root);manifest=Y.load(root/'manifest.json')
    pairs=[]
    for pair,meta in manifest['markets'].items():
        if meta['status']!='READY':continue
        if digest(root/(pair+'.json.gz'))!=meta['sha256']:raise ValueError('Frozen input hash mismatch')
        pairs.append(pair)
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('pairs='+json.dumps(sorted(pairs))+'\n')


def run_pair(args):
    if digest(Path(__file__).parents[1]/'bishop/v2/simulation.py')!=SIM_SHA:
        raise ValueError('Execution engine changed since source run')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    root=Path(args.inputs);manifest=Y.load(root/'manifest.json')
    if digest(root/(args.pair+'.json.gz'))!=manifest['markets'][args.pair]['sha256']:
        raise ValueError('Frozen input hash mismatch')
    feed=Y.feed_file(root/(args.pair+'.json.gz'));end=utc(manifest['end'])
    checkpoint=Path(args.checkpoint);state=Y.load(checkpoint)
    unknown=[r for r in state['book'].values() if r['observation']['outcome']=='CENSORED']
    loader=MinuteLoader(args.pair,feed['instrument'],out/'minute-evidence',time.monotonic()+90*60)
    audits=[]
    for i,row in enumerate(unknown):
        audits.append(refine(row,feed,end,loader))
        Y.dump(out/'trades.json.gz',audits)
        counts=Counter(a['status'] for a in audits)
        print(json.dumps({'pair':args.pair,'processed':i+1,'unknown_orders':len(unknown),'status':counts}),flush=True)
    reasons=Counter(a['reason'] for a in audits if a['reason'])
    models={}
    for mode in sorted({r['mode'] for r in state['book'].values()}):
        items=[a for a in audits if a['mode']==mode]
        models[mode]={'original_unknown':len(items),'new_outcomes':dict(Counter(
            a['observation']['outcome'] if a['status']!='UNRESOLVED' else 'CENSORED' for a in items)),
            'resolved_gross_R':sum(float(a['observation']['net_r']) for a in items if a['status']=='RESOLVED'),
            'reasons':dict(Counter(a['reason'] for a in items if a['reason']))}
    evidence={p.name:digest(p) for p in (out/'minute-evidence').glob('*.gz')}
    Y.dump(out/'summary.json',{'pair':args.pair,'source_run':SOURCE_RUN,'source_sha':SOURCE_SHA,
        'source_checkpoint_sha256':digest(checkpoint),'frozen_input_sha256':digest(root/(args.pair+'.json.gz')),
        'end':end,'unknown_orders':len(unknown),'processed':len(audits),'reasons':reasons,'models':models,
        'evidence_sha256':evidence,'scope':'Frozen cohort execution only; no new signals, freed capacity or later pending cancellations reconstructed.'})


def collect(root,out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=True)
    prior=Y.load(root/'original-report/REPORT.json');summaries={}
    for path in root.glob('unknown-*/summary.json'):
        s=Y.load(path);summaries[s['pair']]=s
    missing=sorted(set(prior['completed'])-summaries.keys())
    combined={};reasons=Counter()
    for pair in prior['matched_comparison_markets']:
        if pair not in summaries:continue
        for mode,s in summaries[pair]['models'].items():
            v=combined.setdefault(mode,{'original_unknown':0,'new_outcomes':Counter(),'resolved_gross_R':0.0})
            v['original_unknown']+=s['original_unknown'];v['new_outcomes'].update(s['new_outcomes'])
            v['resolved_gross_R']+=s['resolved_gross_R']
        reasons.update(summaries[pair]['reasons'])
    report={'status':'COMPLETE' if not missing else 'PARTIAL','missing_markets':missing,
        'source_run':SOURCE_RUN,'source_sha':SOURCE_SHA,'matched_markets':prior['matched_comparison_markets'],
        'original_matched_results':prior['combined_matched_markets'],'unknown_refinement':combined,
        'reasons':reasons,'markets':summaries,
        'limitations':['Only original unknowns; original results immutable.','Same-hour M1 ambiguity stays unknown; no tick assumptions.',
        'M1 must contain all 60 minutes and exactly match frozen H1.','Frozen cohort only: original capacity and subsequent pending management are not rerun.',
        'Gross zero-cost execution; no live-return guarantee.']}
    Y.dump(out/'REPORT.json',report)
    lines=['# Bishop unknown-trade M1 refinement',f"Status: {report['status']}. Missing markets: {missing}.",
        '', 'Original yearly run: '+str(SOURCE_RUN), '',
        '| Model | Unknown examined | Newly won | Newly lost | Still unknown | Open | Added gross R |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for mode,s in sorted(combined.items()):
        c=s['new_outcomes'];lines.append(f"| {mode} | {s['original_unknown']} | {c['WIN']} | {c['LOSS']} | {c['CENSORED']} | {c['OPEN']} | {s['resolved_gross_R']:.2f} |")
    lines+=['','Unresolved reasons: '+json.dumps(reasons),'',*report['limitations']]
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','pair','collect'])
    p.add_argument('--inputs',default='year-inputs');p.add_argument('--pair');p.add_argument('--checkpoint')
    p.add_argument('--out',default='result');p.add_argument('--results',default='results');args=p.parse_args()
    if args.command=='prepare':prepare(args.inputs)
    elif args.command=='pair':run_pair(args)
    else:collect(args.results,args.out)

if __name__=='__main__':main()

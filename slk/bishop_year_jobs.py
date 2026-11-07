"""GitHub job preparation/reporting for the isolated yearly replay."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
import re
from pathlib import Path
import time
from slk import bishop_year_replay as Y



@contextmanager
def research_feed_lock(db, wait=300):
    """Poll nonblocking acquisition; GET_LOCK(wait) exceeds DB read timeout."""
    from slk.jobs import feed_lock
    deadline=time.monotonic()+wait
    while True:
        with feed_lock(db,wait=0) as acquired:
            if acquired:
                yield True
                return
        if time.monotonic()>=deadline:
            raise RuntimeError('Broker feed busy; no replay launched')
        time.sleep(min(5,max(0,deadline-time.monotonic())))


def prepare(root):
    from slk import db, tenancy, live, store, settings, instruments
    from slk.jobs import feed_lock
    from bishop.v2.types import Instrument, Bar
    from bishop.v2.aggregation import expected_slots
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    end=datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)
    end=min(end,datetime(2027,1,1,tzinfo=timezone.utc))
    start=datetime(2026,1,1,tzinfo=timezone.utc);warmup=start-timedelta(days=live.HISTORY_DAYS)
    with tenancy.scope(tenancy.owner_id()):cfg,_,vals=live.build_cfg(db.get_settings())
    selected=vals['pairs'] or settings.PAIRS
    config={'cfg':cfg,'stories':vals['stories'],'avoid_pairs':vals['avoid_pairs']}
    # Only strategy inputs are exported. Never dump the settings table, tokens,
    # user records, Telegram destinations or database connection information.
    Y.dump(root/'config.json',config)
    manifest={'version':Y.VERSION,'commit':os.environ.get('GITHUB_SHA'),'start':start.isoformat(),
        'end':end.isoformat(),'selected':selected,'markets':{},'config_sha256':hashlib.sha256((root/'config.json').read_bytes()).hexdigest(),
        'interpretation':'Current settings applied throughout the historical year; historical preferences and actual past web rows are not reconstructed.'}
    pairs=[]
    with research_feed_lock(db) as acquired:
        if not acquired:raise RuntimeError('Broker feed busy; no replay launched')
        try:
            for pair in selected:
                if not re.fullmatch(r'[A-Z0-9_]{1,32}',pair):raise ValueError('Invalid selected market key')
                continuous=instruments.deriv_continuous(pair)
                if pair not in settings.PAIRS and not continuous:
                    manifest['markets'][pair]={'status':'UNSUPPORTED_CALENDAR'};continue
                try:
                    # Separate local store/cache; no save to the live cache and no
                    # fallback source substitution. Shared broker token refresh
                    # uses the existing token manager under the feed lock.
                    saved=store.update(pair,now=end,since=warmup,source='deriv' if continuous else 'ctrader')
                    source='deriv' if continuous else 'ctrader'
                    if saved.src!=source:raise ValueError('Primary source unavailable')
                    digits=(saved.sym or {}).get('digits')
                    if digits is None:raise ValueError('Price precision unavailable')
                    tick=Decimal(1).scaleb(-int(digits));calendar='24x7_utc_v1' if continuous else 'fx_ny_v1'
                    inst=Instrument(pair,str(tick),str(instruments.pip(pair)),calendar,
                        'utc_epoch_v1' if continuous else 'ny17_wall_v2','MID' if continuous else 'BID',source+':'+pair,source)
                    h=saved.frame(int(warmup.timestamp()));bars=[]
                    for at,row in h.iterrows():
                        at=at.to_pydatetime();close=at+timedelta(hours=1)
                        if close>end:continue
                        prices=[]
                        for key in ('open','high','low','close'):
                            raw=Decimal(str(row[key]));rounded=raw.quantize(tick)
                            if abs(raw-rounded)>tick/Decimal(1000):raise ValueError('Off-grid price')
                            prices.append(inst.to_ticks(rounded))
                        bars.append(Bar(pair,'H1',at,close,*prices,close,inst.source_id))
                    if not bars or bars[0].start>start-timedelta(days=35):raise ValueError('Missing Bishop warmup at year start')
                    wanted=set(expected_slots(start,end,'H1',calendar));present={b.start for b in bars}
                    if not wanted & present:raise ValueError('No year-to-date candles')
                    path=root/(pair+'.json.gz')
                    Y.dump(path,{'instrument':inst,'bars':bars,'manifest':{'calendar':calendar,'base_tf':'H1'}})
                    manifest['markets'][pair]={'status':'READY','first':bars[0].start.isoformat(),'last':bars[-1].end.isoformat(),
                        'expected_ytd_hours':len(wanted),'present_ytd_hours':len(wanted & present),'missing_ytd_hours':len(wanted-present),
                        'kk_full_warmup':bars[0].start<=warmup+timedelta(days=4),
                        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                    pairs.append(pair)
                    print(json.dumps({'pair':pair,**manifest['markets'][pair]}),flush=True)
                except Exception as exc:
                    manifest['markets'][pair]={'status':'UNAVAILABLE','error_type':type(exc).__name__}
                    print(json.dumps({'pair':pair,'status':'UNAVAILABLE','error_type':type(exc).__name__}),flush=True)
                Y.dump(root/'manifest.json',manifest)
        finally:store.close_feed()
    if not pairs:raise RuntimeError('No supported selected market has the required historical feed')
    # Quarter boundaries preserve the checkpoint across jobs; open trades and
    # frozen entry evidence are carried over, never reset at the boundary.
    ends=[min(end,datetime(2026,m,1,tzinfo=timezone.utc)).isoformat() for m in (4,7,10)] + [end.isoformat()]
    manifest['pairs']=pairs;manifest['segment_ends']=ends;Y.dump(root/'manifest.json',manifest)
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:
        f.write('pairs='+json.dumps(pairs)+'\n')
    return manifest


def pilot(root,out):
    from bishop.v2.types import utc
    root=Path(root);m=Y.load(root/'manifest.json');pair=m['pairs'][0]
    feed=Y.feed_file(root/(pair+'.json.gz'));config=Y.load(root/'config.json')
    start=utc(m['start']);end=utc(m['end']);clocks=[b.available_at for b in feed['bars'] if start<=b.available_at<=end]
    if len(clocks)<4:raise ValueError('Insufficient replay pilot hours')
    # The same deterministic decision must survive a physically removed future
    # and a poisoned future. Execution totals are NOT compared across cutoffs.
    at=clocks[0];cut=Y.prefix(feed,at);full_state=Y.new_state();cut_state=Y.new_state()
    t=time.monotonic()
    a=Y.decision(feed,Y.dataframe(feed),at,start,config,full_state,{})
    b=Y.decision(cut,Y.dataframe(cut),at,start,config,cut_state,{})
    if a!=b:raise AssertionError('Prefix audit failed: future data changed a decision')
    from dataclasses import replace
    poisoned={**feed,'bars':tuple(replace(x,open_ticks=x.open_ticks*2,high_ticks=x.high_ticks*2,
        low_ticks=x.low_ticks*2,close_ticks=x.close_ticks*2) if x.available_at>at else x for x in feed['bars'])}
    c=Y.decision(poisoned,Y.dataframe(poisoned),at,start,config,Y.new_state(),{})
    if a!=c:raise AssertionError('Poisoned-future audit failed')
    state=Y.replay(feed,config,start,clocks[min(23,len(clocks)-1)],checkpoint=Path(out)/'checkpoint.json.gz')
    elapsed=time.monotonic()-t;seconds=elapsed/(len(state['audit'])+3)
    check={'status':'PASS','pair':pair,'hours':len(state['audit']),'physical_prefix_equal':a==b,
        'poisoned_future_equal':a==c,'seconds_per_hour':seconds,'estimated_24x7_quarter_minutes':seconds*24*92/60,
        'note':'One feed pilot plus unit tests; all full-run decisions still receive physical prefixes.'}
    Y.dump(Path(out)/'pilot.json',check);print(json.dumps(check),flush=True)
    if check['estimated_24x7_quarter_minutes']>300:
        raise RuntimeError('Measured replay exceeds bounded job budget; subdivide segments before launching full run')


def segment(root,pair,number,out,resume=None):
    root=Path(root);m=Y.load(root/'manifest.json');feed=Y.feed_file(root/(pair+'.json.gz'))
    state=Y.thaw_state(Y.load(resume)) if resume else Y.new_state()
    end=m['segment_ends'][number-1];out=Path(out);out.mkdir(parents=True,exist_ok=True)
    try:
        state=Y.replay(feed,Y.load(root/'config.json'),m['start'],end,state,checkpoint=out/'checkpoint.json.gz')
        Y.dump(out/'summary.json',Y.report(state,feed,'COMPLETED_SEGMENT',m['start'],end))
    except Exception as exc:
        Y.dump(out/'checkpoint.json.gz',state)
        Y.dump(out/'failure.json',{'error_type':type(exc).__name__,'message':str(exc)[:300]})
        raise


def collect(inputs,results,out):
    from bishop.v2.types import utc
    inputs=Path(inputs);results=Path(results);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    m=Y.load(inputs/'manifest.json');summaries=[];all_rows=[];completed=[];incomplete=[]
    for pair in m['pairs']:
        files=list(results.glob(f'year-*-{pair}/checkpoint.json.gz'))
        if not files:incomplete.append(pair);continue
        states=[Y.thaw_state(Y.load(p)) for p in files]
        state=max(states,key=lambda s:s['audit'][-1]['at'] if s['audit'] else '')
        feed=Y.feed_file(inputs/(pair+'.json.gz'))
        required=max(b.available_at for b in feed['bars'] if b.available_at<=utc(m['end']))
        done=bool(state['audit']) and utc(state['audit'][-1]['at'])==required
        (completed if done else incomplete).append(pair)
        s=Y.report(state,feed,'COMPLETED' if done else 'INCOMPLETE',m['start'],m['end']);summaries.append(s)
        # Incomplete markets are visibly excluded from combined totals.
        if done:all_rows.extend(state['book'].values())
    modes=sorted({r['mode'] for r in all_rows})
    combined={mode:Y.summarize([r for r in all_rows if r['mode']==mode]) for mode in modes}
    excluded={p:v for p,v in m['markets'].items() if v['status']!='READY'}
    report={'status':'COMPLETE' if not incomplete and not excluded else 'PARTIAL','completed':completed,
        'incomplete':incomplete,'excluded':excluded,'data_gaps':{p:v['missing_ytd_hours'] for p,v in m['markets'].items() if v.get('missing_ytd_hours')},'manifest':m,'markets':summaries,'combined_completed_markets':combined}
    Y.dump(out/'REPORT.json',report)
    lines=['# Bishop 2026 prefix-only backtest','',f"Status: **{report['status']}**. Completed markets: {len(completed)}. Incomplete: {len(incomplete)}. Unavailable/unsupported: {len(excluded)}.",'',
        'Period: '+m['start']+' through '+m['end']+'. Frozen code: `'+str(m['commit'])+'`.','',
        'Every decision uses only physically available closed candles. Current KK rules/preferences are reconstructed historically. Original baseline means current Bishop rules without the KK gate, not an archived older software version.','',
        '| Model / exit | Orders | Resolved | Wins | Losses | Open | Unknown | Total gross R | Win % | Closed drawdown R |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for mode,s in combined.items():
        c=s['outcomes'];wr='—' if s['win_rate'] is None else f"{s['win_rate']:.1f}"
        lines.append(f"| {mode} | {s['orders']} | {s['resolved']} | {c.get('WIN',0)} | {c.get('LOSS',0)} | {c.get('OPEN',0)} | {c.get('CENSORED',0)} | {s['total_R']:.2f} | {wr} | {s['closed_drawdown_R']:.2f} |")
    lines+=['','1R/2R/3R are separate full exits on the same enrolled entries. They are not hours, partial exits, or simultaneous account allocations. Recognition is a new research execution cohort; its production panel still does not place orders.',
        '', 'Unknown/open outcomes are not wins or losses. Gross totals exclude costs; per-market JSON includes explicit 1- and 2-pip cost hurdles (not a historical spread/fill simulation). Closed drawdown excludes floating loss. Results are not a live-return guarantee.',
        '', 'Quarter checkpoints preserve open positions and frozen geometry. Incomplete markets are excluded from combined totals. Inspect REPORT.json for coverage, exclusions, paired same-entry exits, cost hurdles and per-market details.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('job',choices=['prepare','pilot','segment','collect'])
    p.add_argument('--inputs',default='year-inputs');p.add_argument('--out',default='year-results');p.add_argument('--pair')
    p.add_argument('--number',type=int);p.add_argument('--resume');p.add_argument('--results',default='collected')
    a=p.parse_args()
    if a.job=='prepare':prepare(a.inputs)
    elif a.job=='pilot':pilot(a.inputs,a.out)
    elif a.job=='segment':segment(a.inputs,a.pair,a.number,a.out,a.resume)
    else:collect(a.inputs,a.results,a.out)


if __name__=='__main__':main()

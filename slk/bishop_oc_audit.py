"""Prefix-only audit of OC alternatives at recorded A/V decisions.

Reference eligibility is frozen before inspecting later prices. Touch diagnostics
are not fills or P&L. This audit neither rewrites baseline orders nor trades.
"""
import argparse,gzip,json,hashlib,os
from collections import Counter,defaultdict
from datetime import timedelta
from pathlib import Path
from bishop.v2.types import utc
from bishop.v2.entries import _engulfs
from bishop.v2.aggregation import aggregate,expected_slots
from slk import bishop_year_replay as Y
from slk.bishop_entry_reference import OC_MODELS,AV_MODELS,episode_key


def immediate_oc(bars,pair_ids,side,now,gap_ticks=0):
    """The specific OC junction: two opposite candles, then a closed engulf."""
    known=[b for b in bars if b.complete and b.end<=now and b.available_at<=now]
    if len(pair_ids)!=2:return {'status':'NO_SAVED_ENGULF_PAIR'}
    indices={b.id:i for i,b in enumerate(known)}
    if any(i not in indices for i in pair_ids):return {'status':'PATTERN_BARS_UNAVAILABLE'}
    ai,bi=(indices[i] for i in pair_ids)
    if bi!=ai+1 or ai<1:return {'status':'NO_PRECEDING_ADJACENT_CANDLE'}
    p,a,b=known[ai-1],known[ai],known[bi]
    if p.segment_id!=a.segment_id or p.end!=a.start or a.end!=b.start:return {'status':'PATTERN_GAP'}
    if not _engulfs(a,b,side):return {'status':'NOT_STRICT_ADJACENT_ENGULF'}
    if p.side!=a.side or p.side is None:return {'status':'NO_TWO_SAME_DIRECTION_OC_CANDLES'}
    price=p.close_ticks
    crossed=b.open_ticks<=price<b.close_ticks if side=='BUY' else b.close_ticks<price<=b.open_ticks
    if not crossed:return {'status':'JUNCTION_NOT_CROSSED_BY_ENGULF'}
    return {'status':'OC_JUNCTION_GAP' if abs(p.close_ticks-a.open_ticks)>gap_ticks else 'KNOWN_JUNCTION','gap_ticks':a.open_ticks-p.close_ticks,'allowed_gap_ticks':gap_ticks,'price_ticks':price,'bar_ids':[p.id,a.id],
        'engulf_bar_ids':[a.id,b.id],'available_at':max(p.available_at,a.available_at).isoformat(),
        'engulf_closed_at':b.available_at.isoformat()}


def freeze_reference(row,result,bars,policy):
    """Only detector output and decision-prefix candles enter this function."""
    o,s=row['order'],row['setup'];now=utc(o['clock']['available_at'])
    out={'order_id':o['id'],'pair':o['instrument'],'mode':row['mode'],'decision':now.isoformat(),
         'tf':o['tf'],'side':o['side'],'av_ticks':o['entry_ticks'],'setup_id':s['id']}
    pair=s['details'].get('confirmation_protection_bar_ids',[])
    junction=immediate_oc(bars,pair,o['side'],now,policy.oc_gap_ticks);out['junction']=junction
    reproduced=next((x for x in result['setups'] if x['id']==s['id']),None)
    if reproduced is None or reproduced['entry_ticks']!=o['entry_ticks'] or reproduced['status']!='ELIGIBLE':
        return {**out,'status':'BASELINE_NOT_REPRODUCED','alternatives':[]}
    if junction['status']!='KNOWN_JUNCTION':return {**out,'status':junction['status'],'alternatives':[]}
    levels={l['id']:l for l in result['diagnostics']['structures'][o['tf']]['levels']}
    matches=[]
    for candidate in result['setups']:
        if candidate['model'] not in OC_MODELS or candidate['story_id']!=s['story_id'] or candidate['tf']!=o['tf'] or candidate['side']!=o['side']:continue
        if utc(candidate['clock']['available_at'])!=now:continue
        level=levels.get(candidate['level_id'])
        if not level or level['kind']!='OC' or set(level['bar_ids'])!=set(junction['bar_ids']) or utc(level['available_at'])>now:continue
        if candidate['entry_ticks']!=junction['price_ticks']:continue
        matches.append({'setup_id':candidate['id'],'model':candidate['model'],'level_id':candidate['level_id'],
            'entry_ticks':candidate['entry_ticks'],'stop_ticks':candidate['stop_ticks'],'target_ticks':candidate['target_ticks'],
            'engine_status':candidate['status'],'unresolved_reasons':candidate['details'].get('unresolved_reasons',[])})
    return {**out,'status':'ENGINE_ELIGIBLE_OC' if any(m['engine_status']=='ELIGIBLE' for m in matches) else 'OC_NOT_ENGINE_ELIGIBLE',
            'alternatives':matches,'scope':'Same story/timeframe/direction/decision and exact immediate OC junction. Full alternative admission/capacity and profitability are not established.'}


def touches(bars,now,deadline,oc,av,calendar):
    """Observe subsequent exact-price touches; never infer intrabar order."""
    if deadline<=now:return {'status':'EMPTY_WINDOW'}
    rows=[b for b in bars if b.complete and b.start>=now and b.end<=deadline and b.available_at<=deadline]
    wanted=set(expected_slots(now,deadline,'H1',calendar));present={b.start for b in rows}
    missing=wanted-present
    def first(price):return next((b for b in rows if b.low_ticks<=price<=b.high_ticks),None)
    o,a=first(oc),first(av)
    if missing:status='INCOMPLETE_WINDOW'
    elif o and not a:status='OC_ONLY_PRICE_TOUCH'
    elif a and o:status='BOTH_SAME_H1_ORDER_UNKNOWN' if a.id==o.id else 'BOTH_PRICE_TOUCHED'
    elif a:status='AV_ONLY_PRICE_TOUCH'
    else:status='NEITHER_PRICE_TOUCHED'
    return {'status':status,'window_start':now.isoformat(),'window_end':deadline.isoformat(),'missing_h1_slots':len(missing),
            'oc_first_window':{'start':o.start.isoformat(),'end':o.end.isoformat()} if o else None,
            'av_first_window':{'start':a.start.isoformat(),'end':a.end.isoformat()} if a else None,
            'meaning':'Exact BID price touch, not executable fill or missed winning trade; spread and intrabar sequencing are not resolved.'}


def audit_pair(checkpoint,feed_path,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    state=Y.load(checkpoint);book=state['book'];feed=Y.feed_file(feed_path)
    # One record for each RR entry cohort; never count 2R/3R as extra entries.
    rows=[r for r in book.values() if r['order']['model'] in AV_MODELS and not r['mode'].endswith(('2R','3R'))]
    batches=defaultdict(list)
    for row in rows:batches[(row['order']['clock']['available_at'],row['mode'].startswith('recognition'))].append(row)
    findings=[];last=max(b.available_at for b in feed['bars'])
    for (at,later),batch in sorted(batches.items()):
        now=utc(at)
        # Physical prefix is mandatory even though detect() also enforces it.
        prefix=Y.prefix(feed,now,35);result,policy=Y.detect(prefix,now,later=later)
        frames={tf:aggregate(prefix['bars'],tf,feed['instrument'],now)['bars'] for tf in {r['order']['tf'] for r in batch}}
        for row in batch:
            frozen=freeze_reference(row,result,frames[row['order']['tf']],policy)
            peers=[r for r in book.values() if r['mode']==row['mode'] and r['order']['model'] in OC_MODELS and r['order']['clock']['available_at']==at]
            eligible={x['setup_id'] for x in frozen['alternatives'] if x['engine_status']=='ELIGIBLE'}
            frozen['oc_already_recorded']=any(r['setup']['id'] in eligible for r in peers)
            if frozen['status'] in ('ENGINE_ELIGIBLE_OC','OC_JUNCTION_GAP'):
                o=row['order'];deadlines=[last,now+timedelta(hours=24)]
                if o.get('expires_at'):deadlines.append(utc(o['expires_at']))
                for action in row.get('actions',[]):
                    if action.get('kind','').upper() in ('CANCEL','REPLACE') and utc(action['available_at'])>=now:deadlines.append(utc(action['available_at']))
                frozen['touches']=touches(feed['bars'],now,min(deadlines),frozen['junction']['price_ticks'],o['entry_ticks'],feed['instrument'].calendar_id)
            findings.append(frozen)
        Y.dump(out/'audit.json.gz',{'findings':findings,'completed_batches':len({(r['decision'],r['mode'].startswith('recognition')) for r in findings}),'expected_batches':len(batches),'code_commit':os.environ.get('GITHUB_SHA','LOCAL_CHECK'),'source_checkpoint_sha256':hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest(),'feed_sha256':hashlib.sha256(Path(feed_path).read_bytes()).hexdigest()})
        print(feed['instrument'].symbol,at,len(findings),'/',len(rows),flush=True)
    if not batches:Y.dump(out/'audit.json.gz',{'findings':[],'completed_batches':0,'expected_batches':0})


def report(root,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);rows=[];files=list(Path(root).glob('**/audit.json.gz'));incomplete=[]
    for p in files:
        d=Y.load(p);rows.extend(d['findings'])
        if d['completed_batches']!=d['expected_batches']:incomplete.append(str(p))
    counters={}
    for mode in sorted({r['mode'] for r in rows}):
        group=[r for r in rows if r['mode']==mode]
        counters[mode]={'av_orders_audited':len(group),'eligibility':dict(Counter(r['status'] for r in group)),
          'touches':dict(Counter(r['touches']['status'] for r in group if r.get('touches') and r['status']=='ENGINE_ELIGIBLE_OC')),
          'oc_only_with_no_recorded_oc_order':sum(r['status']=='ENGINE_ELIGIBLE_OC' and r.get('touches',{}).get('status')=='OC_ONLY_PRICE_TOUCH' and not r['oc_already_recorded'] for r in group),
          'gap_rule_exclusions':dict(Counter(str(r['junction'].get('gap_ticks')) for r in group if r['status']=='OC_JUNCTION_GAP')),
          'gap_excluded_oc_only_price_touches':sum(r['status']=='OC_JUNCTION_GAP' and r.get('touches',{}).get('status')=='OC_ONLY_PRICE_TOUCH' for r in group)}
    Y.dump(out/'REPORT.json',{'market_artifacts':len(files),'incomplete':incomplete,'results':counters,'findings':rows})
    lines=['# OC versus A/V reference audit','','Recorded A/V decisions only, original capacity-limited cohort. Not a complete search for ungenerated setups or a new profit backtest.',
      'Eligibility reconstructed on physical decision prefixes. Exact immediate two-candle OC junction, not any older crossed OC level.',
      'Subsequent price touches use H1 BID within original cancellation/expiry (maximum 24 hours). Missing data remains unresolved. A touch is not a fill or a win.',
      'An engine-eligible alternative is not proof that all portfolio/recognition admission gates would admit a second order.',
      f'Market artifacts: {len(files)}; incomplete: {len(incomplete)}.','', '| Strategy | A/V orders audited | Engine-eligible immediate OC | OC-only touch | OC-only with no recorded OC order |','|---|---:|---:|---:|---:|']
    for mode,c in counters.items():lines.append(f"| {mode} | {c['av_orders_audited']} | {c['eligibility'].get('ENGINE_ELIGIBLE_OC',0)} | {c['touches'].get('OC_ONLY_PRICE_TOUCH',0)} | {c['oc_only_with_no_recorded_oc_order']} |")
    lines+=['','## OC junction gap exclusions','', 'These references fail the current exact-junction rule. Their touches are diagnostic, not eligible trades.','']
    for mode,c in counters.items():lines.append(f"- {mode}: excluded gap sizes (ticks): {c['gap_rule_exclusions']}; OC-only touches among these: {c['gap_excluded_oc_only_price_touches']}")
    lines+=['','Detailed unresolved reasons and every examined order are in REPORT.json. Do not add these counts to the original P&L.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    if incomplete or len(files)!=26:raise RuntimeError('Partial audit: expected all 26 complete market artifacts')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['pair','report']);p.add_argument('--checkpoint');p.add_argument('--feed');p.add_argument('--root',default='audit-results');p.add_argument('--out',default='oc-audit');a=p.parse_args()
    if a.command=='pair':audit_pair(a.checkpoint,a.feed,a.out)
    else:report(a.root,a.out)

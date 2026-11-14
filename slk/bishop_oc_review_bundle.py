"""Build a separately labelled mini-app-compatible archive from NEW orders only.

No publishing, database write or Telegram delivery. Never graft old outcomes
onto corrected setups. Incomplete pairs are listed and excluded from the bundle.
"""
import os
from pathlib import Path
from slk.bishop_oc_replay import load,dump
from bishop.v2.types import utc


def build_bundle(inputs,results,out):
    inputs,results,out=Path(inputs),Path(results),Path(out)
    manifest=load(inputs/'manifest.json');entries=[];missing=[];matches=[]
    for pair in manifest['pairs']:
        files=list(results.glob(f'year-*-{pair}/checkpoint.json.gz'))
        if not files:missing.append(pair);continue
        states=[load(p) for p in files]
        state=max(states,key=lambda x:x['audit'][-1]['at'] if x['audit'] else '')
        feed=load(inputs/(pair+'.json.gz'))
        cutoff=max(utc(b['available_at']) for b in feed['bars'] if utc(b['available_at'])<=utc(manifest['end']))
        if not state['audit'] or utc(state['audit'][-1]['at'])!=cutoff:
            missing.append(pair);continue
        dump(out/(pair+'.json.gz'),feed)
        tick=float(feed['instrument']['tick_size']);groups={}
        flow_by_setup={p['setup_id']:f for f in (state.get('flow') or {}).get('flows',[]) for p in f.get('plans',[])}
        for row in state['book'].values():
            o=row['order'];s=row['setup'];mode=row['mode'];obs=row['observation']
            family=mode.rsplit('_',1)[0]+'_RR' if mode.endswith(('1R','2R','3R')) else mode
            key=(o['setup_id'],family)
            if key not in groups:
                pattern=s['details'].get('three_candle_oc')
                flow=flow_by_setup.get(s['id']) if family=='recognition_RR' else None
                groups[key]=dict(id=o['id'].removesuffix('_r1').removesuffix('_r2').removesuffix('_r3')+'_'+family,
                    pair=pair,strategy='Corrected OC H1/H2 · '+family,
                    confirmation='engulfing' if pattern else '4th man' if o['model']=='confirmation_standing_extreme' else 'breakout',
                    tf=o['tf'],side=o['side'],decision=o['clock']['available_at'],entry=o['entry_ticks']*tick,
                    stop=o['stop_ticks']*tick,kind=o['kind'],bias=row.get('bias'),stop_proof=row.get('stop_proof'),
                    targets=[],flow=flow,highlight=False,tick_size=tick,cutoff=cutoff.isoformat(),
                    three_candle_oc=pattern,entry_reference=dict(kind='OC',model=o['model'],confirmation='engulfing',
                        pattern_link='THREE_CLOSED_CANDLES',pattern=pattern) if pattern else None)
            window=obs.get('fill_window') or {}
            groups[key]['targets'].append(dict(label=mode.rsplit('_',1)[-1] if family.endswith('RR') else 'Nearby',
                price=o['target_ticks']*tick,order_id=o['id'],result=dict(outcome=obs['outcome'],gross_R=obs.get('net_r'),
                observed_at=row.get('closed_at'),fill_start=window.get('start'),fill_end=window.get('end'))))
        for e in groups.values():e['targets'].sort(key=lambda t:t['label'])
        entries.extend(groups.values());matches.extend(dict(pair=pair,**m) for m in state.get('cross_tf_matches',[]))
    entries.sort(key=lambda e:(e['decision'],e['pair'],e['strategy']))
    dump(out/'index.json.gz',dict(source_run=os.environ.get('GITHUB_RUN_ID','local-test'),correction_runs=[],
        notice='Corrected three-candle OC, H1/H2 only, one active opportunity per pair per strategy family. Separate rerun; legacy archive unchanged. Gross results; partial saved M1 refinement only.',
        entries=entries,incomplete_pairs=missing,status='PARTIAL' if missing else 'COMPLETE'))
    dump(out/'cross_tf_matches.json',dict(matches=matches,meaning='Same clock,side and entry price; not proof that every H1 engulf is an H2 fourth man'))
    (out/'IMPORT.md').write_text('Separate corrected dataset for the mini app. Do not overwrite the existing archive silently. Publish/import only after checking the completed workflow, coverage and new order IDs. Historical outcomes come exclusively from this rerun; saved old minute evidence is reused only after exact H1 matching.\n')
    return {'entries':len(entries),'incomplete':missing}

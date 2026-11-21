"""Read-only owner-scoped audit of the mini-app RR study, not annual research."""
import csv,json,os,hashlib
from collections import Counter
from decimal import Decimal
from pathlib import Path
from datetime import datetime,timezone
from slk.bishop_rr import summary

def audit(studies):
    rows=[]
    for s in studies:
        inst=s['instrument'];tick=Decimal(str(inst['tick_size']));unit=Decimal(str(inst['distance_unit']))
        pair=s['pair'];fx=len(pair)==6 and pair[:3] in ('USD','EUR','GBP','AUD','NZD','CAD','CHF','JPY') and pair[3:] in ('USD','EUR','GBP','AUD','NZD','CAD','CHF','JPY')
        pip=Decimal('.01') if fx and pair.endswith('JPY') else Decimal('.0001') if fx else None
        for rr in ('1','2','3'):
            v=s.get('variants',{}).get(rr,{});o=v.get('order') or s['source_order'];obs=v.get('observation',{})
            unknown=s.get('status')=='UNKNOWN' or obs.get('outcome')=='CENSORED'
            if not unknown:continue
            entry=o['entry_ticks'];stop=s['stop_proof'].get('stop_ticks');target=o.get('target_ticks') if v.get('order') else None
            distance=abs(Decimal(entry-stop)*tick) if stop is not None else None
            rows.append(dict(study_id=s['id'],pair=pair,tf=s['tf'],side=s['side'],model=s.get('model'),rr=rr,
                decision_at=s.get('created_at'),history_to=s.get('history_to'),enrolled_at=s.get('enrolled_at'),
                study_status=s.get('status'),variant_outcome=obs.get('outcome'),
                reason=s.get('reason') if s.get('status')=='UNKNOWN' else obs.get('censor_reason') or 'CENSOR_REASON_NOT_RECORDED',
                entry_price=str(Decimal(entry)*tick),stop_price=str(Decimal(stop)*tick) if stop is not None else None,
                target_price=str(Decimal(target)*tick) if target is not None else None,
                stop_pips=str(distance/pip) if distance is not None and pip else None,
                stop_distance_units=str(distance/unit) if distance is not None else None,
                fill_window=json.dumps(obs.get('fill_window'),default=str),
                first_ambiguous_candle='NOT_RETAINED_IN_STUDY_PAYLOAD',
                source_id=inst.get('source_id'),price_basis=inst.get('price_basis'),
                stop_rule=s['stop_proof'].get('rule')))
    return rows

def main():
    # Never initialize/migrate tables or invoke scanners; SELECT only.
    from slk import db
    raw_uid=os.environ.get('TELEGRAM_CHAT_ID')
    if not raw_uid:raise RuntimeError('Owner identity secret missing; refusing default-user fallback')
    try:
        records=db.query('SELECT payload FROM bishop_rr_studies WHERE user_id=%s ORDER BY created_at',(int(raw_uid),))
    except Exception:
        raise RuntimeError('Read-only study database query failed; no credentials logged') from None
    studies=[json.loads(r['payload']) for r in records]
    if not studies:raise RuntimeError('No study records for configured owner; cannot match screenshot')
    rows=audit(studies);stats=summary(studies)
    out=Path('reports/rr-panel-audit');out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps(stats,indent=2))
    (out/'unknowns.json').write_text(json.dumps(rows,indent=2))
    if rows:
        with (out/'unknowns.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    reasons=Counter(r['reason'] for r in rows)
    pips=sorted(float(r['stop_pips']) for r in rows if r['stop_pips'] is not None)
    snapshot_match=stats['cohort']==151 and stats['paired_closed']==52 and all(stats['variants'][str(k)]['unknown']==n for k,n in [(1,45),(2,37),(3,38)])
    manifest=dict(at=datetime.now(timezone.utc).isoformat(),cohort=stats['cohort'],exact_screenshot_count_match=snapshot_match,
        snapshot_hash=hashlib.sha256(json.dumps(studies,sort_keys=True).encode()).hexdigest(),
        unknown_variants=len(rows),unique_unknown_studies=len({r['study_id'] for r in rows}),reasons=dict(reasons),
        fx_stop_pips=dict(min=min(pips),median=pips[len(pips)//2],max=max(pips)) if pips else None,
        read_only=True,limitation='No new OHLC fetched. Censor candle/event IDs not retained by study evaluator. Cannot claim these are M1 collisions.')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    lines=['# Mini-app Bishop RR unknown audit',f"Enrolled:{stats['cohort']}; screenshot counts match:{snapshot_match}.",
        f"Unknown variant outcomes:{len(rows)} across{manifest['unique_unknown_studies']} unique studies.",'',
        '| Reason | Variant outcomes |','|---|---:|']
    lines += [f'| {k} | {v} |' for k,v in reasons.items()]
    lines+=['', 'FX stop-size distribution (variant-weighted): '+str(manifest['fx_stop_pips']),
        '', 'The study scanner freezes CENSORED variants and UNKNOWN studies. It does not perform an M1 retry.',
        'The stored study variants omit execution events and the first censor candle. Those must be reconstructed from matching historical feed evidence before attributing ambiguity to one minute.',
        'Expired/cancelled/replaced entries omitted by the UI are present in summary.json. Database was not modified.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print('Read-only audit exported; no study outcomes changed.')

if __name__=='__main__':main()

"""Describe recorded entry references without changing strategy or results."""
from collections import defaultdict

OC_MODELS={'confirmation_engulfed_oc','oc_break_retest'}
AV_MODELS={'engulf_av_retest','engulf_irl_retest'}
ENGULF_MODELS=OC_MODELS|AV_MODELS

def reference_kind(model):
    return 'OC' if model in OC_MODELS else 'AV' if model in AV_MODELS else None

def episode_key(row):
    s=row['setup'];o=row['order'];bars=tuple(s['details'].get('confirmation_protection_bar_ids',()))
    if len(bars)!=2:return None
    return (row['mode'],s['story_id'],o['tf'],o['side'],o['clock']['available_at'],bars)

def metadata(book,tick):
    rows=[r for r in book.values() if not r['mode'].endswith(('2R','3R'))]
    groups=defaultdict(list)
    for r in rows:
        key=episode_key(r)
        if key and r['order']['model'] in ENGULF_MODELS:groups[key].append(r)
    out={}
    for r in rows:
        o=r['order'];kind=reference_kind(o['model'])
        candidates={}
        for alt in groups.get(episode_key(r),[]) if kind else ():
            a=alt['order'];k=(reference_kind(a['model']),a['entry_ticks'],alt['setup']['level_id'])
            candidates.setdefault(k,{'kind':k[0],'price':float(a['entry_ticks'])*tick,'level_id':k[2],'models':[]})['models'].append(a['model'])
        out[o['id']]={'model':o['model'],'kind':kind,'level_id':r['setup']['level_id'],
          'confirmation':'engulfing' if kind else None,
          'pattern_link':'ADJACENT_ENGULF_PAIR' if len(r['setup']['details'].get('confirmation_protection_bar_ids',()))==2 else 'OC_CROSS_WITHOUT_SAVED_ADJACENT_ENGULF_PAIR' if kind=='OC' else None,
          'alternatives':sorted(candidates.values(),key=lambda x:(x['kind'],x['price'],x['level_id'])),
          'evidence_scope':'Recorded admitted orders with the same strategy, story, timeframe, direction, decision time and confirmation bars. Absence does not prove another reference was ineligible.'}
    return out


def attach_audit(refs,findings,ticks):
    """Publish decision evidence only. Never copy later touches/results into review."""
    for finding in findings:
        ref=refs.get(finding['order_id'])
        if ref is None:continue
        junction=finding['junction']
        ref['junction_audit']={'status':finding['status'],'junction_status':junction['status'],
            'gap_ticks':junction.get('gap_ticks'),'allowed_gap_ticks':junction.get('allowed_gap_ticks'),
            'price':junction['price_ticks']*ticks[finding['pair']] if 'price_ticks' in junction else None}
        if finding['status']!='ENGINE_ELIGIBLE_OC':continue
        eligible_ids={a['level_id'] for a in finding['alternatives'] if a['engine_status']=='ELIGIBLE'}
        for a in ref['alternatives']:
            if a['kind']=='OC' and a['level_id'] in eligible_ids:a['immediate_junction']=True
        existing={(a['kind'],a['level_id']) for a in ref['alternatives']}
        for a in finding['alternatives']:
            if a['engine_status']!='ELIGIBLE' or ('OC',a['level_id']) in existing:continue
            ref['alternatives'].append({'kind':'OC','price':a['entry_ticks']*ticks[finding['pair']],
                'level_id':a['level_id'],'models':[a['model']],'audit_only':True,'immediate_junction':True})
            existing.add(('OC',a['level_id']))

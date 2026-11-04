"""Isolate current-weekly-context effect on already frozen standing plans.

Reproduce every original risk result before changing context alone. No orders.
"""
import gzip,json
from pathlib import Path
from types import SimpleNamespace
from bishop.v2.types import Level,Liquidity,Event,Clock,utc,jsonable
from bishop.v2.structure import Range,RoleIndex
from bishop.v2.feed import load_feed
from bishop.v2.risk import plan
from bishop.v2.types import StrategyPolicy

REPORT=Path('reports/implementation_review/primary_video_40584728247/video-t3-usdcad-buy-open.json.gz')
def reprice(context):
    doc=json.load(gzip.open(REPORT));r=doc['result'];p=doc['plan'];at=utc('2026-06-12T16:00:00Z')
    m=json.load(open(p['manifest_path']));f=load_feed(p['input_path'],m,p['as_of'],p['history_start'])
    bars=f['bars'];bybar={b.id:b for b in bars};structures=r['diagnostics']['structures']
    levels=tuple(Level(**l) for d in structures.values() for l in d['levels'] if utc(l['available_at'])<=at)
    pools=tuple(Liquidity(**l) for d in structures.values() for l in d['liquidity'] if utc(l['available_at'])<=at)
    roles={tf:RoleIndex(tuple(Event(**{**e,'clock':Clock(**e['clock'])}) for e in d['events'])) for tf,d in structures.items()}
    ranges=tuple(Range(**{**x,'formed_at':utc(x['formed_at']),'available_at':utc(x['available_at'])}) for x in structures['H1']['ranges'])
    bystory={s['id']:s for s in r['stories']};policy=StrategyPolicy(source_profile='bishop_confirmation',risk_profile='context_liquidity',target_profile='nearest_erl',entry_tfs=('H4','H3','H2','H1'),origin_tfs=('W','D','H4'))
    ss=[s for s in r['setups'] if s['tf']=='H1' and s['model']=='confirmation_standing_extreme' and s['side']=='BUY' and utc(s['clock']['available_at'])==at]
    rows=[]
    for s in ss:
        original=bystory[s['story_id']];details={**original['details'],'entry_weekly_relation':s['details']['entry_weekly_relation'],'entry_weekly_context':s['details']['entry_weekly_context']}
        story=SimpleNamespace(**{**original,'details':details})
        protected=tuple(bybar[x[0]] for x in s['details']['protected_objects'] if x[2]=='pattern_wick')
        kwargs={'role_lookup':lambda l,t:roles[l.tf].role_at(l,t),'protection_bars':protected,'ranges':ranges,
                'protection_evidence_ids':s['details']['protection_evidence_ids'],
                'protection_range_ids':s['details']['protection_range_ids']}
        before=plan('BUY',s['entry_ticks'],at,'H1',bars,levels,pools,story,f['instrument'],policy,**kwargs)
        assert (before.stop_ticks,before.target_ticks)==(s['stop_ticks'],s['target_ticks']),s['id']
        relation=('ALIGNED' if context['side']=='BUY' else 'COUNTER_WEEKLY') if context['status']=='KNOWN' else context['status']
        revised=SimpleNamespace(**{**vars(story),'details':{**details,'entry_weekly_relation':relation,'entry_weekly_context':context}})
        after=plan('BUY',s['entry_ticks'],at,'H1',bars,levels,pools,revised,f['instrument'],policy,**kwargs)
        rows.append({'setup_id':s['id'],'before':before,'after':after,'entry_weekly_relation':relation})
    assert ss
    return jsonable({'scope':'SAME_FROZEN_CANDIDATES_CONTEXT_ONLY_RISK_ISOLATION_NOT_BOOK_REPLAY',
       'reproduced_original_plans':len(rows),'source_report':str(REPORT),
       'before_targets':sorted({s['target_ticks'] for s in ss}),
       'after_targets':sorted({x['after'].target_ticks for x in rows if x['after'].target_ticks is not None}),
       'before_stops':sorted({s['stop_ticks'] for s in ss}),
       'after_stops':sorted({x['after'].stop_ticks for x in rows if x['after'].stop_ticks is not None}),
       'weekly_context':context,'orders_submitted':0,'rows':rows})

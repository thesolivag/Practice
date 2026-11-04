"""Read an existing frozen GitHub replay; never rerun detection or execution."""
from collections import Counter,defaultdict
from decimal import Decimal
import argparse,gzip,json
from pathlib import Path
import ijson


def one(path,prefix):
    with gzip.open(path,'rb') as stream:return next(ijson.items(stream,prefix,use_float=True))


def chosen(path,prefix,ids):
    rows={}
    with gzip.open(path,'rb') as stream:
        for row in ijson.items(stream,prefix+'.item',use_float=True):
            if row['id'] in ids:rows[row['id']]=row
            if rows.keys()==ids:break
    if rows.keys()!=ids:raise ValueError('selected record missing: '+str(ids-rows.keys()))
    return rows


def audit(path):
    orders=one(path,'result.orders');obs={o['id']:o for o in one(path,'result.observations')}
    setups=chosen(path,'result.setups',{o['setup_id'] for o in orders})
    stories=chosen(path,'result.stories',{s['story_id'] for s in setups.values()})
    groups=defaultdict(lambda:dict(orders=0,outcomes=Counter(),closed_net_r=Decimal(0),planned_under_one_r=0))
    rows=[]
    for order in orders:
        setup=setups[order['setup_id']];story=stories[setup['story_id']];details=setup['details'];ob=obs[order['id']]
        risk=abs(order['entry_ticks']-order['stop_ticks']);reward=abs(order['target_ticks']-order['entry_ticks'])
        rr=Decimal(reward)/Decimal(risk)
        row=dict(order=order,observation=ob,planned_reward_r=str(rr),risk_ticks=risk,reward_ticks=reward,
                 entry_weekly_relation=details.get('entry_weekly_relation'),
                 target_candidates=details.get('target_candidates'),target_adjustments=details.get('target_adjustments'),
                 entry_range_id=details.get('entry_range_id'),entry_range_version=details.get('entry_range_version'),
                 setup_details=details,setup_evidence_ids=setup['evidence_ids'],story=story)
        rows.append(row)
        key='|'.join(str(x) for x in (order['tf'],order['model'],row['entry_weekly_relation']))
        group=groups[key];group['orders']+=1;group['outcomes'][ob['outcome']]+=1
        group['planned_under_one_r']+=rr<1
        if ob['net_r'] is not None:group['closed_net_r']+=Decimal(ob['net_r'])
    summary=dict(orders=len(rows),planned_under_one_r=sum(Decimal(r['planned_reward_r'])<1 for r in rows),
        planned_under_tenth_r=sum(Decimal(r['planned_reward_r'])<Decimal('.1') for r in rows),
        counterweekly_guard_used=sum(bool(r['target_adjustments']) for r in rows),
        closed_net_r=str(sum((Decimal(o['net_r']) for o in obs.values() if o['net_r'] is not None),Decimal(0))),
        outcomes=dict(Counter(r['observation']['outcome'] for r in rows)))
    for group in groups.values():
        group['closed_net_r']=str(group['closed_net_r']);group['outcomes']=dict(group['outcomes'])
    economic=defaultdict(list)
    for row in rows:
        o=row['order']
        key=(o['instrument'],o['tf'],o['side'],o['clock']['available_at'],o['entry_ticks'],o['stop_ticks'],o['target_ticks'],o['kind'],o['expires_at'])
        economic[key].append(row)
    duplicates=[]
    for group in economic.values():
        if len(group)<2:continue
        duplicates.append(dict(order_ids=[r['order']['id'] for r in group],models=[r['order']['model'] for r in group],
            same_story=len({r['story']['id'] for r in group})==1,
            same_confirmation_pair=all(r['setup_details']['confirmation_protection_bar_ids']==group[0]['setup_details']['confirmation_protection_bar_ids'] for r in group),
            same_protection_evidence=all(r['setup_details']['protection_evidence_ids']==group[0]['setup_details']['protection_evidence_ids'] for r in group),
            merge_authorized=False,reason='NUMERICAL_EQUALITY_DOES_NOT_ESTABLISH_CANCELLATION_LINEAGE'))
    return dict(scope='SOURCE_SCOPE_AUDIT_NOT_PARAMETER_OPTIMIZATION',source_run=40693590233,
                summary=summary,groups=dict(groups),numerically_identical_order_groups=duplicates,trades=rows)


def contextual_objectives(path,report):
    """Compare explicit H4 sponsorship, not hypothetical profitable exits."""
    from bishop.v2.feed import load_feed
    from bishop.v2.aggregation import aggregate
    from bishop.v2.types import Event, Clock, utc
    from bishop.v2.structure import RoleIndex
    h4=one(path,'result.diagnostics.structures.H4')
    plan=one(path,'plan')
    metadata=json.loads(Path(plan['manifest_path']).read_text())
    feed=load_feed(plan['input_path'],metadata,plan['as_of'],plan['history_start'])
    bars=aggregate(feed['bars'],'H4',feed['instrument'],plan['as_of'],calendar=metadata['calendar_id'])['bars']
    events={e['id']:e for e in h4['events']}
    roles=RoleIndex(tuple(Event(**{**e,'clock':Clock(**e['clock'])}) for e in h4['events']))
    pools={p['id']:p for p in h4['liquidity']}
    levels={l['id']:l for l in h4['levels']}
    breaks={'BREAKOUT','BOS','SWEEP_BOS','EXTERNAL_BREAK'}
    counts=Counter()
    for row in report['trades']:
        o=row['order'];at=utc(o['clock']['available_at']);sign=1 if o['side']=='BUY' else -1
        # IDs are the actual saved setup's causal evidence, not nearest events.
        ids=row['setup_evidence_ids']
        sponsors=[events[i] for i in ids if i in events and events[i]['kind'] in breaks
                  and events[i]['side']==o['side'] and utc(events[i]['clock']['available_at'])<=at]
        context=dict(sponsoring_breaks=sponsors,scope_status='UNRESOLVED_SPONSOR',objective=None)
        if len(sponsors)==1:
            sponsor=sponsors[0];scope=sponsor['scope_id']
            context['scope_id']=scope
            known=[r for r in h4['ranges'] if r['id']==scope and utc(r['available_at'])<=at]
            latest=max(enumerate(known),key=lambda pair:(utc(pair[1]['available_at']),pair[0]))[1] if known else None
            seed_ids={r['id'] for r in h4['ranges'] if utc(r['available_at'])<=at and r['details'].get('seed_break_event_id')==sponsor['id']}
            seed_versions=[]
            for ident in sorted(seed_ids):
                versions=[r for r in h4['ranges'] if r['id']==ident and utc(r['available_at'])<=at]
                seed_versions.append(max(enumerate(versions),key=lambda pair:(utc(pair[1]['available_at']),pair[0]))[1])
            context['seed_linked_range_alternatives_not_ranked']=seed_versions
            context['scope_link_policy']='EXACT_EVENT_SCOPE_AUDIT_WITH_UNRANKED_SEED_ALTERNATIVES'
            context['range']=latest
            context['entry_inside_sponsoring_range']=bool(latest and min(latest['origin_ticks'],latest['endpoint_ticks'])<=o['entry_ticks']<=max(latest['origin_ticks'],latest['endpoint_ticks']))
            context['scope_status']='KNOWN' if latest else 'UNRESOLVED_RANGE'
            if latest:
                pool=pools.get(latest['endpoint_liquidity_id'])
                reason=None
                if latest['status']=='BROKEN':
                    reason='RANGE_ORIGIN_INVALIDATED'
                elif latest['details'].get('endpoint_broken'):
                    reason='SCOPE_ENDPOINT_DELIVERED_REASSESS_NEW_SCOPE'
                elif latest['details'].get('endpoint_stage')!='CONFIRMED_DELIVERY':reason='UNCONFIRMED_ENDPOINT'
                elif latest['direction']!=o['side']:reason='OPPOSITE_CONTEXT'
                elif not pool or utc(pool['available_at'])>at:reason='UNKNOWN_ENDPOINT_POOL'
                elif pool['kind']!=('HIGH' if sign==1 else 'LOW'):reason='WRONG_ENDPOINT_KIND'
                elif sign*(pool['price_ticks']-o['entry_ticks'])<=0:reason='ENDPOINT_NOT_AHEAD'
                elif any(b.available_at<=at and b.id not in pool['bar_ids'] and b.end>utc(pool['formed_at'])
                         and (b.high_ticks>=pool['price_ticks'] if pool['kind']=='HIGH' else b.low_ticks<=pool['price_ticks']) for b in bars):
                    reason='ENDPOINT_ALREADY_TOUCHED'
                context['objective_status']=reason or 'KNOWN_STANDING_CONTEXT_ERL'
                if reason is None:
                    context['objective']=pool
                    context['context_reward_r']=str(Decimal(abs(pool['price_ticks']-o['entry_ticks']))/row['risk_ticks'])
                    context['same_as_selected_target']=pool['price_ticks']==o['target_ticks']
                # Source-described opposing context KL stays separate from ERL.
                opposite=[]
                for lv in h4['levels']:
                    if utc(lv['available_at'])>at or sign*(lv['price_ticks']-o['entry_ticks'])<=0:continue
                    from types import SimpleNamespace
                    role=roles.role_at(SimpleNamespace(**{**lv,'available_at':utc(lv['available_at']),'initial_role':'SUPPORT' if lv['side']=='BUY' else 'RESISTANCE'}),at)
                    if role in (('RESISTANCE','SELL') if sign==1 else ('SUPPORT','BUY')):
                        opposite.append(dict(id=lv['id'],kind=lv['kind'],price_ticks=lv['price_ticks'],tf='H4'))
                context['opposing_H4_levels_for_review_only']=sorted(opposite,key=lambda l:sign*(l['price_ticks']-o['entry_ticks']))
        if row['target_adjustments']:
            guard_id=row['target_adjustments'][-1][2]
            context['selected_guard_is_H4_level']=guard_id in levels
        counts[context.get('objective_status',context['scope_status'])]+=1
        row['contextual_target_audit']=context
    report['context_objective_status_counts']=dict(counts)
    report['context_policy_limitation']='No replacement target was selected; H4 KL/ERL and story destination remain distinct source routes.'
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('replay',type=Path);p.add_argument('output',type=Path);p.add_argument('--context',action='store_true');a=p.parse_args()
    result=audit(a.replay)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    if a.context:
        result=contextual_objectives(a.replay,result)
        a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(summary=result['summary'],groups=result['groups']),indent=2))

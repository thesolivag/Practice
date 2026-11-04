"""Map saved causal objects to closed observed candles; never assert chart identity."""
import gzip,json
from pathlib import Path
from bishop.v2.feed import load_feed
from bishop.v2.aggregation import aggregate
from bishop.v2.types import utc,jsonable,Level,Liquidity,Event,Clock
from bishop.v2.structure import role_at
from bishop.v2.entries import BREAKS,_first_take_for_reaction,_protection_episode_bars
from reports.replay_collected_teacher_examples_v2 import digest

def map_trace(path):
    saved=json.load(gzip.open(path,'rt'));plan=saved['plan'];result=saved['result'];case=saved['case']
    metadata=json.load(open(plan['manifest_path'])); assert digest(plan['input_path'])==saved['summary']['input_sha256']
    clock=utc(saved['summary']['as_of'])
    feed=load_feed(plan['input_path'],metadata,clock,plan['history_start'])
    # All candles come from declared raw input and close before the source snapshot.
    day=utc('2026-07-15T00:00:00Z' if case['pair']=='EURNZD' else '2026-06-23T00:00:00Z')
    candles={tf:aggregate(feed['bars'],tf,feed['instrument'],clock,calendar=metadata['calendar_id'])['bars'] for tf in ('H4',case['tf'])}
    structure=result['diagnostics']['structures']['H4'];events=structure['events']
    h4_events=tuple(Event(**{**e,'clock':Clock(**e['clock'])}) for e in events)
    pools=list(structure['liquidity'])
    for support in result['support']:
        if support.get('route')=='entry_liquidity_forms':
            pools.extend(p for p in support.get('objects',[]) if p['tf']=='H4')
    pools=list({p['id']:p for p in pools}.values())
    h4bars=candles['H4']
    # No source-price matching, tolerance fitting, or phase chosen by outcomes.
    levels=[]
    for level in structure['levels']:
        if utc(level['available_at'])>clock:continue
        relevant=[]
        for b in candles[case['tf']]:
            if b.start<day or utc(level['available_at'])>b.start:continue
            if b.low_ticks<=level['price_ticks']<=b.high_ticks:
                known=[e for e in events if e['kind']=='LEVEL_ROLE_CHANGE' and e['reference_id']==level['id'] and utc(e['clock']['available_at'])<=b.start]
                role=max(known,key=lambda e:utc(e['clock']['available_at']))['side'] if known else level['side']
                parents=[e for e in events if e['kind'] in BREAKS and e['side']=='SELL' and utc(e['clock']['available_at'])<=b.start]
                parent=max(parents,key=lambda e:utc(e['clock']['available_at'])) if parents else None
                audit=[]
                if parent:
                    known_h4=[x for x in h4bars if x.available_at<=b.start]
                    segment_start=next((x.start for x in h4bars if known_h4 and x.segment_id==known_h4[-1].segment_id),b.start)
                    typed_parent=Event(**{**parent,'clock':Clock(**parent['clock'])})
                    for pool in pools:
                        reasons=[]
                        if pool['kind']!='HIGH':continue
                        if utc(pool['formed_at'])<segment_start or utc(pool['available_at'])<segment_start:reasons.append('OUTSIDE_CURRENT_SEGMENT')
                        if pool['form'] in ('BAR','PRIOR_PERIOD','SESSION') and pool['details'].get('role')!='IRL':reasons.append('NOT_INTERNAL_LIQUIDITY')
                        if utc(pool['available_at'])>b.start:reasons.append('UNAVAILABLE_AT_REACTION_START')
                        if utc(pool['formed_at'])<utc(parent['clock']['occurred_from']):reasons.append('FORMED_BEFORE_PARENT')
                        first=next((x for x in candles[case['tf']] if x.start>=utc(pool['available_at']) and x.end<=b.end and x.available_at<=b.available_at and x.high_ticks>pool['price_ticks']),None)
                        linked=_first_take_for_reaction(Liquidity(**pool),b,candles[case['tf']],Level(**level),typed_parent,h4_events) if not reasons else None
                        complete=bool(linked and _protection_episode_bars((linked,),b,candles[case['tf']]))
                        audit.append({'pool':pool,'selection_rejections':reasons,'first_observed_take':jsonable(first) if first else None,'linked_first_take_id':linked.id if linked else None,'protection_episode_complete':complete})
                relevant.append({'bar':jsonable(b),'role_at_bar_start':role,'closes_below_level':b.close_ticks<level['price_ticks'],'latest_known_sell_parent':parent,'pool_audit':audit})
        if relevant:
            levels.append({'level':level,'observed_contacts':relevant,'role_history':[e for e in events if e['reference_id']==level['id'] and e['kind']=='LEVEL_ROLE_CHANGE']})
    assert all(b.end<=clock for bs in candles.values() for b in bs)
    return {'case_id':case['id'],'source_snapshot':clock.isoformat(),'chart_object_identity':'UNRESOLVED_NOT_ESTABLISHED_BY_PRICE_PROXIMITY','input_sha256':digest(plan['input_path']),'anchor':metadata['anchor_id'],'candles':{tf:jsonable(tuple(b for b in bs if b.start>=day)) for tf,bs in candles.items()},'contact_lineages':levels,'sell_stories':[s for s in result['stories'] if s['side']=='SELL' and utc(s['clock']['available_at'])>=day],'h4_pools':structure['liquidity']}

def main():
    out=Path('reports/teacher_lineage_mapping');out.mkdir(exist_ok=True)
    for p in Path('reports/teacher_missing_investigation').glob('*/printed_source_snapshot.json.gz'):
        r=map_trace(p);(out/(r['case_id']+'.json')).write_text(json.dumps(r,indent=2)+'\n')
        print(r['case_id'],'contacted H4 levels',len(r['contact_lineages']),'source identity unresolved')
if __name__=='__main__':main()

"""Isolated causal recognition study. Produces plans, never orders or Telegram."""
from datetime import datetime,timedelta,timezone
import json
VERSION='closed_break_later_liquidity_v1'
MODELS={'confirmation_bo':'breakout','confirmation_sweep_bos':'breakout',
 'confirmation_engulfed_oc':'engulfing','oc_break_retest':'engulfing','engulf_av_retest':'engulfing',
 'engulf_irl_retest':'engulfing','confirmation_standing_extreme':'4th man'}


def break_proof(event,bars,structure):
    """Require the actual closed candle and exact old A/V reference/role flip."""
    from bishop.v2.entries import _breakout_retest_level
    from bishop.v2.structure import RoleIndex
    candles=[b for b in bars if b.id in event.bar_ids and b.complete and b.available_at==event.available_at]
    if len(candles)!=1:return None,'H4_BREAK_CANDLE_UNRESOLVED'
    b=candles[0];roles=RoleIndex(structure.events)
    lv,reason=_breakout_retest_level(event,b,structure.levels,event.side,roles.role_at)
    if reason:return None,'H4_'+reason.upper()
    return {'event_id':event.id,'candle_id':b.id,'level_id':lv.id,'level_ticks':lv.price_ticks,
            'close_ticks':b.close_ticks,'available_at':event.available_at.isoformat()},None


def recognize(frames,structure,biases,policy,as_of,since,setups=(),calendar='fx_ny_v1',instrument=None):
    """All inputs are filtered at as_of. No future sweep is used to create pools.

    Current watched bias is a live admission snapshot, not reconstructed historic
    KK bias. Later approach geometry remains the explicitly named research rule.
    """
    from bishop.v2.types import utc,stable_id,jsonable
    from bishop.v2.entries import BREAKS,_direct_episode_reason,_first_take_for_reaction,_reaction_episode_reason
    from bishop.v2.structure import RoleIndex
    from bishop.v2.liquidity_forms import later_kl_irl
    from bishop.v2.aggregation import expected_slots
    from dataclasses import replace
    from slk.bishop_rr import logical_stop
    now=utc(as_of);since=utc(since)
    frames={tf:tuple(sorted((b for b in bs if b.complete and b.available_at<=now),key=lambda b:b.start)) for tf,bs in frames.items()}
    h4=replace(structure,events=tuple(e for e in structure.events if e.available_at<=now),levels=tuple(l for l in structure.levels if l.available_at<=now))
    roles=RoleIndex(h4.events);bars=frames.get('H4',());parents={e.id:e for e in h4.events if e.kind in BREAKS and e.side and e.evidence_status=='KNOWN' and e.available_at>=since}
    qualified={};rejected=[];bias_proofs={}
    for ident,e in parents.items():
        matching=[b for b in biases if b['pair']==e.instrument and utc(b['confirmed_at'])<=e.available_at]
        if not matching or any(b['side']!=e.side for b in matching):continue
        proof,reason=break_proof(e,bars,h4)
        if reason:rejected.append({'event_id':ident,'at':e.available_at.isoformat(),'reason':reason});continue
        qualified[ident]=proof;bias_proofs[ident]=max(matching,key=lambda b:(utc(b['confirmed_at']),str(b['id'])))
    # Preserve all events for causal role/retirement checks; reject pools whose
    # chosen parent fails proof rather than falling back to an older parent.
    pools=later_kl_irl(bars,h4.levels,h4.events,policy,roles.role_at)
    levels={l.id:l for l in h4.levels};flows=[];used_parents=set()
    setup_index={}
    for setup in sorted(setups,key=lambda s:(s['clock']['available_at'],s['id'])):
        setup_index.setdefault((setup['tf'],utc(setup['clock']['available_at'])),[]).append(setup)
    for pool in pools:
        parent=parents.get(pool.details['parent_break_id'])
        if not parent or parent.id not in qualified:continue
        used_parents.add(parent.id)
        level=levels[pool.details['reaction_level_id']]
        pool_bars=[b for b in bars if b.id in pool.bar_ids]
        if not pool_bars:continue
        for tf in ('H1','H2','H3'):
            bs=frames.get(tf,())
            ident=stable_id('bishop_flow',VERSION,pool.id,tf,bias_proofs[parent.id]['id'])
            timeline=[{'stage':'BIAS_CONFIRMED','at':bias_proofs[parent.id]['confirmed_at'],'evidence_id':str(bias_proofs[parent.id]['id'])},
             {'stage':'BREAK_CONFIRMED','at':parent.available_at.isoformat(),'evidence_id':parent.id},
             {'stage':'LIQUIDITY_CANDIDATE','at':pool.available_at.isoformat(),'evidence_id':pool.id}]
            row={'id':ident,'version':VERSION,'pair':pool.instrument,'tf':tf,'side':parent.side,
                 'status':'WAIT_TAKE','bias':bias_proofs[parent.id],'break':qualified[parent.id],
                 'pool':jsonable(pool),'level':jsonable(level),'timeline':timeline,'plans':[]}
            take=None;reaction=None;covered_until=pool.available_at
            for b in bs:
                if b.start<pool.available_at:continue
                # Unknown gaps cannot be interpreted as an intact/untaken pool.
                missing=next(expected_slots(covered_until,b.start,'H1',calendar),None) if b.start>covered_until else None
                covered_until=b.end
                reason=_direct_episode_reason(parent,b.available_at,h4.events,level)
                # Segment counters are local to each timeframe/window, so they
                # cannot be compared between an H4 pool and child candles.
                if missing is not None:reason='DATA_GAP'
                if reason:
                    row.update(status='INVALIDATED',reason=reason);timeline.append({'stage':'INVALIDATED','at':b.available_at.isoformat(),'reason':reason});break
                if take is None and (b.high_ticks>pool.price_ticks if pool.kind=='HIGH' else b.low_ticks<pool.price_ticks):
                    take=b;row['status']='WAIT_REACTION';timeline.append({'stage':'LIQUIDITY_TAKEN','at':b.available_at.isoformat(),'evidence_id':b.id})
                if take and b.low_ticks<=level.price_ticks<=b.high_ticks and (b.close_ticks>level.price_ticks if parent.side=='BUY' else b.close_ticks<level.price_ticks) and roles.role_at(level,b.start) in (parent.side,'SUPPORT' if parent.side=='BUY' else 'RESISTANCE'):
                    linked=_first_take_for_reaction(pool,b,bs,level,parent,h4.events,first_candidate=take)
                    if linked:
                        reaction=b;row['status']='WAIT_CONFIRMATION';timeline.append({'stage':'KEY_LEVEL_REACTION','at':b.available_at.isoformat(),'evidence_id':b.id})
                if reaction:
                    for setup in setup_index.get((tf,b.available_at),()):
                        if setup['tf']!=tf or setup['side']!=parent.side or setup['model'] not in MODELS:continue
                        if utc(setup['clock']['available_at'])!=b.available_at:continue
                        if pool.id not in setup['liquidity_ids'] or not {parent.id,level.id,reaction.id}.issubset(setup['evidence_ids']):continue
                        if _reaction_episode_reason((reaction,level,parent,(pool,)),b,h4.events):continue
                        proof=logical_stop(setup,bs,instrument) if instrument else {'status':'UNRESOLVED','reason':'Instrument unavailable'}
                        plan={'setup_id':setup['id'],'confirmation':MODELS[setup['model']],'model':setup['model'],
                              'at':b.available_at.isoformat(),'entry_ticks':setup['entry_ticks'],'stop_proof':proof,
                              'engine_status':setup['status'],'source_target_ticks':setup.get('target_ticks'),'paper_only':True}
                        if proof['status']=='READY':
                            risk=abs(setup['entry_ticks']-proof['stop_ticks']);sign=1 if parent.side=='BUY' else -1
                            plan['targets']={str(rr):setup['entry_ticks']+sign*risk*rr for rr in (1,2,3)}
                        row['plans'].append(plan)
                    if row['plans']:
                        row['status']='CONFIRMED_PLAN' if any(p['stop_proof']['status']=='READY' and p['engine_status']=='ELIGIBLE' for p in row['plans']) else 'CONFIRMED_UNRESOLVED'
                        timeline.append({'stage':row['status'],'at':b.available_at.isoformat(),'evidence_id':row['plans'][0]['setup_id']});break
            # Expire an unconfirmed watch on observed context invalidation even
            # when no child bar has yet closed at the event publication clock.
            if not row['plans']:
                reason=_direct_episode_reason(parent,now,h4.events,level)
                if reason and row['status']!='INVALIDATED':row.update(status='INVALIDATED',reason=reason);timeline.append({'stage':'INVALIDATED','at':now.isoformat(),'reason':reason})
            flows.append(row)
    for ident in qualified.keys()-used_parents:
        parent=parents[ident];bias=bias_proofs[ident]
        reason=_direct_episode_reason(parent,now,h4.events)
        flows.append({'id':stable_id('bishop_flow_break',VERSION,ident,bias['id']),'version':VERSION,
            'pair':parent.instrument,'tf':'H4','side':parent.side,'status':'INVALIDATED' if reason else 'WAIT_LIQUIDITY',
            'reason':reason,'bias':bias,'break':qualified[ident],'pool':{'price_ticks':None},'level':{'price_ticks':None},'plans':[],
            'timeline':[{'stage':'BIAS_CONFIRMED','at':bias['confirmed_at'],'evidence_id':str(bias['id'])},
                        {'stage':'BREAK_CONFIRMED','at':parent.available_at.isoformat(),'evidence_id':ident}]})
    return {'version':VERSION,'as_of':now.isoformat(),'flows':flows,'rejected_breaks':rejected,
            'note':'Recognition study only; no order, fill or profitability claim. Later approach geometry is experimental.'}


def compute(payload):
    from bishop.v2.engine import run
    from bishop.v2.types import StrategyPolicy,utc,Level,Event,Clock
    from bishop.v2.structure import StructureResult
    from bishop.v2.aggregation import aggregate
    from bishop.v2.simulation import Costs
    from slk.bishop_paper import feed_from_store
    feed=feed_from_store(payload['pair'],payload['now']);now=utc(payload['now'])
    calendar=feed['manifest'].get('calendar',feed['instrument'].calendar_id)
    feed={**feed,'bars':tuple(b for b in feed['bars'] if b.start>=now-timedelta(days=35))}
    policy=StrategyPolicy(source_profile='bishop_confirmation',research_later_kl_irl=True,entry_tfs=('H4','H3','H2','H1'))
    # This mode never enters the simulator's order book or consumes baseline slots.
    r=run(feed,as_of=now,scan_start=payload['since'],policy=policy,costs=Costs(),compact_story_diagnostics=True,include_diagnostics=True,entry_gate=lambda *_:'RECOGNITION_ONLY_NO_ORDER')
    raw=r['diagnostics']['structures']['H4'];h4=StructureResult((),tuple(Level(**l) for l in raw['levels']),(),tuple(Event(**{**e,'clock':Clock(**e['clock'])}) for e in raw['events']),())
    frames={tf:aggregate(feed['bars'],tf,feed['instrument'],now,calendar=calendar)['bars'] for tf in ('H4','H3','H2','H1')}
    result=recognize(frames,h4,payload['biases'],policy,now,payload['since'],r['setups'],calendar,feed['instrument'])
    result['tick_size']=str(feed['instrument'].tick_size)
    return result

SCHEMA='''CREATE TABLE IF NOT EXISTS bishop_flow_state (
 user_id BIGINT NOT NULL,pair VARCHAR(16) NOT NULL,activated_at BIGINT NOT NULL,
 checked_at BIGINT NOT NULL DEFAULT 0,payload MEDIUMTEXT NULL,
 PRIMARY KEY(user_id,pair)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''


def merge(previous,current):
    """Retain completed evidence; revisions never silently rewrite old stages."""
    old={r['id']:r for r in (previous or {}).get('flows',[])};out=[]
    for row in current['flows']:
        prior=old.pop(row['id'],None)
        if prior and (prior.get('plans') or prior['status'] in ('INVALIDATED','EVIDENCE_CHANGED')):row=prior
        elif prior and row['timeline'][:len(prior['timeline'])]!=prior['timeline']:
            row={**prior,'status':'EVIDENCE_CHANGED','reason':'Previously recorded stages changed; original evidence retained'}
        out.append(row)
    for row in old.values():
        if not row.get('plans') and row['status'] not in ('INVALIDATED','EVIDENCE_CHANGED'):
            row={**row,'status':'UNAVAILABLE','reason':'Current bias or retained context no longer supports this watch'}
        out.append(row)
    # This is a recognition ledger, not a results cohort. Keep all live watches
    # and recent 100 completed/retired plans per selected pair, explicitly labeled.
    live=[r for r in out if r['status'].startswith('WAIT_')]
    closed=sorted((r for r in out if not r['status'].startswith('WAIT_')),key=lambda r:r['timeline'][-1]['at'],reverse=True)[:100]
    return {**current,'tick_size':current.get('tick_size',(previous or {}).get('tick_size')),'flows':live+closed,'retention':'All current watches plus latest 100 completed/retired records per market'}


def scan(budget=100,timeout=20):
    import time,subprocess,sys
    from slk import db,tenancy,settings
    from slk.bishop_paper import confirmed_web_biases,iso
    stamp=int(time.time());now=datetime.fromtimestamp(stamp,timezone.utc);deadline=time.monotonic()+budget
    db.execute(SCHEMA);done=failed=deferred=0
    users=sorted({tenancy.owner_id(),*(int(r['user_id']) for r in db.query('SELECT user_id FROM app_users'))})
    cursor=int(db.get_setting('bishop_flow_user_cursor','0') or '0');users=[u for u in users if u>cursor]+[u for u in users if u<=cursor]
    for uid in users:
        if time.monotonic()+timeout+2>=deadline:break
        with tenancy.scope(uid):vals=settings.load(db.get_settings())
        if not vals['bishop_flow_study']:continue
        pairs=vals['pairs'] or (settings.PAIRS if uid==tenancy.owner_id() else tenancy.STARTER['pairs'].split(','))
        states={r['pair']:r for r in db.query('SELECT * FROM bishop_flow_state WHERE user_id=%s',(uid,))}
        for pair in sorted(pairs,key=lambda p:(states.get(p,{}).get('checked_at',0),p)):
            if time.monotonic()+timeout+2>=deadline:deferred+=1;break
            state=states.get(pair)
            if not state:
                db.execute('INSERT IGNORE INTO bishop_flow_state(user_id,pair,activated_at) VALUES(%s,%s,%s)',(uid,pair,stamp));continue
            with tenancy.scope(uid):rows=db.query('SELECT * FROM bias WHERE pair=%s ORDER BY COALESCE(confirm_time,tap_time) DESC,id DESC',(pair,))
            biases=confirmed_web_biases(rows,vals,now)
            previous=json.loads(state['payload']) if state['payload'] else None
            try:
                if not biases:result={'version':VERSION,'as_of':iso(stamp),'flows':[],'rejected_breaks':[],'note':'Waiting for a confirmed watched web bias'}
                else:
                    payload={'pair':pair,'now':iso(stamp),'since':iso(max(state['activated_at'],stamp-7*86400)),'biases':biases}
                    child=subprocess.run([sys.executable,'-m','slk.bishop_flow','--compute'],input=json.dumps(payload),text=True,capture_output=True,timeout=timeout,check=True)
                    result=json.loads(child.stdout)
                    if 'error' in result:raise ValueError('worker unavailable')
                result=merge(previous,result)
                db.execute('UPDATE bishop_flow_state SET checked_at=%s,payload=%s WHERE user_id=%s AND pair=%s',(stamp,json.dumps(result),uid,pair));done+=1
            except Exception:
                failed+=1
                # Mark stale explicitly without replacing the saved evidence.
                result={**(previous or {'flows':[],'rejected_breaks':[]}),'note':'Latest recognition scan unavailable; prior evidence retained','stale':True}
                db.execute('UPDATE bishop_flow_state SET checked_at=%s,payload=%s WHERE user_id=%s AND pair=%s',(stamp,json.dumps(result),uid,pair))
        db.set_setting('bishop_flow_user_cursor',str(uid))
    print(json.dumps({'recognition':VERSION,'markets_ok':done,'unavailable':failed,'deferred':deferred,'orders':0}));return 0


def main():
    import sys
    if '--compute' in sys.argv:
        try:print(json.dumps(compute(json.load(sys.stdin))))
        except Exception as exc:print(json.dumps({'error':type(exc).__name__}))
        return 0
    from slk import db
    from slk.jobs import feed_lock
    with feed_lock(db,wait=0) as acquired:
        if not acquired:print('Recognition deferred: shared feed busy');return 0
        return scan()


if __name__=='__main__':raise SystemExit(main())

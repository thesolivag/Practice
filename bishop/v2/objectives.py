"""First qualified trade objective, distinct from overall storyline destination.

Source: Bishop bias-entries88.2-95.7,326.2-337.6; trades-breakdown3
389.1-456.7 and1695.5-1708.2. 'Nearest' follows structural qualification;
no entry-size range, arbitrary wick/junction, RR window or source-price lookup.

Mechanical significance policy: an actual setup-sponsoring closed break must
identify the range directly by scope or exact seed-event linkage. Explicit
ancestors retain their farther objectives; unrelated containing ranges do not.
A confirmed, undelivered endpoint is an external candidate. Only an explicit
scope-linked opposing KL can be a first obstacle. Source-specific discretionary
front-running and unlinked/context-free objectives remain unresolved.
"""
from dataclasses import dataclass
from .types import utc
from .structure import RoleIndex
from .target_context import TargetContext, validate_context

BREAKS=frozenset(('BREAKOUT','BOS','SWEEP_BOS','EXTERNAL_BREAK'))
POLICY='actual_setup_sponsor_scope_endpoint_v1'


@dataclass(frozen=True)
class ObjectiveResult:
    candidates: tuple[TargetContext,...]
    diagnostics: tuple[dict,...]


def _latest_ranges(structure,at):
    grouped={}
    for row in structure.ranges:
        if row.available_at>at:continue
        old=grouped.get(row.id,())
        if not old or row.available_at>old[0].available_at:grouped[row.id]=(row,)
        elif row.available_at==old[0].available_at:grouped[row.id]=(*old,row)
    result={};ambiguous=set()
    for ident,rows in grouped.items():
        semantics={(r.parent_id,r.direction,r.status,r.protected_turn_id,r.endpoint_turn_id,
                    r.endpoint_liquidity_id,r.origin_ticks,r.endpoint_ticks,
                    r.details.get('endpoint_stage'),bool(r.details.get('endpoint_broken')),
                    r.details.get('target_level_id'),r.details.get('opposing_level_id')) for r in rows}
        if len(semantics)!=1:ambiguous.add(ident)
        else:result[ident]=rows[0]
    return result,ambiguous


def resolve_objectives(sponsors,structures,bars_by_tf,at,entry,side, *, _range_cache=None, _validation_cache=None, _all_bars=None, _named_bars=None, _role_cache=None):
    """Freeze all qualified first objectives at setup publication, without IO.

    `sponsors` are actual positive structural events in the setup's evidence,
    not every historical break. All candidates include exact qualification and
    history/consumption checks; the risk layer chooses nearest after validation.
    """
    at=utc(at);contexts=[];diagnostics=[];seen=set()
    all_bars=_all_bars if _all_bars is not None else tuple(b for rows in bars_by_tf.values() for b in rows)
    named=_named_bars if _named_bars is not None else {b.id:b for b in all_bars}
    role_cache={} if _role_cache is None else _role_cache
    range_cache={} if _range_cache is None else _range_cache
    validation_cache={} if _validation_cache is None else _validation_cache
    for sponsor in sponsors:
        if sponsor.id in seen:continue
        seen.add(sponsor.id)
        base={'sponsor_id':sponsor.id,'tf':sponsor.tf,'policy':POLICY}
        structure=structures.get(sponsor.tf)
        if (structure is None or sponsor.kind not in BREAKS or sponsor.evidence_status!='KNOWN'
                or sponsor.available_at>at or sponsor.side!=side):
            diagnostics.append({**base,'status':'UNRESOLVED','reasons':('sponsor_unqualified',)})
            continue
        key=(sponsor.tf,at)
        if key not in range_cache:range_cache[key]=_latest_ranges(structure,at)
        versions,ambiguous=range_cache[key]
        direct={r.id for r in versions.values() if r.id==sponsor.scope_id
                or r.details.get('seed_break_event_id')==sponsor.id}
        if sponsor.scope_id in ambiguous:
            diagnostics.append({**base,'status':'UNRESOLVED','reasons':('sponsor_scope_versions_ambiguous',)})
            continue
        # A direct range with incompatible latest snapshots cannot disappear
        # into a convenient ancestor or a nearby containing range.
        seeded_ambiguous={r.id for r in structure.ranges if r.id in ambiguous
                          and r.available_at<=at and r.details.get('seed_break_event_id')==sponsor.id}
        if seeded_ambiguous:
            diagnostics.append({**base,'status':'UNRESOLVED','reasons':('seed_scope_versions_ambiguous',)})
            continue
        linked=set(direct)
        for ident in tuple(direct):
            current=versions.get(ident);trail=set()
            while current is not None and current.parent_id is not None and current.parent_id not in trail:
                trail.add(current.id);parent=versions.get(current.parent_id)
                if parent is None:break
                linked.add(parent.id);current=parent
        if not direct:
            diagnostics.append({**base,'status':'UNRESOLVED','reasons':('no_explicit_sponsor_scope_or_seed_link',)})
            continue
        if sponsor.tf not in role_cache:role_cache[sponsor.tf]=RoleIndex(structure.events)
        role_index=role_cache[sponsor.tf]
        for ident in sorted(linked):
            row=versions[ident];reasons=[]
            if row.status!='DEFINED':reasons.append('range_not_defined')
            if row.direction!=side:reasons.append('range_direction_mismatch')
            if row.details.get('endpoint_stage')!='CONFIRMED_DELIVERY':reasons.append('endpoint_not_confirmed')
            if row.details.get('endpoint_broken'):reasons.append('endpoint_already_delivered')
            relation='DIRECT_SCOPE' if ident==sponsor.scope_id else 'EXACT_SEED' if ident in direct else 'EXPLICIT_ANCESTOR'
            provenance={'qualification_rule':POLICY,'source_route':'first_significant_qualified_objective',
                        'sponsor_available_at':sponsor.available_at,'range_available_at':row.available_at,
                        'range_version_id':row.version_id,'scope_relation':relation,
                        'overall_destination_not_replaced':True}
            options=[]
            pools=[p for p in structure.liquidity if p.id==row.endpoint_liquidity_id and p.available_at<=at]
            if len(pools)==1:
                pool=pools[0];pool_reasons=list(reasons)
                if pool.instrument!=sponsor.instrument or pool.tf!=sponsor.tf:pool_reasons.append('objective_instrument_or_tf_mismatch')
                if pool.kind!=('HIGH' if side=='BUY' else 'LOW'):pool_reasons.append('external_endpoint_kind_mismatch')
                if pool.price_ticks!=row.endpoint_ticks:pool_reasons.append('endpoint_pool_price_mismatch')
                options.append((pool,'ERL',None,pool_reasons))
            else:
                diagnostics.append({**base,'scope_id':ident,'status':'UNRESOLVED','reasons':(*reasons,'endpoint_pool_unresolved_or_ambiguous')})
            links={row.details.get(k) for k in ('target_level_id','opposing_level_id') if row.details.get(k) is not None}
            if len(links)==1:
                levels=[l for l in structure.levels if l.id in links and l.available_at<=at]
                if len(levels)==1:
                    level=levels[0];role=role_index.role_at(level,at);kl_reasons=list(reasons)
                    if role!=('SELL' if side=='BUY' else 'BUY'):kl_reasons.append('linked_obstacle_not_opposing')
                    options.append((level,'KL',role,kl_reasons))
                else:diagnostics.append({**base,'scope_id':ident,'status':'UNRESOLVED','reasons':('linked_obstacle_unresolved',)})
            elif len(links)>1:
                diagnostics.append({**base,'scope_id':ident,'status':'UNRESOLVED','reasons':('linked_obstacles_ambiguous',)})
            for reference,kind,role,why in options:
                if not reference.bar_ids or any(ident not in named or named[ident].instrument!=sponsor.instrument
                        or named[ident].tf!=sponsor.tf or not named[ident].complete
                        or named[ident].available_at>at for ident in reference.bar_ids):
                    why.append('objective_source_bars_unresolved_or_unpublished')
                context=TargetContext(instrument=sponsor.instrument,tf=sponsor.tf,side=side,
                    sponsor_id=sponsor.id,scope_id=row.id,available_at=at,
                    objective_kind=kind,objective_ref_id=reference.id,objective_price_ticks=reference.price_ticks,
                    objective_available_at=reference.available_at,objective_formed_at=reference.formed_at,
                    objective_bar_ids=reference.bar_ids,objective_role=role,
                    status='UNRESOLVED' if why else 'KNOWN',reasons=tuple(why),provenance=provenance)
                if context.id not in validation_cache:
                    proxy=reference.price_ticks-(1 if side=='BUY' else -1)
                    _,failure=validate_context(context,at,proxy,side,all_bars,events=structure.events)
                    validation_cache[context.id]=failure
                failure=validation_cache[context.id]
                if (1 if side=='BUY' else -1)*(reference.price_ticks-entry)<=0:
                    failure=(*failure,'context_objective_not_ahead')
                diagnostics.append({**base,'scope_id':row.id,'reference_id':reference.id,'kind':kind,
                    'price_ticks':reference.price_ticks,'status':'UNRESOLVED' if failure else 'QUALIFIED',
                    'reasons':failure,'scope_relation':relation})
                if not failure:contexts.append(context)
    # Same economic objective may have several true sponsor proofs. Retain all
    # proof contexts; risk selection never ranks them by policy-sensitive IDs.
    return ObjectiveResult(tuple(contexts),tuple(diagnostics))


class ObjectiveResolver:
    """Run-local causal caches; no cross-run/prefix state or output mutation."""
    def __init__(self,structures,bars_by_tf):
        self.structures=structures;self.bars=bars_by_tf
        self.all_bars=tuple(b for rows in bars_by_tf.values() for b in rows)
        self.ranges={};self.validation={};self.results={}
        self.named={b.id:b for b in self.all_bars};self.roles={}

    def resolve(self,sponsors,at,entry,side):
        sponsors=tuple(sponsors)
        key=(tuple(e.id for e in sponsors),at,entry,side)
        if key not in self.results:
            self.results[key]=resolve_objectives(sponsors,self.structures,self.bars,at,entry,side,
                _range_cache=self.ranges,_validation_cache=self.validation,_all_bars=self.all_bars,
                _named_bars=self.named,_role_cache=self.roles)
        return self.results[key]

"""Causal story routes; no orders, IO, outcomes or source fixture lookup."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from itertools import islice
from .types import Bar, Clock, Event, Story, StrategyPolicy, stable_id

LADDERS = {"M": "W", "W": "D", "D": "H4", "H4": "H1"}
BREAKS = frozenset(("BREAKOUT", "BOS", "SWEEP_BOS", "EXTERNAL_BREAK"))


@dataclass(frozen=True)
class StoryResult:
    stories: tuple[Story, ...]
    events: tuple[Event, ...]
    reactions: tuple[Event, ...]
    support: tuple[dict, ...]


class _StoryTemporalIndex:
    """Run-local chronology, preserving the public story clock/ID ordering."""
    def __init__(self, stories, reactions):
        self.weekly = {}
        self.opposite = {}
        self.flips = {}
        for story in stories:
            if story.origin_tf == 'W':
                self.weekly.setdefault(story.instrument, []).append(story)
            self.opposite.setdefault((story.instrument, story.side), []).append(story)
            reaction = reactions[story.origin_id]
            scope = story.details.get('scope_type')
            if scope in ('ROOT', 'CHILD') and reaction.kind == 'KL_REJECTION':
                key = (story.instrument, story.side, story.origin_tf, scope, reaction.reference_id)
                self.flips.setdefault(key, []).append(story)
        self.weekly = self._timelines(self.weekly)
        self.opposite = self._timelines(self.opposite)
        self.flips = self._timelines(self.flips)

    @staticmethod
    def _timelines(grouped):
        return {key: (tuple(row.available_at for row in rows), tuple(rows))
                for key, rows in grouped.items()}

    def weekly_before(self, story):
        times, rows = self.weekly.get(story.instrument, ((), ()))
        position = bisect_left(times, story.available_at)
        return rows[position-1] if position else None

    def opposite_after(self, story):
        side = 'SELL' if story.side == 'BUY' else 'BUY'
        times, rows = self.opposite.get((story.instrument, side), ((), ()))
        return islice(rows, bisect_right(times, story.available_at), None)

    def first_flip(self, story):
        side = 'SELL' if story.side == 'BUY' else 'BUY'
        key = (story.instrument, side, story.origin_tf,
               story.details.get('scope_type'), story.destination_ref_id)
        times, rows = self.flips.get(key, ((), ()))
        position = bisect_right(times, story.available_at)
        return rows[position] if position < len(rows) else None


def _close_clock(bar, *available):
    return Clock(bar.end, bar.end, max((bar.available_at,) + available))


def _event(kind, bar, policy, *, side=None, reference_id=None, price=None,
           evidence_ids=(), clock=None, details=None, status="KNOWN"):
    return Event(id=stable_id(kind, bar.id, reference_id, evidence_ids, policy.id),
                 kind=kind, instrument=bar.instrument, tf=bar.tf,
                 clock=clock or _close_clock(bar), side=side,
                 reference_id=reference_id, price_ticks=price, bar_ids=(bar.id,),
                 evidence_ids=evidence_ids, policy_id=policy.id,
                 evidence_status=status, details=details or {})


class _StoryRoleQueries:
    """Run-local role/qualification timelines; no event or output mutation."""
    def __init__(self, events):
        from .structure import RoleIndex
        self.roles=RoleIndex(events)
        self.changes={};self.assessments={};self.qualification_cache={};self.role_cache={}
        self.first_unavailable={}
        for event in events:
            if event.kind=='LEVEL_UNAVAILABLE':
                old=self.first_unavailable.get(event.reference_id)
                if old is None or (event.available_at,event.id)<(old.available_at,old.id):
                    self.first_unavailable[event.reference_id]=event
            if event.kind=='LEVEL_ROLE_CHANGE':
                self.changes.setdefault(event.reference_id,[]).append(event)
            elif event.kind=='IMPULSE_ASSESSMENT' and event.evidence_status=='KNOWN':
                self.assessments.setdefault(event.reference_id,[]).append(event)
        for grouped in (self.changes,self.assessments):
            for key,rows in grouped.items():
                ordered=tuple(sorted(rows,key=lambda e:(e.available_at,e.id)))
                grouped[key]=(tuple(e.available_at for e in ordered),ordered)

    @staticmethod
    def latest(grouped,key,at):
        times,rows=grouped.get(key,((),()))
        position=bisect_right(times,at)
        return rows[position-1] if position else None

    def qualification(self,level,at):
        key=(level.id,at)
        if key not in self.qualification_cache:
            change=self.latest(self.changes,level.id,at)
            assessment=self.latest(self.assessments,change.id,at) if change else None
            qualification=(assessment.details.get('qualification') if assessment else
                           change.details.get('qualification') if change else None)
            self.qualification_cache[key]=(change,assessment,qualification)
        return self.qualification_cache[key]


class _StoryStructureView:
    def __init__(self,result,lower=None):
        self._result=result
        self._story_role_queries=_StoryRoleQueries(result.events)
        self._story_turns={t.id:t for t in result.turns}
        self._story_lower=lower
        self._story_bars={b.id:b for b in lower} if lower is not None else None
        self._story_versions={}
        self._story_range_versions={};self._story_seed_ranges={};self._story_seed_versions={}
        self._story_range_positions={}
        for position,version in enumerate(result.ranges):
            self._story_range_positions.setdefault(id(version),position)
            self._story_range_versions.setdefault(version.id,{}).setdefault(version.available_at,version)
            seed=getattr(version,'details',{}).get('seed_break_event_id')
            if seed is not None:
                self._story_seed_ranges.setdefault(seed,set()).add(version.id)
                self._story_seed_versions.setdefault(seed,{}).setdefault(version.available_at,version)
        for identifier,by_time in self._story_range_versions.items():
            times=tuple(sorted(by_time))
            self._story_range_versions[identifier]=(times,tuple(by_time[t] for t in times))
        for seed,by_time in self._story_seed_versions.items():
            times=tuple(sorted(by_time))
            self._story_seed_versions[seed]=(times,tuple(by_time[t] for t in times))
        self._story_liquidity_environments={}
        self._story_environment_breaks=tuple(sorted((e for e in result.events if e.kind in BREAKS and e.evidence_status=='KNOWN'),key=lambda e:e.available_at))
        self._story_environment_break_times=tuple(e.available_at for e in self._story_environment_breaks)
        self._story_relations={}
        self._story_earliest_break={}
        self._story_break_events={}
        self._story_scope_breaks={}
        self._story_scoped_structural_breaks={}
        for event in result.events:
            if event.kind=='RANGE_BROKEN':
                self._story_scope_breaks.setdefault(event.scope_id,[]).append(event)
            if event.kind in BREAKS:
                self._story_scoped_structural_breaks.setdefault(event.scope_id,[]).append(event)
                if event.evidence_status=='KNOWN':
                    self._story_break_events.setdefault(event.side,[]).append(event)
                old=self._story_earliest_break.get(event.reference_id)
                if old is None or event.available_at<old:
                    self._story_earliest_break[event.reference_id]=event.available_at

        self._story_break_events={side:tuple(sorted(rows,key=lambda e:(e.available_at,e.id)))
                                  for side,rows in self._story_break_events.items()}

    def _range_at(self,identifier,at):
        times,rows=self._story_range_versions.get(identifier,((),()))
        position=bisect_right(times,at)
        return rows[position-1] if position else None

    def _confirmation_range_at(self,event,at):
        direct=self._range_at(event.scope_id,at)
        seeded=_StoryRoleQueries.latest(self._story_seed_versions,event.id,at)
        return max((v for v in (direct,seeded) if v is not None),
                   key=lambda v:(v.available_at,-self._story_range_positions[id(v)]),default=None)

    def _event_versions_at(self,event):
        identifiers=set(self._story_seed_ranges.get(event.id,()))
        if event.scope_id is not None:identifiers.add(event.scope_id)
        versions={}
        for identifier in identifiers:
            version=self._range_at(identifier,event.available_at)
            if version is not None and (version.id==event.scope_id or version.details.get('seed_break_event_id')==event.id):
                versions[identifier]=version
        ordered=tuple(sorted(versions.values(),key=lambda r:(r.available_at,r.id)))
        for version in ordered:
            parent=self._range_at(version.parent_id,event.available_at)
            if parent is not None:versions[parent.id]=parent
        return versions,ordered

    def _versions_at(self,at):
        if at not in self._story_versions:
            versions={}
            for candidate in self._result.ranges:
                if candidate.available_at<=at:
                    previous=versions.get(candidate.id)
                    if previous is None or candidate.available_at>previous.available_at:
                        versions[candidate.id]=candidate
            self._story_versions[at]=(versions,tuple(sorted(versions.values(),key=lambda r:(r.available_at,r.id))))
        return self._story_versions[at]

    def __getattr__(self,name):
        return getattr(self._result,name)


def _indexed_structures(structures,bars_by_tf=None):
    return {tf:result if isinstance(result,_StoryStructureView) else _StoryStructureView(result,(bars_by_tf or {}).get(tf))
            for tf,result in structures.items()}


def _role_qualification(level, result, at):
    queries=getattr(result,'_story_role_queries',None)
    if queries is not None:
        return queries.qualification(level,at)
    changes = sorted((e for e in result.events if e.kind == "LEVEL_ROLE_CHANGE" and
                      e.reference_id == level.id and e.available_at <= at),
                     key=lambda e: (e.available_at, e.id))
    if not changes:
        return None, None, None
    change = changes[-1]
    assessments = sorted((e for e in result.events if e.kind == "IMPULSE_ASSESSMENT" and
                          e.reference_id == change.id and e.available_at <= at and
                          e.evidence_status == "KNOWN"), key=lambda e: (e.available_at, e.id))
    assessment = assessments[-1] if assessments else None
    qualification = (assessment.details.get("qualification") if assessment else
                     change.details.get("qualification"))
    return change, assessment, qualification


def _role(level, result, at, source_profile="bishop_confirmation"):
    from .structure import role_at
    queries=getattr(result,'_story_role_queries',None)
    key=(level.id,at,source_profile)
    if queries is not None and key in queries.role_cache:
        return queries.role_cache[key]
    change, assessment, qualification = _role_qualification(level, result, at)
    # Profiles select source alternatives. An optional numerical assessment is
    # an engineering policy; Bishop raw-close routes have no universal gate.
    raw_routes = ("bishop_confirmation", "bishop_direct", "source_all", "all_routes", "owner_aggressive", "aggressive_direct", "nested_confirmation")
    impulse_required = source_profile.startswith(("core", "plug"))
    if change and (impulse_required or source_profile not in raw_routes):
        if qualification != "IMPULSE_CONFIRMED":
            if queries is not None:queries.role_cache[key]=None
            return None
    role=queries.roles.role_at(level,at) if queries is not None else role_at(level,result.events,at)
    if queries is not None:queries.role_cache[key]=role
    return role


def _role_side(role):
    if isinstance(role, str):
        return {"SUPPORT": "BUY", "RESISTANCE": "SELL", "BUY": "BUY", "SELL": "SELL"}.get(role)
    return getattr(role, "side", None)


def _candle_liquidity_identity(bar, kind):
    """A named candle wick is evidence; its IRL/ERL role still needs context."""
    return {'id':stable_id('source_candle_liquidity',bar.id,kind),
            'instrument':bar.instrument,'tf':bar.tf,'kind':kind,'form':'BAR',
            'price_ticks':bar.low_ticks if kind=='LOW' else bar.high_ticks,
            'formed_at':bar.end,'available_at':bar.available_at,'bar_ids':(bar.id,),
            'role':'UNKNOWN','classification_evidence':()}


def _liquidity_environment(structure, at):
    if isinstance(structure,_StoryStructureView) and at in structure._story_liquidity_environments:
        return structure._story_liquidity_environments[at]
    versions={}
    for r in structure.ranges:
        if r.available_at>at:continue
        old=versions.get(r.id,())
        if not old or r.available_at>old[0].available_at:versions[r.id]=(r,)
        elif r.available_at==old[0].available_at:versions[r.id]=(*old,r)
    roots=[];ambiguous=[]
    for ident,rows in versions.items():
        if not any(r.parent_id is None for r in rows):continue
        states={(r.parent_id,r.direction,r.status,r.origin_ticks,r.endpoint_ticks,
                 r.endpoint_liquidity_id,r.details.get('endpoint_stage'),r.details.get('endpoint_broken')) for r in rows}
        if len(states)>1:ambiguous.append(ident);continue
        r=rows[0]
        if r.parent_id is None and r.status=='DEFINED':roots.append(r)
    sides={r.direction for r in roots}
    if isinstance(structure,_StoryStructureView):
        stop=bisect_right(structure._story_environment_break_times,at)
        latest=structure._story_environment_break_times[stop-1] if stop else None
        first=stop
        while first and structure._story_environment_break_times[first-1]==latest:first-=1
        recent=structure._story_environment_breaks[first:stop]
    else:
        eligible=[e for e in structure.events if e.kind in BREAKS and e.evidence_status=='KNOWN' and e.available_at<=at]
        latest=max((e.available_at for e in eligible),default=None)
        recent=[e for e in eligible if e.available_at==latest]
    state='UNKNOWN' if ambiguous else 'DEFINED_ROOT' if len(sides)==1 else 'CONFLICT' if sides else 'UNKNOWN'
    environment={'as_of':at,'state':state,
                 'side':next(iter(sides)) if len(sides)==1 and not ambiguous else None,
                 'range_ids':tuple(sorted(r.id for r in roots)),
                 'ambiguous_range_ids':tuple(sorted(ambiguous)),
                 'latest_break_ids':tuple(sorted(e.id for e in recent)),
                 'latest_break_sides':tuple(sorted({e.side for e in recent if e.side})),
                 'rule':'DEFINED_ROOT_DIRECTION_NOT_LAST_INTERNAL_BREAK'}
    result=(environment,roots)
    if isinstance(structure,_StoryStructureView):structure._story_liquidity_environments[at]=result
    return result


def _liquidity_origin(previous, origin, side, structure, lower=()):
    swept=_candle_liquidity_identity(previous,'LOW' if side=='BUY' else 'HIGH')
    opposite=_candle_liquidity_identity(previous,'HIGH' if side=='BUY' else 'LOW')
    contact=next((b for b in lower if origin.start<=b.start and b.end<=origin.end
                  and b.available_at<=max(origin.available_at,previous.available_at)
                  and (b.low_ticks<swept['price_ticks'] if side=='BUY' else b.high_ticks>swept['price_ticks'])),None)
    cutoff=contact.start if contact else origin.start
    environment,roots=_liquidity_environment(structure,cutoff)
    pools={pool.id:pool for pool in structure.liquidity if pool.available_at<=cutoff}
    swept['knowledge_at_contact']='KNOWN' if previous.available_at<=cutoff else 'UNPUBLISHED_SOURCE_REFERENCE'
    for point in (swept,opposite):
        point['observed_pool_ids']=tuple(sorted(pool.id for pool in pools.values()
            if pool.kind==point['kind'] and pool.price_ticks==point['price_ticks']
            and pool.form in ('BAR','PRIOR_PERIOD') and previous.id in pool.bar_ids))
    classifications=[]
    for r in roots:
        pool=pools.get(r.endpoint_liquidity_id)
        if (pool is not None and not r.details.get('endpoint_broken')
                and r.details.get('endpoint_stage')=='CONFIRMED_DELIVERY'
                and pool.kind==swept['kind'] and pool.price_ticks==swept['price_ticks']
                and previous.id in pool.bar_ids):
            classifications.append({'role':'ERL','range_id':r.id,'endpoint_liquidity_id':pool.id})
    if environment['state']=='DEFINED_ROOT' and len(roots)==1 and len(classifications)==1:swept['role']='ERL'
    swept['classification_evidence']=tuple(classifications)
    swept['status_at_sweep_close']='TAKEN'
    taken=origin.high_ticks>=opposite['price_ticks'] if side=='BUY' else origin.low_ticks<=opposite['price_ticks']
    opposite['status_at_sweep_close']='TAKEN' if taken else 'NOT_OBSERVED_TAKEN'
    opposite['selected_as_target']=False
    relation=('WITH_STRUCTURE' if environment['side']==side else 'COUNTER_STRUCTURE_RETRACEMENT'
              if environment['side'] is not None else 'UNKNOWN')
    return {'source':'building-bias-part2:30.9-140.2;211.2-309.2;815.7-928.7',
            'swept_liquidity':swept,'opposite_candle_liquidity_candidate':opposite,
            'structural_environment':environment,'relation_to_structure':relation,
            'environment_cutoff_policy':'FIRST_OBSERVED_LOWER_CONTACT_START' if contact else 'ORIGIN_BAR_START_CONSERVATIVE_NO_LOWER_CONTACT',
            'contact_bar_id':contact.id if contact else None,
            'first_obstacle_status':'UNRESOLVED','external_destination_status':'UNRESOLVED',
            'scope':'PRIOR_SINGLE_CANDLE_SUBTYPE_NOT_ALL_LIQUIDITY_FORMS'}


def _reaction_candidates(bars_by_tf, structures, policy):
    structures=_indexed_structures(structures)
    reactions, support = [], []
    for tf in policy.origin_tfs:
        bars = tuple(b for b in bars_by_tf.get(tf, ()) if b.complete)
        if tf not in structures:
            support.append({"route": "origins", "tf": tf, "status": "UNSUPPORTED", "reason": "missing structure"})
            continue
        level_sets = [(tf, structures[tf])]
        if tf == "D" and "W" in structures:
            level_sets.append(("W", structures["W"]))
        for i, bar in enumerate(bars):
            for level_tf, result in level_sets:
                for level in result.levels:
                    if level.instrument != bar.instrument or level.available_at > bar.start:
                        continue
                    side = _role_side(_role(level, result, bar.start, policy.source_profile))
                    if side is None:
                        if bar.low_ticks <= level.price_ticks <= bar.high_ticks:
                            queries=getattr(result,'_story_role_queries',None)
                            if queries is not None:
                                first_unavailable=queries.first_unavailable.get(level.id)
                                unavailable=(first_unavailable,) if first_unavailable and first_unavailable.available_at<=bar.start else ()
                            else:
                                unavailable=sorted((e for e in result.events if e.kind=='LEVEL_UNAVAILABLE'
                                    and e.reference_id==level.id and e.available_at<=bar.start),
                                    key=lambda e:(e.available_at,e.id))
                            change, _, qualification = _role_qualification(level, result, bar.start)
                            if unavailable:
                                reason = ("level_unavailable_after_data_gap" if
                                    "GAP" in str(unavailable[0].details.get("reason", "")).upper()
                                    else "level_unavailable")
                            elif change and qualification != "IMPULSE_CONFIRMED":
                                reason = "selected source route requires impulse qualification; raw role change alone is insufficient"
                            else:
                                reason = "level_unavailable"
                            support.append({"route": "reused_level_origin", "level_id": level.id,
                                "origin_bar_id": bar.id, "status": "UNKNOWN", "reason": reason,
                                "unavailability_event_id": unavailable[0].id if unavailable else None})
                        continue
                    rejected = bar.close_ticks > level.price_ticks if side == "BUY" else bar.close_ticks < level.price_ticks
                    if bar.low_ticks <= level.price_ticks <= bar.high_ticks and rejected:
                        change, assessment, qualification = _role_qualification(level, result, bar.start)
                        epoch = change.id if change else level.id
                        role_evidence = (level.id, epoch) + ((assessment.id,) if assessment else ())
                        reactions.append(_event("KL_REJECTION", bar, policy, side=side,
                            reference_id=level.id, price=level.price_ticks, evidence_ids=role_evidence,
                            details={"origin_tf": tf, "level_tf": level_tf, "role_epoch_id": epoch,
                                     "origin_bar_id": bar.id, "fallback": level_tf != tf,
                                     "source_profile": policy.source_profile,
                                     "role_qualification": "IMPULSE_CONFIRMED" if qualification == "IMPULSE_CONFIRMED" else "RAW_CLOSE_BISHOP_ALTERNATIVE" if change else "FORMATION_OR_QUALIFIED",
                                     "impulse_assessment_id": assessment.id if assessment else None,
                                     "role_route_source": "bishop_key_level_close_through" if change else "initial_level_role"}))
            if i and bars[i-1].segment_id == bar.segment_id:
                previous = bars[i-1]
                for side, swept, price in (("BUY", bar.low_ticks < previous.low_ticks and bar.close_ticks > previous.low_ticks, previous.low_ticks),
                                           ("SELL", bar.high_ticks > previous.high_ticks and bar.close_ticks < previous.high_ticks, previous.high_ticks)):
                    if swept:
                        identity=_liquidity_origin(previous,bar,side,structures[tf],bars_by_tf.get(LADDERS.get(tf),()))
                        reactions.append(_event("PRIOR_CANDLE_SWEEP", bar, policy, side=side,
                            reference_id=previous.id, price=price,
                            evidence_ids=(previous.id,identity['swept_liquidity']['id']),
                            clock=_close_clock(bar,previous.available_at),
                            details={"origin_tf": tf, "level_tf": None, "origin_bar_id": bar.id, "fallback": False,
                                     'liquidity_origin':identity}))
    return reactions, support


def _touch(reaction, origin, lower):
    """First witnessed contact interval; coarse origin alone cannot prove BO order."""
    for bar in lower:
        if not origin.start <= bar.start or bar.end > origin.end:
            continue
        hit = bar.low_ticks <= reaction.price_ticks <= bar.high_ticks
        if reaction.kind == "PRIOR_CANDLE_SWEEP":
            hit = bar.low_ticks < reaction.price_ticks if reaction.side == "BUY" else bar.high_ticks > reaction.price_ticks
        if hit:
            return bar
    return None


def _invalidated(reaction, origin, until, bars, structures):
    for bar in bars:
        if not origin.end < bar.end or bar.available_at > until:
            continue
        if bar.close_ticks < reaction.price_ticks if reaction.side == "BUY" else bar.close_ticks > reaction.price_ticks:
            return True
        if reaction.kind == "KL_REJECTION" and bar.low_ticks <= reaction.price_ticks <= bar.high_ticks:
            # A new same-role reaction must obtain its own positive confirmation.
            return True
    if reaction.kind == "KL_REJECTION":
        result = structures[reaction.details["level_tf"]]
        level = next(l for l in result.levels if l.id == reaction.reference_id)
        if _role_side(_role(level, result, until, reaction.details.get("source_profile", "bishop_confirmation"))) != reaction.side:
            return True
    return False


def _related_reference(event, reference, touch, lower, structure):
    if isinstance(structure,_StoryStructureView) and structure._story_lower is lower:
        key=(event.id,reference.id if reference else None,touch.id)
        if key not in structure._story_relations:
            structure._story_relations[key]=_related_reference_uncached(event,reference,touch,lower,structure)
        return structure._story_relations[key]
    return _related_reference_uncached(event,reference,touch,lower,structure)


def _related_reference_uncached(event, reference, touch, lower, structure):
    """Prove pre-contact reference or a fresh reference in this reaction leg.

    Newly formed turns alone are insufficient: a frozen range snapshot must
    bind its protected origin to the witnessed contact/post-contact leg and
    bind the broken turn to that same lineage. No nearest-turn substitution.
    """
    ref_available = reference.available_at if reference else event.details.get("reference_available_at")
    if ref_available is None:
        return None
    if ref_available <= touch.start:
        return {"kind": "PRE_REACTION_REFERENCE", "evidence_ids": (event.reference_id, touch.id)}
    if reference is None or reference.formed_at < touch.end or reference.available_at > event.clock.occurred_from:
        return None
    turns = structure._story_turns if isinstance(structure,_StoryStructureView) else {turn.id: turn for turn in structure.turns}
    bars = structure._story_bars if isinstance(structure,_StoryStructureView) and structure._story_lower is lower else {bar.id: bar for bar in lower}
    # Each cached snapshot is still selected only at this break's availability.
    if isinstance(structure,_StoryStructureView):
        versions, ordered_versions=structure._event_versions_at(event)
    else:
        versions = {}
        for candidate in structure.ranges:
            if candidate.available_at <= event.available_at:
                previous = versions.get(candidate.id)
                if previous is None or candidate.available_at > previous.available_at:
                    versions[candidate.id] = candidate
        ordered_versions=sorted(versions.values(), key=lambda r: (r.available_at, r.id))
    for lineage in ordered_versions:
        is_event_lineage = event.scope_id == lineage.id or lineage.details.get("seed_break_event_id") == event.id
        if not is_event_lineage or lineage.status == "BROKEN" or lineage.direction != event.side:
            continue
        if reference.id not in (lineage.endpoint_turn_id, lineage.protected_turn_id):
            continue
        protected = turns.get(lineage.protected_turn_id)
        protected_bar = bars.get(protected.anchor_bar_id) if protected else None
        if protected_bar is None or protected.available_at > event.available_at:
            continue
        if protected_bar.segment_id != touch.segment_id or protected_bar.start < touch.start:
            continue
        if protected_bar.end > event.clock.occurred_from:
            continue
        # The episode's range origin must itself touch the reaction price or
        # be descended from a parent which already contains that contact.
        same_contact = protected_bar.id == touch.id
        parent = versions.get(lineage.parent_id)
        parent_known = parent is not None and parent.available_at <= touch.start
        if not same_contact and not parent_known:
            continue
        if parent_known:
            low, high = sorted((parent.origin_ticks, parent.endpoint_ticks))
            if not low <= touch.close_ticks <= high:
                continue
            parent_events=(structure._story_scope_breaks.get(parent.id,())
                           if isinstance(structure,_StoryStructureView) else structure.events)
            if any(e.kind == "RANGE_BROKEN" and e.scope_id == parent.id and
                   touch.available_at < e.available_at <= event.available_at for e in parent_events):
                continue
        # No other lower-bar segment or opposing break may sever the episode.
        if any(b.segment_id != touch.segment_id for b in lower
               if touch.start <= b.start and b.end <= event.clock.occurred_from):
            continue
        lineage_events=(structure._story_scoped_structural_breaks.get(lineage.id,())
                        if isinstance(structure,_StoryStructureView) else structure.events)
        if any(e.kind in BREAKS and e.side != event.side and e.scope_id == lineage.id and
               touch.available_at < e.available_at < event.available_at for e in lineage_events):
            continue
        return {"kind": "POST_REACTION_CHILD_REFERENCE",
                "lineage_id": lineage.id, "lineage_version_id": lineage.version_id,
                "parent_lineage_id": lineage.parent_id,
                "evidence_ids": (touch.id, protected.id, reference.id, lineage.version_id)}
    return None


def _closed_bar_invalidation_at(reaction,origin,bars):
    """Monotone bar-evidence bound; role-only changes are not such a bound.

    A closed origin-TF candle already beyond the reaction, or a renewed KL
    contact, makes every confirmation at/after its publication invalid under
    _invalidated. Later closes cannot undo that historical observation.
    """
    return min((bar.available_at for bar in bars if origin.end<bar.end and
                ((bar.close_ticks<reaction.price_ticks if reaction.side=='BUY' else bar.close_ticks>reaction.price_ticks)
                 or (reaction.kind=='KL_REJECTION' and bar.low_ticks<=reaction.price_ticks<=bar.high_ticks))),default=None)


def _last_pre_touch_reference(touch, lower, structure, side):
    """Owner route: freeze the last known A/V before first possible contact."""
    cached=isinstance(structure,_StoryStructureView) and structure._story_lower is lower
    key=(touch.id,side)
    if cached:
        cache=getattr(structure,'_story_frozen_refs',None)
        if cache is None:cache=structure._story_frozen_refs={}
        if key in cache:return cache[key]
    bar_map=structure._story_bars if cached else {b.id:b for b in lower}
    eligible=[t for t in structure.turns
              if t.instrument==touch.instrument and t.tf==touch.tf
              and t.kind==('H' if side=='BUY' else 'L')
              and t.available_at<=touch.start and t.formed_at<=touch.start
              and t.anchor_bar_id in bar_map
              and bar_map[t.anchor_bar_id].segment_id==touch.segment_id]
    latest=max(((t.formed_at,t.available_at) for t in eligible),default=None)
    matches=[t for t in eligible if (t.formed_at,t.available_at)==latest]
    result=(matches[0],None) if len(matches)==1 else (None,'last_pre_touch_AV_ambiguous' if matches else 'last_pre_touch_AV_unresolved')
    if cached:cache[key]=result
    return result


def _confirm(reaction, origin, tf, lower, structure, bars, structures, *, after=None, reference_profile='source_lineage'):
    touch = _touch(reaction, origin, lower)
    if touch is None:
        return None
    earliest = max(touch.end, after or touch.end)
    if reference_profile=='last_pre_touch' and reaction.kind=='PRIOR_CANDLE_SWEEP':
        previous=next((b for b in bars if b.id==reaction.reference_id),None)
        if previous is None or previous.available_at>touch.start:return None
    frozen=None
    if reference_profile=='last_pre_touch' and reaction.kind in ('KL_REJECTION','PRIOR_CANDLE_SWEEP'):
        frozen,_=_last_pre_touch_reference(touch,lower,structure,reaction.side)
        if frozen is None:return None
    references = structure._story_turns if isinstance(structure,_StoryStructureView) else {t.id: t for t in structure.turns}
    invalid_at=_closed_bar_invalidation_at(reaction,origin,bars) if isinstance(structure,_StoryStructureView) else None
    if invalid_at is not None and max(reaction.available_at,touch.available_at)>=invalid_at:
        return None
    candidates = []
    best_available = None
    candidate_events=(structure._story_break_events.get(reaction.side,())
                      if isinstance(structure,_StoryStructureView) else structure.events)
    for event in candidate_events:
        if invalid_at is not None and event.available_at>=invalid_at:
            break
        # Indexed events are chronological. After a valid minimum is found,
        # later publication clocks cannot beat it; retain the whole tied batch
        # because max(reaction, event, touch) may assign several events one clock.
        if isinstance(structure,_StoryStructureView) and best_available is not None and event.available_at>best_available:
            break
        if event.kind not in BREAKS or event.side != reaction.side or event.evidence_status != "KNOWN":
            continue
        if event.clock.occurred_from <= earliest:
            continue
        earlier_break = (structure._story_earliest_break[event.reference_id]<event.available_at
                         if isinstance(structure,_StoryStructureView) else
                         any(e.kind in BREAKS and e.reference_id == event.reference_id and e.available_at < event.available_at for e in structure.events))
        if earlier_break:
            continue
        if frozen is not None and event.reference_id!=frozen.id:
            continue
        relation = _related_reference(event, references.get(event.reference_id), touch, lower, structure)
        if frozen is not None and relation is not None:
            relation={**relation,'kind':'FROZEN_LAST_PRE_TOUCH_AV',
                      'frozen_reference_id':frozen.id,'frozen_reference_ticks':frozen.price_ticks,
                      'reference_formed_at':frozen.formed_at,'reference_available_at':frozen.available_at,
                      'knowledge_cutoff':touch.start,'touch_interval_end':touch.end}
        if relation is None:
            continue
        available = max(reaction.available_at, event.available_at, touch.available_at)
        if _invalidated(reaction, origin, available, bars, structures):
            continue
        reference=references.get(event.reference_id)
        def stamp(value):return value.isoformat() if hasattr(value,'isoformat') else str(value or '')
        semantic=(event.clock.occurred_to,event.clock.occurred_from,event.available_at,
                  event.kind,event.side or '',getattr(reference,'kind',''),
                  getattr(reference,'price_ticks',None) if getattr(reference,'price_ticks',None) is not None else event.price_ticks or 0,
                  stamp(getattr(reference,'formed_at',None)),stamp(getattr(reference,'available_at',None)),
                  relation.get('kind',''))
        candidates.append((available, semantic, event, touch, relation))
        best_available=available if best_available is None else min(best_available,available)
    if not candidates:return None
    first_clock=min((c[0],c[1][:3]) for c in candidates)
    tied=[c for c in candidates if (c[0],c[1][:3])==first_clock]
    # Policy identity changes event IDs. It cannot rank two economically
    # different simultaneous confirmations; hold genuinely ambiguous geometry.
    if len({c[1][3:] for c in tied})>1:return None
    return tied[0]


def _destination(origin_tf, side, price, at, structures, policy):
    result = structures[origin_tf]
    options = [l for l in result.levels if l.available_at <= at and
               _role_side(_role(l, result, at, policy.source_profile)) == ("SELL" if side == "BUY" else "BUY") and
               (l.price_ticks > price if side == "BUY" else l.price_ticks < price)]
    return min(options, key=lambda l: (abs(l.price_ticks-price), l.available_at, l.id), default=None)


def _story_destinations(origin_tf, side, price, at, structures, policy, bars):
    """Separate a qualified root objective from nearer, non-terminal obstacles.

    Part2 815.7-928.7 distinguishes structural delivery from the first exit
    during a counter-structure retracement. A candle wick alone proves neither.
    """
    result=structures[origin_tf]
    environment,roots=_liquidity_environment(result,at)
    pools={p.id:p for p in result.liquidity if p.available_at<=at}
    known=tuple(b for b in bars if b.available_at<=at)
    qualified=[]
    for root in roots:
        pool=pools.get(root.endpoint_liquidity_id)
        if (pool is None or pool.tf!=origin_tf or pool.price_ticks!=root.endpoint_ticks
                or (known and pool.instrument!=known[0].instrument)
                or root.details.get('endpoint_broken')
                or root.details.get('endpoint_stage')!='CONFIRMED_DELIVERY'
                or pool.kind!=('HIGH' if side=='BUY' else 'LOW')
                or not (pool.price_ticks>price if side=='BUY' else pool.price_ticks<price)):
            continue
        observed=[b for b in known if b.start>=pool.formed_at]
        source_ids={b.id for b in known}
        if (not observed or (pool.bar_ids and not set(pool.bar_ids)<=source_ids)
                or any(b.segment_id!=known[-1].segment_id for b in observed)):
            continue
        if any(b.high_ticks>=pool.price_ticks if side=='BUY' else b.low_ticks<=pool.price_ticks for b in observed):
            continue
        qualified.append((root,pool))
    overall=qualified[0][1] if environment['state']=='DEFINED_ROOT' and len(roots)==1 and len(qualified)==1 and environment['side']==side else None
    kl=_destination(origin_tf,side,price,at,structures,policy)
    # Only positively qualified endpoints and source-qualified opposing KLs;
    # raw BAR/series wick enumeration is deliberately excluded.
    obstacles=[pool for _,pool in qualified]+([kl] if kl is not None else [])
    obstacle=min(obstacles,key=lambda p:(abs(p.price_ticks-price),p.available_at,p.price_ticks),default=None)
    destination=overall or kl
    detail={'overall_objective':({'id':overall.id,'price_ticks':overall.price_ticks,
             'range_id':qualified[0][0].id,'role':'ERL','available_at':overall.available_at} if overall else None),
            'first_obstacle':({'id':obstacle.id,'price_ticks':obstacle.price_ticks,
             'domain':'EXTERNAL_LIQUIDITY' if any(obstacle.id==p.id for _,p in qualified) else 'KEY_LEVEL_EXIT_CANDIDATE'} if obstacle else None),
            'destination_domain':'EXTERNAL_LIQUIDITY' if overall else 'KEY_LEVEL_EXIT_CANDIDATE',
            'external_liquidity_destination_status':'QUALIFIED' if overall else 'UNRESOLVED',
            'destination_policy':'confirmed_standing_root_endpoint_with_distinct_first_obstacle_v1',
            'destination_environment':environment,
            'destination_caveat':None if overall else 'No qualified overall endpoint; legacy KL exit/lifecycle retained'}
    return destination,detail


def find_stories(bars_by_tf, structures, policy=StrategyPolicy(), *, include_successor_diagnostics=True):
    """Publish immutable initial stories and later lifecycle observations.

    Inputs must contain only available complete bars from a frozen causal feed.
    Stories retain their initial state; later changes are append-only events.
    The explicit compact projection omits only nonterminal successor diagnostics;
    all story states, destinations, first flips and other terminal events remain.
    """
    if type(include_successor_diagnostics) is not bool:
        raise ValueError('include_successor_diagnostics must be boolean')
    bars_by_tf = {tf: tuple(sorted((b for b in bars if b.complete), key=lambda b: b.end))
                  for tf, bars in bars_by_tf.items()}
    for tf, bars in bars_by_tf.items():
        if any(b.tf != tf for b in bars):
            raise ValueError("bar timeframe does not match its input key")
        if any(a.end > b.start for a, b in zip(bars, bars[1:])):
            raise ValueError("overlapping story input bars")
    instruments = {b.instrument for bars in bars_by_tf.values() for b in bars}
    if len(instruments) > 1:
        raise ValueError("story analysis requires one instrument")
    structures=_indexed_structures(structures,bars_by_tf)
    bar_map = {b.id: b for bars in bars_by_tf.values() for b in bars}
    reactions, support = _reaction_candidates(bars_by_tf, structures, policy)
    stories, events = [], []
    for reaction in reactions:
        origin = bar_map[reaction.details["origin_bar_id"]]
        tf = LADDERS.get(origin.tf)
        if tf not in structures or tf not in bars_by_tf:
            support.append({"route": reaction.kind, "tf": origin.tf, "status": "UNSUPPORTED", "reason": "missing confirmation timeframe"})
            continue
        fallback = reaction.details["fallback"]
        if fallback:
            weekly = [r for r in reactions if r.tf == "W" and r.kind == "KL_REJECTION" and
                      r.reference_id == reaction.reference_id and r.side == reaction.side and r.available_at <= reaction.available_at]
            if not weekly:
                continue
            count = max(policy.fallback_rejections, 2 if "plug" in policy.source_profile else 1)
            daily = [r for r in reactions if r.tf == "D" and r.reference_id == reaction.reference_id and
                     r.side == reaction.side and r.details.get("role_epoch_id") == reaction.details.get("role_epoch_id") and
                     weekly[-1].available_at <= r.available_at <= reaction.available_at]
            required_bars = list(bars_by_tf["D"])
            idx = required_bars.index(origin)
            expected_ids = {b.id for b in required_bars[max(0, idx-count+1):idx+1]}
            counted = [r for r in daily if r.details["origin_bar_id"] in expected_ids]
            if len({r.details["origin_bar_id"] for r in counted}) < count:
                continue
        reference_profile=policy.bias_reference_profile
        frozen=None
        if reference_profile=='last_pre_touch' and reaction.kind in ('KL_REJECTION','PRIOR_CANDLE_SWEEP'):
            first_touch=_touch(reaction,origin,bars_by_tf[tf])
            if first_touch is not None:
                frozen,reason=_last_pre_touch_reference(first_touch,bars_by_tf[tf],structures[tf],reaction.side)
                if frozen is not None:
                    events.append(_event('BIAS_REFERENCE_FROZEN',first_touch,policy,side=reaction.side,
                        reference_id=frozen.id,price=frozen.price_ticks,
                        evidence_ids=(reaction.id,first_touch.id,frozen.id),
                        clock=Clock(first_touch.start,first_touch.end,max(reaction.available_at,first_touch.available_at)),
                        details={'rule':'LAST_KNOWN_PRE_TOUCH_AV','origin_tf':origin.tf,'confirmation_tf':tf,
                                 'reaction_id':reaction.id,'origin_kind':reaction.kind,'knowledge_cutoff':first_touch.start,
                                 'reference_formed_at':frozen.formed_at,'reference_available_at':frozen.available_at}))
                else:
                    support.append({'reaction_id':reaction.id,'route':'last_pre_touch_external_break',
                                    'status':'WAIT_CONFIRMATION','reason':reason})
        answer = _confirm(reaction, origin, tf, bars_by_tf[tf], structures[tf], bars_by_tf[origin.tf], structures,
                          reference_profile=reference_profile)
        route = "weekly_level_daily_fallback" if fallback else "kl_structural" if reaction.kind == "KL_REJECTION" else "candle_sweep_structural"
        intermediate = None
        if reference_profile=="source_lineage" and origin.tf == "W" and "H4" in structures and "H4" in bars_by_tf:
            # Explicit W rejection -> D engulf -> H4 structure cascade.
            daily = bars_by_tf["D"]
            touch = _touch(reaction, origin, daily)
            if touch:
                for i, current in enumerate(daily):
                    if not i or current.end <= touch.end:
                        continue
                    previous = daily[i-1]
                    engulf = (current.close_ticks > previous.open_ticks and current.open_ticks <= previous.close_ticks and previous.side == "SELL" and current.side == "BUY") if reaction.side == "BUY" else (current.close_ticks < previous.open_ticks and current.open_ticks >= previous.close_ticks and previous.side == "BUY" and current.side == "SELL")
                    if not engulf:
                        continue
                    # Terminal relation still uses original Weekly reaction;
                    # the structural close must follow the engulf occurrence.
                    cascade = _confirm(reaction, origin, "H4", bars_by_tf["H4"], structures["H4"], bars_by_tf[origin.tf], structures, after=current.end,reference_profile=reference_profile)
                    if cascade and (answer is None or (max(cascade[0], current.available_at), cascade[1]) < answer[:2]):
                        answer = cascade
                        intermediate = _event("ENGULF_CONTEXT", current, policy, side=reaction.side,
                                              evidence_ids=(reaction.id, previous.id),
                                              details={"definition": "body_engulf_v1_implementation_choice"})
                        events.append(intermediate)
                        route, tf = "weekly_daily_engulf_h4_cascade", "H4"
                        break
        if (reference_profile=='last_pre_touch' and reaction.kind in ('KL_REJECTION','PRIOR_CANDLE_SWEEP')
                and (answer is None or answer[0]>reaction.available_at)):
            events.append(_event('BIAS_WAIT_EXTERNAL_BREAK',origin,policy,side=reaction.side,
                reference_id=reaction.id,evidence_ids=(reaction.id,),status='UNRESOLVED',
                details={'rule':'LAST_KNOWN_PRE_TOUCH_AV','confirmation_tf':tf,
                         'frozen_reference_id':frozen.id if frozen is not None else None,
                         'reason':'required_last_pre_touch_break_not_confirmed'}))
        if answer is None:
            support.append({"reaction_id": reaction.id, "route": route, "status": "WAIT_CONFIRMATION", "reason": "no fresh related structural break with known ordering/reference"})
            continue
        available, _, confirmation, touch, relation = answer
        if intermediate:
            available = max(available, intermediate.available_at)
        if fallback:
            # The fallback is only a fallback while W has no related D break.
            weekly_origin = bar_map[weekly[-1].details["origin_bar_id"]]
            parent_confirmation = _confirm(weekly[-1], weekly_origin, "D", bars_by_tf["D"], structures["D"], bars_by_tf["W"], structures,reference_profile=reference_profile)
            if parent_confirmation and parent_confirmation[0] <= available:
                continue
        current_bars = [b for b in bars_by_tf[origin.tf] if b.available_at <= available]
        current_price = current_bars[-1].close_ticks
        target, destination_details = _story_destinations(origin.tf, reaction.side, current_price, available, structures, policy, bars_by_tf[origin.tf])
        relation_event = _event("REACTION_CONFIRMATION_LINK", origin, policy, side=reaction.side,
            reference_id=confirmation.id, evidence_ids=(reaction.id, confirmation.id) + relation["evidence_ids"],
            clock=Clock(confirmation.clock.occurred_from, confirmation.clock.occurred_to, available),
            details=relation)
        events.append(relation_event)
        evidence = (reaction.id, touch.id, confirmation.id, relation_event.id) + ((intermediate.id,) if intermediate else ())
        if isinstance(structures[tf],_StoryStructureView):
            scoped_range=structures[tf]._confirmation_range_at(confirmation,available)
        else:
            ranges = [r for r in structures[tf].ranges if r.available_at <= available and
                      (r.id == confirmation.scope_id or r.details.get("seed_break_event_id") == confirmation.id)]
            scoped_range = max(ranges, key=lambda r: r.available_at, default=None)
        story = Story(id=stable_id("story", evidence, route, policy.id), instrument=origin.instrument,
                      side=reaction.side, origin_tf=origin.tf, level_tf=reaction.details["level_tf"],
                      confirmation_tf=tf, route=route, source_profile=policy.source_profile,
                      clock=Clock(confirmation.clock.occurred_from, confirmation.clock.occurred_to, available),
                      origin_id=reaction.id, confirmation_id=confirmation.id,
                      level_id=reaction.reference_id if reaction.kind == "KL_REJECTION" else None,
                      scope_id=scoped_range.id if scoped_range else confirmation.scope_id, destination_ticks=target.price_ticks if target else None,
                      destination_ref_id=target.id if target else None, evidence_ids=evidence,
                      details={"policy_id": policy.id, "reaction_bar_id": origin.id,
                               "role_epoch_id": reaction.details.get("role_epoch_id"),
                               "role_qualification": reaction.details.get("role_qualification"),
                               "role_route_source": reaction.details.get("role_route_source"),
                               **destination_details,
                               'liquidity_origin':reaction.details.get('liquidity_origin'),
                               "intermediate_tf": "D" if intermediate else None,
                               "confirmation_relation": relation["kind"],
                               "bias_reference_profile":reference_profile,
                               "frozen_external_reference_id":relation.get("frozen_reference_id"),
                               "frozen_external_reference_ticks":relation.get("frozen_reference_ticks"),
                               "confirmation_lineage_id": relation.get("lineage_id"),
                               "protected_origin_status": "KNOWN" if scoped_range and scoped_range.status == "DEFINED" else "UNKNOWN",
                               "protected_turn_id": scoped_range.protected_turn_id if scoped_range else None,
                               "scope_type": scoped_range.details.get("scope_type") if scoped_range else "LOCAL",
                               "initial_weekly_relation": "UNKNOWN"})
        stories.append(story)
    stories.sort(key=lambda s: (s.available_at, s.id))
    reaction_map = {r.id: r for r in reactions}
    temporal = _StoryTemporalIndex(stories, reaction_map)
    # Weekly snapshots use only information already known at each eligibility.
    from dataclasses import replace
    decorated = []
    for story in stories:
        parent = temporal.weekly_before(story)
        relation = "ALIGNED" if parent and parent.side == story.side else "COUNTER_WEEKLY" if parent else "UNKNOWN"
        decorated.append(replace(story, parent_id=parent.id if parent else None,
            details={**story.details, "initial_weekly_relation": relation,
                     "owner_selection": "BLOCKED_COUNTERWEEKLY" if relation == "COUNTER_WEEKLY" and not policy.allow_counterweekly else "CANDIDATE",
                     "counterweekly_target_guard_required": relation == "COUNTER_WEEKLY"}))
    stories = decorated
    for story in stories:
        obstacle=story.details.get('first_obstacle')
        if obstacle and obstacle['id']!=story.destination_ref_id:
            first=next((b for b in bars_by_tf[story.origin_tf] if b.start>=story.available_at
                        and b.low_ticks<=obstacle['price_ticks']<=b.high_ticks),None)
            if first:
                events.append(_event('STORY_FIRST_OBSTACLE_REACHED',first,policy,side=story.side,
                    reference_id=story.id,price=obstacle['price_ticks'],
                    evidence_ids=(story.id,obstacle['id']),
                    details={'pending_action':'NONE','position_action':'NONE','overall_bias_retired':False}))
        for bar in bars_by_tf[story.origin_tf]:
            if bar.start < story.available_at:
                continue
            if story.destination_ticks is not None and bar.low_ticks <= story.destination_ticks <= bar.high_ticks:
                events.append(_event("STORY_DESTINATION_REACHED", bar, policy, side=story.side,
                    reference_id=story.id, price=story.destination_ticks, clock=bar.clock,
                    evidence_ids=(story.id, story.destination_ref_id),
                    details={"pending_action": "CANCEL_DEPENDENT", "position_action": "NONE"}))
                break
        first_flip = temporal.first_flip(story) if not include_successor_diagnostics else None
        successors = temporal.opposite_after(story) if include_successor_diagnostics else ((first_flip,) if first_flip else ())
        for successor in successors:
            r = reaction_map[successor.origin_id]
            if successor.origin_tf == story.origin_tf and successor.details.get("scope_type") == story.details.get("scope_type") and story.details.get("scope_type") in ("ROOT", "CHILD"):
                # Positive opposite origin/confirmation, same story scope.
                kind = "STORY_FLIPPED" if r.reference_id == story.destination_ref_id and r.kind == "KL_REJECTION" else "OPPOSITE_STORY_CONFIRMED"
            else:
                kind = "STORY_RETRACEMENT_EVIDENCE"
            origin = bar_map[successor.details["reaction_bar_id"]]
            events.append(_event(kind, origin, policy, side=successor.side,
                reference_id=story.id, evidence_ids=(story.id, successor.id), clock=successor.clock,
                details={"successor_story_id": successor.id,
                         "pending_action": "CANCEL_DEPENDENT" if kind == "STORY_FLIPPED" else "REASSESS_SETUP_DEPENDENCIES",
                         "position_action": "NONE"}))
            if kind == "STORY_FLIPPED":
                break
        result=structures[story.confirmation_tf]
        observations=(result._story_scope_breaks.get(story.scope_id,())
                      if isinstance(result,_StoryStructureView) else result.events)
        for observation in observations:
            if observation.kind == "RANGE_BROKEN" and observation.scope_id == story.scope_id and observation.available_at > story.available_at:
                events.append(Event(id=stable_id("story_invalidated", story.id, observation.id, policy.id),
                    kind="STORY_INVALIDATED", instrument=story.instrument, tf=story.origin_tf,
                    side=story.side, clock=observation.clock, reference_id=story.id,
                    evidence_ids=(story.id, observation.id), policy_id=policy.id,
                    details={"pending_action": "CANCEL_DEPENDENT", "position_action": "NONE",
                             "opposite_direction_confirmed": False}))
                break
    support.extend(({"route": "engulf_started_previous_story_exception", "status": "UNSUPPORTED", "reason": "source exception does not establish executable scope/geometry"},
                    {"route": "experience_based_no_daily_structure", "status": "UNSUPPORTED", "reason": "discretionary source route lacks positive mechanical Daily evidence"},
                    {"route": "protected_story_origin", "status": "KNOWN" if stories and all(s.details.get("protected_origin_status") == "KNOWN" for s in stories) else "UNKNOWN", "reason": "DEFINED scoped lineage required; no reaction wick substitution"}))
    # Local obstacle observations cannot outlive the story they describe.
    terminal={}
    for e in events:
        if e.kind in ('STORY_DESTINATION_REACHED','STORY_INVALIDATED','STORY_FLIPPED'):
            terminal[e.reference_id]=min(terminal.get(e.reference_id,e.available_at),e.available_at)
    events=[e for e in events if e.kind!='STORY_FIRST_OBSTACLE_REACHED'
            or e.reference_id not in terminal or e.available_at<terminal[e.reference_id]]
    return StoryResult(tuple(stories), tuple(sorted(events, key=lambda e: (e.available_at, e.id))),
                       tuple(reactions), tuple(support))

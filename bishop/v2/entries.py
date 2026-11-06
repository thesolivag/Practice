"""Named, causal entry alternatives. Numerical geometry is OUR CHOICE.

All candidates retain their family. Missing protection/ERL remains unresolved;
no fixture, later performance or expected future sweep controls eligibility.
"""
from __future__ import annotations
from dataclasses import dataclass, replace, is_dataclass
from datetime import timedelta
from bisect import bisect_left,bisect_right
from .types import Clock, Event, Setup, Liquidity, stable_id, utc
from .risk import plan

BREAKS = frozenset(('BREAKOUT', 'BOS', 'SWEEP_BOS', 'EXTERNAL_BREAK'))
FAMILIES = ('direct_h4', 'direct_h2', 'confirmation_bo', 'confirmation_sweep_bos',
            'confirmation_engulfed_oc', 'confirmation_standing_extreme',
            'engulf_av_retest', 'oc_break_retest', 'engulf_irl_retest',
            'aggressive_kl_imbalance', 'nested_confirmation')


@dataclass(frozen=True)
class Imbalance:
    id: str
    instrument: str
    tf: str
    low_ticks: int
    high_ticks: int
    side: str
    available_at: object
    bar_ids: tuple[str, ...]
    policy_id: str


@dataclass(frozen=True)
class EntryResult:
    setups: tuple[Setup, ...]
    events: tuple[Event, ...]
    support: tuple[dict, ...]
    imbalances: tuple[Imbalance, ...]


def _role(level, structure, at):
    from .structure import role_at
    return role_at(level, structure.events, at)


def _direction_role(side):
    return 'SUPPORT' if side == 'BUY' else 'RESISTANCE'


def _imbalance(bars, policy):
    out=[]
    for i in range(2, len(bars)):
        a, m, b=bars[i-2:i+1]
        if len({a.segment_id,m.segment_id,b.segment_id}) != 1:
            continue
        if a.high_ticks < b.low_ticks:
            lo,hi,side=a.high_ticks,b.low_ticks,'BUY'
        elif b.high_ticks < a.low_ticks:
            lo,hi,side=b.high_ticks,a.low_ticks,'SELL'
        else:
            continue
        out.append(Imbalance(stable_id('fvg',a.id,m.id,b.id,policy.id),b.instrument,b.tf,
                             lo,hi,side,max(x.available_at for x in (a,m,b)),
                             (a.id,m.id,b.id),policy.id))
    return out


def _atr(bars, at, policy):
    known=[b for b in bars if b.available_at <= at]
    if len(known)<policy.near_atr_period:
        return None
    values=[]
    for i in range(len(known)-policy.near_atr_period,len(known)):
        b=known[i]; p=known[i-1].close_ticks if i else b.open_ticks
        values.append(max(b.high_ticks-b.low_ticks,abs(b.high_ticks-p),abs(b.low_ticks-p)))
    return sum(values)/len(values)*float(policy.near_atr_fraction)


def _engulfs(a,b,side):
    if a.segment_id != b.segment_id or a.side == side or a.side is None or b.side != side:
        return False
    return (min(b.open_ticks,b.close_ticks)<=min(a.open_ticks,a.close_ticks)
            and max(b.open_ticks,b.close_ticks)>=max(a.open_ticks,a.close_ticks)
            and (b.close_ticks>a.open_ticks if side=='BUY' else b.close_ticks<a.open_ticks))


def _is_active(story, at, story_events):
    for event in story_events:
        if event.available_at>at:
            continue
        if (event.reference_id==story.id or event.details.get('story_id')==story.id):
            if event.kind in ('STORY_SUSPENDED','STORY_RETIRED','STORY_INVALIDATED','STORY_FLIPPED','DESTINATION_REACHED','STORY_DESTINATION_REACHED'):
                return False
    return True




class _RiskObjectIndex:
    """Run-local memo of the exact publication/segment filter used by risk.plan."""
    def __init__(self, levels, liquidity):
        self.levels=levels;self.liquidity=liquidity;self.cache={}

    def at(self, at, segment_start):
        key=(at,segment_start)
        if key not in self.cache:
            def visible(obj):
                return obj.available_at<=at and (segment_start is None or obj.formed_at>=segment_start)
            self.cache[key]=(tuple(x for x in self.levels if visible(x)),
                             tuple(x for x in self.liquidity if visible(x)))
        return self.cache[key]


class _PoolSelectionIndex:
    """The original pool predicate, narrowed by formation time, in input order."""
    def __init__(self, pools):
        grouped={};parents={}
        for position,pool in enumerate(pools):
            if pool.form in ('BAR','PRIOR_PERIOD','SESSION') and pool.details.get('role')!='IRL':
                continue
            row=(pool.formed_at,position,pool)
            grouped.setdefault((pool.tf,pool.kind),[]).append(row)
            for parent in {pool.details.get(k) for k in ('parent_break_id','breakout_id')} - {None}:
                parents.setdefault((pool.tf,pool.kind,parent),[]).append(row)
        self.groups={}
        for key,rows in (*grouped.items(),*parents.items()):
            ordered=tuple(sorted(rows,key=lambda row:(row[0],row[1])))
            self.groups[key]=(tuple(row[0] for row in ordered),ordered)

    def select(self,tf,side,at,after,segment_start,*,parent_id=None):
        key=(tf,'LOW' if side=='BUY' else 'HIGH')
        if parent_id is not None:key=(*key,parent_id)
        times,rows=self.groups.get(key,((),()))
        lo=bisect_left(times,max(after,segment_start));hi=bisect_right(times,at)
        selected=[row for row in rows[lo:hi] if segment_start<=row[2].available_at<=at]
        return tuple(row[2] for row in sorted(selected,key=lambda row:row[1]))


class _NestedPairIndex:
    """Exact adjacent patterns grouped by shared episode segment, never by age."""
    def __init__(self,bars_by_tf):
        standing={};engulf={}
        for tf,bars in bars_by_tf.items():
            if tf not in ('H1','M30','M15','M5'):continue
            for a,b in zip(bars,bars[1:]):
                if a.segment_id!=b.segment_id:continue
                for side in ('BUY','SELL'):
                    if tf=='H1':
                        valid=(b.low_ticks<a.low_ticks and b.high_ticks<a.high_ticks and b.close_ticks>a.low_ticks) if side=='BUY' else (b.high_ticks>a.high_ticks and b.low_ticks>a.low_ticks and b.close_ticks<a.high_ticks)
                        if valid:standing.setdefault((side,b.segment_id),[]).append((a,b))
                    elif a.end==b.start and _engulfs(a,b,side):
                        engulf.setdefault((tf,side,b.segment_id),[]).append((a,b))
        self.standing={key:(tuple(a.start for a,b in pairs),tuple(pairs)) for key,pairs in standing.items()}
        self.engulf={key:(tuple(b.end for a,b in pairs),tuple(pairs)) for key,pairs in engulf.items()}

    def standing_after(self,side,segment,at):
        times,pairs=self.standing.get((side,segment),((),()))
        return pairs[bisect_left(times,at):]

    def engulf_after(self,tf,side,segment,at):
        times,pairs=self.engulf.get((tf,side,segment),((),()))
        return pairs[bisect_left(times,at):]


class _NestedWitnessIndex:
    """Exact two-clock witness query with original input-order tie priority.

    Rows are already ordered by reaction start / formation-level order. The
    latest reaction-publication clock wins after both story cutoffs; a tie
    keeps the first original row. Suffix maxima over parent publication make
    each query logarithmic without imposing an age or history window.
    """
    def __init__(self,rows):
        ordered=sorted(((row[2].available_at,position,row[0].available_at,row)
                        for position,row in enumerate(rows)),key=lambda item:(item[0],item[1]))
        self.parents=tuple(item[0] for item in ordered)
        self.best=[None]*len(ordered);self.reaction_clocks=[None]*len(ordered)
        best=None
        for i in range(len(ordered)-1,-1,-1):
            _,position,clock,row=ordered[i]
            if best is None or clock>best[0] or (clock==best[0] and position<best[1]):
                best=(clock,position,row)
            self.reaction_clocks[i]=best[0];self.best[i]=best[2]

    def query(self,reaction_after,parent_after):
        first=bisect_left(self.parents,parent_after)
        if first==len(self.parents) or self.reaction_clocks[first]<reaction_after:
            return None
        return self.best[first]


class _ReactionEligibilityIndex:
    """First admissible parent per identical latest-reaction visibility key.

    All parent variants for one reaction bar/level have the same visibility
    and selection key. After story-clock filtering only their first input row
    can ever be selected; later parents cannot become an invalidation fallback.
    Keep selected original positions so distinct tied bars retain their order.
    """
    def __init__(self,rows):
        groups={}
        for position,row in enumerate(rows):
            bar,level,parent,_=row
            key=(bar.id,bar.end,bar.available_at,level.id)
            groups.setdefault(key,[]).append((parent.available_at,position,row))
        self.groups=[];self.cache={}
        for key,group in groups.items():
            ordered=sorted(group,key=lambda item:(item[0],item[1]))
            best=[None]*len(ordered);selected=None
            for i in range(len(ordered)-1,-1,-1):
                _,position,row=ordered[i]
                if selected is None or position<selected[0]:selected=(position,row)
                best[i]=selected
            self.groups.append((key[2],tuple(item[0] for item in ordered),best))

    def for_story(self,reaction_after,parent_after):
        key=(reaction_after,parent_after)
        if key not in self.cache:
            selected=[]
            for published,parents,best in self.groups:
                if published<reaction_after:continue
                first=bisect_left(parents,parent_after)
                if first<len(parents):selected.append(best[first])
            rows=tuple(row for _,row in sorted(selected,key=lambda item:item[0]))
            self.cache[key]=(rows,tuple(row[0].end for row in rows))
        return self.cache[key]


def _story_bar_start(publications,at,monotone):
    """Skip only the already-rejected story-publication prefix, not scan history."""
    return bisect_left(publications,at) if monotone else 0


class _StoryActivityIndex:
    """Exact earliest terminal boundary, indexed once per detection run."""
    def __init__(self, events):
        self.terminal_at={}
        terminal=('STORY_SUSPENDED','STORY_RETIRED','STORY_INVALIDATED','STORY_FLIPPED',
                  'DESTINATION_REACHED','STORY_DESTINATION_REACHED')
        for event in events:
            if event.kind not in terminal:
                continue
            for identifier in (event.reference_id,event.details.get('story_id')):
                if identifier is not None:
                    previous=self.terminal_at.get(identifier)
                    if previous is None or event.available_at<previous:
                        self.terminal_at[identifier]=event.available_at

    def active(self, story, at):
        terminal=self.terminal_at.get(story.id)
        return terminal is None or at<terminal

    def can_emit(self, story, lower):
        first=max(story.available_at,lower) if lower is not None else story.available_at
        return self.active(story,first)


def _pool_taken_before(pool, reaction_bar, bars):
    """A previously witnessed take cannot manufacture another fresh reaction.

    Check only observations available before this reaction starts. This does
    not veto a live anticipatory order from a future sweep or touch.
    """
    return any(x.start >= pool.available_at and x.end <= reaction_bar.start
               and x.available_at <= reaction_bar.start
               and (x.high_ticks > pool.price_ticks if pool.kind == 'HIGH'
                    else x.low_ticks < pool.price_ticks) for x in bars)


class _EpisodeEventIndex:
    """Relevant level/scope observations, retaining original event order."""
    def __init__(self,events):
        self.events=tuple(events);self.references={};self.scopes={};self.cache={}
        for position,event in enumerate(self.events):
            if event.reference_id is not None:self.references.setdefault(event.reference_id,[]).append(position)
            if event.scope_id is not None:self.scopes.setdefault(event.scope_id,[]).append(position)
    def relevant(self,level_id,scope_id):
        key=(level_id,scope_id)
        if key not in self.cache:
            positions=set(self.references.get(level_id,())) if level_id is not None else set()
            if scope_id is not None:positions.update(self.scopes.get(scope_id,()))
            self.cache[key]=tuple(self.events[i] for i in sorted(positions))
        return self.cache[key]


_FIRST_TAKE_UNSET=object()


def _reaction_episode_reason(reaction, candidate_bar, h4_events):
    """Retire entry pairing, never the higher story or a previously placed order.

    Scope/role loss and a fresh same-scope context break are causal boundaries;
    elapsed bar counts and distance are deliberately absent.
    """
    rb, level, parent_break, _ = reaction
    if rb.segment_id != candidate_bar.segment_id:
        return 'reaction_data_segment_changed'
    opposite = 'SELL' if parent_break.side == 'BUY' else 'BUY'
    relevant=h4_events.relevant(level.id,parent_break.scope_id) if isinstance(h4_events,_EpisodeEventIndex) else h4_events
    for event in relevant:
        if (event.kind=='LEVEL_UNAVAILABLE' and event.reference_id==level.id
                and rb.available_at<=event.available_at<=candidate_bar.available_at):
            return 'reaction_H4_level_unavailable'
        if event.available_at <= rb.available_at:
            continue
        if (event.available_at <= candidate_bar.available_at
                and event.kind == 'LEVEL_ROLE_CHANGE'
                and event.reference_id == level.id and event.side == opposite):
            return 'reaction_H4_level_role_lost'
        same_scope = parent_break.scope_id is not None and event.scope_id == parent_break.scope_id
        if not same_scope:
            continue
        if event.available_at <= candidate_bar.available_at and event.kind == 'RANGE_BROKEN':
            return 'reaction_H4_scope_broken'
        # Simultaneous parent/child confirmation is not a later episode.
        # A new context already known before the child starts needs its own
        # liquidity/reaction chain before it can sponsor another CE.
        if (event.available_at <= candidate_bar.start and event.kind in BREAKS
                and event.side == parent_break.side and event.evidence_status == 'KNOWN'):
            return 'reaction_replaced_by_fresh_H4_break'
    return None


def _pool_taken_by(pool, at, bars):
    """A delayed anticipatory limit needs liquidity still intact at placement."""
    return any(b.start >= pool.available_at and b.end <= at and b.available_at <= at
               and (b.high_ticks > pool.price_ticks if pool.kind == 'HIGH'
                    else b.low_ticks < pool.price_ticks) for b in bars)


def _direct_episode_reason(parent_break, at, events, level=None):
    """Do not submit a new direct order from a retired breakout episode.

    This checks only events already known at submission. It never rewrites an
    order placed before the episode changed or requires a future liquidity take.
    """
    opposite = 'SELL' if parent_break.side == 'BUY' else 'BUY'
    relevant=events.relevant(level.id if level is not None else None,parent_break.scope_id) if isinstance(events,_EpisodeEventIndex) else events
    for event in relevant:
        if not parent_break.available_at < event.available_at <= at:
            continue
        if level is not None and event.reference_id == level.id:
            if event.kind == 'LEVEL_UNAVAILABLE':
                return 'direct_level_unavailable'
            if event.kind == 'LEVEL_ROLE_CHANGE' and event.side == opposite:
                return 'direct_level_role_lost'
        if parent_break.scope_id is None or event.scope_id != parent_break.scope_id:
            continue
        if event.kind == 'RANGE_BROKEN':
            return 'direct_scope_broken'
        if event.kind in BREAKS and event.side == parent_break.side and event.evidence_status == 'KNOWN':
            return 'direct_replaced_by_fresh_break'
    return None


def _pool_parent_matches(pool, parent_break):
    """Explicit inducement lineage cannot be borrowed by another breakout."""
    return all(pool.details.get(key) in (None, parent_break.id)
               for key in ('parent_break_id', 'breakout_id'))


def _first_take_for_reaction(pool, reaction_bar, bars, level, parent_break, h4_events, *, first_candidate=_FIRST_TAKE_UNSET):
    """Carry the first take forward within its original, still-valid episode.

    A later KL rejection need not repeat the sweep. Conversely, a subsequent
    take cannot replace a first take belonging to an older or broken episode.
    Only closed observations known by the reaction are considered.
    """
    # Later KL-approach pools belong to one declared parent/level chain.
    # A neighbouring contact cannot borrow their already observed take.
    if pool.details.get('reaction_level_id') not in (None, level.id):
        return None
    if not _pool_parent_matches(pool, parent_break):
        return None
    if first_candidate is _FIRST_TAKE_UNSET:
        first = next((b for b in bars
            if b.start >= pool.available_at and b.end <= reaction_bar.end
            and b.available_at <= reaction_bar.available_at
            and (b.high_ticks > pool.price_ticks if pool.kind == 'HIGH'
                 else b.low_ticks < pool.price_ticks)), None)
    else:
        first=first_candidate
        if first is not None and not (first.start>=pool.available_at and first.end<=reaction_bar.end
                and first.available_at<=reaction_bar.available_at
                and (first.high_ticks>pool.price_ticks if pool.kind=='HIGH' else first.low_ticks<pool.price_ticks)):
            first=None
    if first is None or first.start < max(parent_break.available_at, level.available_at):
        return None
    opposite='SELL' if parent_break.side=='BUY' else 'BUY'
    relevant=h4_events.relevant(level.id,parent_break.scope_id) if isinstance(h4_events,_EpisodeEventIndex) else h4_events
    for event in relevant:
        if not parent_break.available_at < event.available_at <= reaction_bar.available_at:
            continue
        if event.reference_id==level.id and (event.kind=='LEVEL_UNAVAILABLE' or
                (event.kind=='LEVEL_ROLE_CHANGE' and event.side==opposite)):
            return None
        if (parent_break.scope_id is not None and event.scope_id==parent_break.scope_id
                and event.kind=='RANGE_BROKEN'):
            return None
    if _reaction_episode_reason((first, level, parent_break, (pool,)), reaction_bar, h4_events):
        return None
    return first


def _latest_reaction(reactions,ends,candle):
    """Same stable maximum as a full visible-reaction scan, using end index."""
    def key(row):return (row[0].end,row[0].available_at,row[1].id)
    def visible(row):
        bar=row[0]
        return (bar.id==candle.id or bar.end<=candle.start) and bar.available_at<=candle.available_at
    for index in range(bisect_right(ends,candle.end)-1,-1,-1):
        if not visible(reactions[index]):continue
        stop=index+1;chosen_key=key(reactions[index])
        # Preserve max()'s first-input tie behavior, even with duplicate keys.
        while index and key(reactions[index-1])==chosen_key:index-=1
        return next(row for row in reactions[index:stop] if visible(row))
    return None


def _breakout_retest_level(event, candle, levels, side, role_lookup):
    """Resolve the exact A/V invalidated by this close, never a nearby level.

    Structural events name a turn; raw level events may name its level directly.
    A buy retests former A resistance as support; a sell mirrors this at V.
    """
    if (event.instrument!=candle.instrument or event.tf!=candle.tf
            or event.side!=side or event.available_at!=candle.available_at
            or candle.id not in event.bar_ids or event.clock.occurred_to!=candle.end):
        return None,'invalid_breakout_event_metadata'
    opposite='SELL' if side=='BUY' else 'BUY'
    kind='A' if side=='BUY' else 'V'
    linked=[level for level in levels
            if level.instrument==candle.instrument and level.tf==candle.tf
            and level.available_at<=candle.start
            and (level.id==event.reference_id or
                 (event.reference_id is not None and level.details.get('turn_id')==event.reference_id))]
    if len(linked)!=1:
        return None, 'missing_breakout_level_link' if not linked else 'ambiguous_breakout_level_link'
    level=linked[0]
    if (level.kind!=kind or level.side!=opposite
            or level.available_at>candle.start
            or (event.price_ticks is not None and event.price_ticks!=level.price_ticks)):
        return None,'invalid_breakout_level_reference'
    if role_lookup(level,candle.start) not in (opposite,_direction_role(opposite)):
        return None,'breakout_level_not_opposing_before_confirmation'
    if role_lookup(level,event.available_at) not in (side,_direction_role(side)):
        return None,'breakout_level_not_flipped'
    if not (candle.close_ticks>level.price_ticks if side=='BUY' else candle.close_ticks<level.price_ticks):
        return None,'breakout_close_not_beyond_level'
    return level,None


def _protection_episode_bars(first_takes, reaction_bar, bars, *, bar_starts=None):
    """OUR CHOICE bounded linked excursion, frozen at reaction availability.

    Call only after _first_take_for_reaction proves pool/KL/parent/role lineage.
    Never inherit a containing parent's unrelated extremes or future bars.
    """
    first_takes=tuple(first_takes)
    if not first_takes:
        return ()
    start=min(b.start for b in first_takes)
    if bar_starts is not None:
        bars=bars[bisect_left(bar_starts,start):bisect_right(bar_starts,reaction_bar.end)]
    episode=tuple(b for b in bars if start<=b.start and b.end<=reaction_bar.end
                  and b.available_at<=reaction_bar.available_at)
    if (not episode or episode[0].start!=start or episode[-1].id!=reaction_bar.id
            or any(b.segment_id!=reaction_bar.segment_id for b in episode)
            or not all(any(b.id==f.id for b in episode) for f in first_takes)
            or any(a.end!=b.start for a,b in zip(episode,episode[1:]))):
        return ()
    return episode


def detect_setups(bars_by_tf, structures, stories, instrument, policy, *, story_events=(), eligibility_start=None):
    if eligibility_start is not None:
        eligibility_start=utc(eligibility_start)
    from .structure import RoleIndex
    role_indices={tf:RoleIndex(result.events) for tf,result in structures.items()}
    story_events=tuple(story_events)
    activity=_StoryActivityIndex(story_events)
    # Only actual current-entry-TF event lineage can sponsor range protection.
    # A containing price range or a higher-TF context event is not such a link.
    event_scope_index={tf:{e.id:(e.scope_id,e.available_at) for e in result.events}
                       for tf,result in structures.items()}
    completion_events={}
    for tf,result in structures.items():
        index={}
        for event in result.events:
            if event.kind in BREAKS:
                index.setdefault((event.available_at,event.side),[]).append(event)
        completion_events[tf]=index
    role_cache={}
    def cached_role(level, result, at):
        key=(level.id,at)
        if key not in role_cache:
            role_cache[key]=role_indices[level.tf].role_at(level,at)
        return role_cache[key]
    stories=tuple(getattr(stories,'stories',stories))
    from .weekly_context import resolve as resolve_weekly, TERMINAL as WEEKLY_TERMINAL
    weekly_context_cache={}
    weekly_ids={s.id for s in stories if getattr(s,'origin_tf',None)=='W'
                and getattr(s,'instrument',None)==instrument.symbol and s.details.get('scope_type')=='ROOT'}
    weekly_events=tuple(e for e in story_events if e.kind in WEEKLY_TERMINAL
                        and (e.reference_id in weekly_ids or e.details.get('story_id') in weekly_ids)) if weekly_ids else ()
    bars_by_tf={tf:tuple(sorted((b for b in bs if b.complete),key=lambda b:b.start))
                for tf,bs in bars_by_tf.items()}
    segment_starts={}
    for tf, bars in bars_by_tf.items():
        segment_starts[tf]={}
        for bar in bars:
            segment_starts[tf].setdefault(bar.segment_id,bar.start)
    imbalances=tuple(g for tf in policy.entry_tfs for g in _imbalance(bars_by_tf.get(tf,()),policy))
    setups={}; events={}; support=[]
    reaction_takes={}
    reaction_protection={}
    take_link_cache={}
    take_events={};first_take_bars={};episode_cache={}
    episode_events={tf:_EpisodeEventIndex(result.events) for tf,result in structures.items()}
    bar_starts={tf:tuple(b.start for b in bs) for tf,bs in bars_by_tf.items()}
    monotone_publication={tf:all(a.available_at<=b.available_at and a.end<=b.start for a,b in zip(bs,bs[1:])) for tf,bs in bars_by_tf.items()}
    publication_times={tf:tuple(b.available_at for b in bs) for tf,bs in bars_by_tf.items()}
    def episode_for(firsts,rb,bs):
        firsts=tuple(firsts);key=(rb.tf,rb.id,rb.available_at,tuple(sorted({b.id for b in firsts})))
        if key not in episode_cache:
            episode_cache[key]=_protection_episode_bars(firsts,rb,bs,bar_starts=bar_starts[rb.tf])
        return episode_cache[key]
    def linked_takes(hp, rb, bs, level, parent, h4):
        linked=[]
        firsts=[]
        for pool in hp:
            key=(pool.id,rb.id,level.id,parent.id)
            if key not in take_link_cache:
                options={'first_candidate':first_take_bars.get((pool.id,rb.tf))} if monotone_publication[rb.tf] else {}
                take_link_cache[key]=_first_take_for_reaction(pool,rb,bs,level,parent,episode_events['H4'],**options)
            first=take_link_cache[key]
            if first is None or not episode_for((first,),rb,bs): continue
            firsts.append(first)
            take=take_events[(pool.id,first.tf)]
            linked.append((pool,take))
        reaction_takes[(rb.id,level.id,parent.id)]=tuple(t.id for _,t in linked)
        reaction_protection[(rb.id,level.id,parent.id)]=episode_for(firsts,rb,bs)
        return tuple(p for p,_ in linked)
    profile=policy.source_profile
    # Profiles select procedures before outcomes. source_all is the audit view.
    if profile in ('source_all','all_routes'):
        enabled=set(FAMILIES)
    elif profile in ('owner_aggressive','aggressive_direct','plug_and_play'):
        enabled={'direct_h4','direct_h2','aggressive_kl_imbalance'}
    elif profile == 'nested_confirmation':
        enabled={'nested_confirmation'}
    elif profile == 'core_course':
        enabled={'engulf_av_retest','oc_break_retest','engulf_irl_retest'}
    else:
        enabled=set(FAMILIES)-{'direct_h4','direct_h2','aggressive_kl_imbalance','nested_confirmation'}
    formed_pools=[]
    # Explicit plug single/series IRL alternatives, known only at candle close.
    for tf,result in structures.items():
        bs=bars_by_tf.get(tf,())
        for br in result.events:
            if br.kind not in BREAKS or br.side is None: continue
            origin=next((b for b in bs if b.id in br.bar_ids),None)
            if origin is None: continue
            following=[b for b in bs if b.start>=origin.end and b.segment_id==origin.segment_id]
            series=[]
            for b in following:
                contained=b.low_ticks>=origin.low_ticks and b.high_ticks<=origin.high_ticks
                external_sweep=(b.high_ticks>origin.high_ticks and b.close_ticks<=origin.high_ticks) if br.side=='BUY' else (b.low_ticks<origin.low_ticks and b.close_ticks>=origin.low_ticks)
                if not contained and not external_sweep: break
                series.append(b)
                price=min(x.low_ticks for x in series) if br.side=='BUY' else max(x.high_ticks for x in series)
                ids=tuple(x.id for x in series)
                formed_pools.append(Liquidity(id=stable_id('entry_irl',br.id,ids,policy.id),instrument=origin.instrument,
                    tf=tf,kind='LOW' if br.side=='BUY' else 'HIGH',price_ticks=price,
                    formed_at=b.end,available_at=max(br.available_at,*[z.available_at for z in series]),form='BAR' if len(series)==1 else 'SERIES',
                    bar_ids=ids,policy_id=policy.id,details={'role':'IRL','breakout_id':br.id,'convention':'OUR_CHOICE_containment_inclusive_v1'}))
                if external_sweep: break
    if policy.research_later_kl_irl and 'H4' in structures:
        from .liquidity_forms import later_kl_irl
        h4_structure=structures['H4']
        formed_pools.extend(later_kl_irl(bars_by_tf.get('H4',()),h4_structure.levels,
                                      h4_structure.events,policy))
    all_liq=tuple(l for r in structures.values() for l in r.liquidity)+tuple(formed_pools)
    all_levels=tuple(l for r in structures.values() for l in r.levels)
    risk_objects=_RiskObjectIndex(all_levels,all_liq)
    pool_index=_PoolSelectionIndex(all_liq)
    pool_segment_cache={}
    # Publish observed takes independently of whether a later reaction exists.
    # Otherwise adding that later reaction would backdate a new event into an
    # earlier report. One immutable event is shared by related reactions.
    for tf in dict.fromkeys((*policy.entry_tfs,'H1') if 'nested_confirmation' in enabled else policy.entry_tfs):
        for pool in all_liq:
            if pool.tf!='H4': continue
            first=next((b for b in bars_by_tf.get(tf,()) if b.start>=pool.available_at
                and (b.high_ticks>pool.price_ticks if pool.kind=='HIGH' else b.low_ticks<pool.price_ticks)),None)
            if first is None: continue
            take=Event(id=stable_id('entry_first_take',pool.id,first.id,policy.id),
                kind='LIQUIDITY_FIRST_TAKEN',instrument=first.instrument,tf=first.tf,
                clock=Clock(first.start,first.end,max(pool.available_at,first.available_at)),
                side='SELL' if pool.kind=='HIGH' else 'BUY',
                reference_id=pool.id,price_ticks=pool.price_ticks,bar_ids=(first.id,),
                evidence_ids=(pool.id,),policy_id=policy.id,
                details={'link_policy':'first_take_then_same_episode_reaction_v1'})
            events[take.id]=take
            take_events[(pool.id,tf)]=take
            first_take_bars[(pool.id,tf)]=first
    for tf in policy.entry_tfs:
        support.append(dict(tf=tf,route='entries',status='SUPPORTED' if tf in structures and tf in bars_by_tf else 'UNSUPPORTED',
                            families=FAMILIES, enabled_families=tuple(f for f in FAMILIES if f in enabled),
                            numerical_conventions='OUR_CHOICE'))
    support.append(dict(route='optional_nested_confirmation',status='SUPPORTED',enabled='nested_confirmation' in enabled,reason='declared_H1_break_reaction_standing_then_lower_engulf_chain_OUR_CHOICE'))
    support.append(dict(route='pdf_p8_standing_extreme',status='UNRESOLVED',
                        reason='high_swept_low_standing_LONG_reference_pair_unresolved'))

    risk_cache={}
    level_selection_cache={}
    pool_selection_cache={}
    episode_reason_cache={}
    def episode_reason(reaction,bar,h4_events):
        rb,level,parent,_=reaction
        key=(rb.id,level.id,parent.id,bar.id)
        if key not in episode_reason_cache:
            episode_reason_cache[key]=_reaction_episode_reason(reaction,bar,episode_events['H4'])
        return episode_reason_cache[key]

    context_objective_cache={}
    h4_target_structure=structures.get('H4')
    context_bars_index={bar.id:bar for bs in bars_by_tf.values() for bar in bs} if policy.target_profile in ('context_objective','context_h4_kl') else {}
    context_sponsors={e.id:e for e in (h4_target_structure.events if h4_target_structure else ())
                      if e.kind in BREAKS and e.evidence_status=='KNOWN'} if policy.target_profile in ('context_objective','context_h4_kl') else {}

    objective_resolver=None
    objective_sponsors={}
    objective_events=()
    if policy.target_profile=='nearest_erl':
        from .objectives import ObjectiveResolver
        objective_resolver=ObjectiveResolver(structures,bars_by_tf)
        objective_events=tuple(e for result in structures.values() for e in result.events)
        objective_sponsors={e.id:e for e in objective_events
                            if e.kind in BREAKS and e.evidence_status=='KNOWN'}

    def emit(model,story,tf,level,at,causes,protection,liq=(),phase='origin',extra=None,zone_bounds=None,protection_episode=(),confirmation_bars=()):
        if eligibility_start is not None and at < eligibility_start:
            return
        if model not in enabled or story.available_at>at or not activity.active(story,at):
            return
        target_context=None
        context_options={}
        trade_objectives=None
        if policy.target_profile=='nearest_erl':
            sponsors=tuple(objective_sponsors[c] for c in dict.fromkeys(causes) if c in objective_sponsors)
            trade_objectives=objective_resolver.resolve(sponsors,at,level.price_ticks,story.side)
            context_options=dict(trade_objectives=trade_objectives.candidates,
                trade_objective_diagnostics=trade_objectives.diagnostics,
                context_bars=objective_resolver.all_bars,
                context_events=objective_events)
        if policy.target_profile in ('context_objective','context_h4_kl'):
            from .target_context import resolve_context
            sponsors=[context_sponsors[c] for c in dict.fromkeys(causes) if c in context_sponsors]
            if policy.target_profile=='context_h4_kl' and len(sponsors)==1:
                from .target_context import resolve_h4_key_level
                key=('H4_KL',sponsors[0].id,at,story.side,tf,level.price_ticks)
                if key not in context_objective_cache:
                    context_objective_cache[key]=resolve_h4_key_level(sponsors[0],structures['H4'],
                        (*bars_by_tf.get('H4',()),*bars_by_tf.get(tf,())) if tf!='H4' else bars_by_tf.get('H4',()),
                        at,level.price_ticks,story.side,role_lookup=lambda l,t:cached_role(l,structures[l.tf],t))
                target_context=context_objective_cache[key]
            reaction=context_bars_index.get(causes[0]) if causes else None
            if policy.target_profile=='context_objective' and len(sponsors)==1 and reaction is not None and reaction.tf==tf:
                sponsor=sponsors[0]
                snapshot=min(at,reaction.available_at)
                key=(sponsor.id,snapshot,story.side,tf)
                if key not in context_objective_cache:
                    context_objective_cache[key]=resolve_context(sponsor,structures['H4'],(*bars_by_tf.get('H4',()),*bars_by_tf.get(tf,())) if tf!='H4' else bars_by_tf.get('H4',()),
                        snapshot,story.side,role_lookup=lambda l,t:cached_role(l,structures[l.tf],t))
                target_context=context_objective_cache[key]
            context_options=dict(target_context=target_context,context_bars=(*bars_by_tf.get('H4',()),*bars_by_tf.get(tf,())) if tf!='H4' else bars_by_tf.get('H4',()),
                                 context_events=structures['H4'].events if 'H4' in structures else ())
        result=structures[tf]
        if cached_role(level,result,at) not in (_direction_role(story.side),story.side):
            return
        if at not in weekly_context_cache:
            weekly_context_cache[at]=resolve_weekly(stories,weekly_events,at,instrument.symbol)
        weekly=weekly_context_cache[at]
        entry_relation=('ALIGNED' if weekly['side']==story.side else 'COUNTER_WEEKLY') if weekly['status']=='KNOWN' else weekly['status']
        # Keep initial labels intact; only positively resolved current context
        # can replace their use for this new submission.
        selection_relation=entry_relation if weekly['status']=='KNOWN' else story.details.get('initial_weekly_relation')
        initially_blocked=story.details.get('owner_selection')=='BLOCKED_COUNTERWEEKLY'
        if ((not policy.allow_counterweekly and selection_relation=='COUNTER_WEEKLY')
                or (initially_blocked and entry_relation!='ALIGNED')):
            return
        study_pattern=tuple(confirmation_bars or protection)
        # H4 first-take/reaction history qualifies the entry. An explicit
        # adjacent engulfing has its own invalidation candles: never inherit
        # an earlier engulfing's extreme just because the H4 context survives.
        protection=tuple({b.id:b for b in (confirmation_bars or (*protection_episode,*protection))}.values())
        causes=tuple(dict.fromkeys((*causes,*(b.id for b in protection_episode))))
        protection_evidence=tuple(dict.fromkeys((*(b.id for b in confirmation_bars),level.id)
            if confirmation_bars else (*causes,level.id)))
        scope_index=event_scope_index[tf]
        protection_scopes=tuple(dict.fromkeys(scope_index[cause][0] for cause in protection_evidence
            if cause in scope_index and scope_index[cause][0] is not None
            and scope_index[cause][1]<=at))
        risk_key=(story.side,level.price_ticks,at,tf,tuple(b.id for b in protection),
                  protection_evidence,protection_scopes,zone_bounds,
                  getattr(story,'destination_ticks',None),getattr(story,'destination_ref_id',None),
                  story.details.get('counterweekly_target_guard_required'),
                  story.details.get('initial_weekly_relation'),story.details.get('retracement'),
                  entry_relation,weekly['story_ids'],weekly['policy'])
        if policy.target_profile in ('context_objective','context_h4_kl'):risk_key=(*risk_key,getattr(target_context,'id',None))
        if trade_objectives is not None:risk_key=(*risk_key,tuple(c.id for c in trade_objectives.candidates),tuple(causes))
        if risk_key not in risk_cache:
            visible_bars=[b for b in bars_by_tf[tf] if b.available_at<=at]
            segment_start=segment_starts[tf][visible_bars[-1].segment_id] if visible_bars else None
            known_levels,known_liquidity=risk_objects.at(at,segment_start)
            effective_details={**story.details,'entry_weekly_relation':entry_relation,
                               'entry_weekly_context':weekly}
            if is_dataclass(story):
                effective_story=replace(story,details=effective_details)
            else:
                from types import SimpleNamespace
                effective_story=SimpleNamespace(**{**vars(story),'details':effective_details})
            risk_cache[risk_key]=plan(story.side,level.price_ticks,at,tf,bars_by_tf[tf],known_levels,known_liquidity,
                  effective_story,instrument,policy,role_lookup=lambda l,t:cached_role(l,structures[l.tf],t),
                  protection_bars=protection,ranges=result.ranges,zone_bounds=zone_bounds,
                  protection_evidence_ids=protection_evidence,protection_range_ids=protection_scopes,**context_options)
        risk=risk_cache[risk_key]
        sid=stable_id('setup',story.id,tf,model,level.id,tuple(causes),policy.id)
        clock=Clock(at,at,at)
        details=dict(risk.details,study_pattern_bar_ids=tuple(b.id for b in study_pattern),
                     study_stop_policy='current_confirmation_episode_v1',entry_weekly_relation=entry_relation,entry_weekly_context=weekly,
                     confirmation_protection_bar_ids=tuple(b.id for b in confirmation_bars),
                     confirmation_protection_policy='current_adjacent_engulf_pair_v1' if confirmation_bars else None,
                     protection_episode_bar_ids=tuple(b.id for b in protection_episode),
                     protection_episode_policy='linked_first_take_through_reaction_v1_OUR_CHOICE' if protection_episode else None,phase=phase,source_profile=profile,model_enabled=True,
                     causal_selection='first_eligible_then_higher_tf_same_batch_OUR_CHOICE',
                     expected_sweep_is_not_fill_veto=True,**(extra or {}))
        expiry=at+timedelta(minutes=policy.pending_minutes) if policy.pending_minutes else None
        setup=Setup(id=sid,instrument=instrument.symbol,tf=tf,model=model,side=story.side,
            story_id=story.id,clock=clock,entry_ticks=level.price_ticks,stop_ticks=risk.stop_ticks,
            target_ticks=risk.target_ticks,risk_profile=policy.risk_profile,status=risk.status,
            level_id=level.id,liquidity_ids=tuple(l.id for l in liq),
            evidence_ids=tuple(dict.fromkeys((story.id,level.id,*causes))),expires_at=expiry,details=details)
        setups[sid]=setup
        kind='ENTRY_ELIGIBLE' if setup.status=='ELIGIBLE' else 'ENTRY_UNRESOLVED'
        e=Event(id=stable_id(kind,sid),kind=kind,instrument=instrument.symbol,tf=tf,clock=clock,
                side=story.side,reference_id=sid,price_ticks=level.price_ticks,
                evidence_ids=setup.evidence_ids,policy_id=policy.id,evidence_status='KNOWN' if risk.status=='ELIGIBLE' else 'UNRESOLVED',
                details={'model':model,'reasons':risk.details['unresolved_reasons']})
        events[e.id]=e

    def select_level(tf,side,at,reference,*,kind=None,formed_after=None,level_id=None):
        key=(tf,side,at,reference,kind,formed_after,level_id)
        if key in level_selection_cache:
            return level_selection_cache[key]
        result=structures[tf]
        levels=[l for l in result.levels if l.available_at<=at and (level_id is None or l.id==level_id) and (kind is None or l.kind==kind)
                and (formed_after is None or l.formed_at>=formed_after)
                and cached_role(l,result,at) in (_direction_role(side),side)]
        # Nearest same-TF relevant level, never chosen by which later retests.
        levels=[l for l in levels if (l.price_ticks<=reference if side=='BUY' else l.price_ticks>=reference)]
        selected=min(levels,key=lambda l:(abs(reference-l.price_ticks),-l.available_at.timestamp(),l.id)) if levels else None
        level_selection_cache[key]=selected
        return selected

    def pools(tf,side,at,after,*,segment_start=None,parent_id=None):
        key=(tf,side,at,after,segment_start,parent_id)
        if key in pool_selection_cache:
            return pool_selection_cache[key]
        if segment_start is None:
            clock=(tf,at)
            if clock not in pool_segment_cache:
                known=next((b for b in reversed(bars_by_tf[tf]) if b.available_at<=at),None)
                pool_segment_cache[clock]=segment_starts[tf][known.segment_id] if known else at
            segment_start=pool_segment_cache[clock]
        selected=pool_index.select(tf,side,at,after,segment_start,parent_id=parent_id)
        pool_selection_cache[key]=selected
        return selected

    declared_h4_parent_births={}
    for pool in all_liq:
        if pool.tf!='H4':continue
        declared_ids={pool.details.get(tag) for tag in ('parent_break_id','breakout_id')
                      if pool.details.get(tag)}
        if len(declared_ids)!=1:continue
        ident=next(iter(declared_ids))
        key=(pool.kind,pool.details.get('reaction_level_id'))
        births=declared_h4_parent_births.setdefault(key,{})
        births[ident]=min(births.get(ident,pool.available_at),pool.available_at)
    reaction_context_cache={}
    reaction_eligibility_indexes={}
    breakout_level_cache={}
    def reaction_context(tf,side):
        # Geometry and first-take/KL lineage are shared by same-side stories.
        # Story birth and sponsoring-break cutoffs are applied afterwards.
        key=(tf,side)
        if key in reaction_context_cache:return reaction_context_cache[key]
        h4=structures.get('H4');bs=bars_by_tf[tf];rows=[]
        if h4 and tf!='H4':
            breaks=[e for e in h4.events if e.kind in BREAKS and e.side==side and e.evidence_status=='KNOWN']
            for b in bs:
                segment_start=segment_starts[tf][b.segment_id]
                related=[e for e in breaks if e.available_at<=b.start and e.clock.occurred_from>=segment_start]
                if not related:continue
                latest=max(related,key=lambda e:e.available_at)
                for lv4 in h4.levels:
                    if lv4.available_at>b.start:continue
                    if not b.low_ticks<=lv4.price_ticks<=b.high_ticks:continue
                    if not (b.close_ticks>lv4.price_ticks if side=='BUY' else b.close_ticks<lv4.price_ticks):continue
                    if cached_role(lv4,h4,b.start) not in (_direction_role(side),side):continue
                    # Declared inducement belongs to its original breakout/KL.
                    # An unrelated later internal break cannot steal that link.
                    # Untagged pools retain the existing latest-break procedure.
                    pool_kind='LOW' if side=='BUY' else 'HIGH'
                    declared={ident for level_id in (None,lv4.id)
                              for ident,known_at in declared_h4_parent_births.get((pool_kind,level_id),{}).items()
                              if known_at<=b.start}
                    parents=(latest,*(e for e in related if e.id!=latest.id and e.id in declared))
                    for br in parents:
                        hp=pools('H4',side,b.start,br.clock.occurred_from,parent_id=br.id if br.id!=latest.id else None)
                        if br.id!=latest.id:
                            hp=tuple(pool for pool in hp if br.id in
                                (pool.details.get('parent_break_id'),pool.details.get('breakout_id'))
                                and _pool_parent_matches(pool,br))
                            if not hp:continue
                        if not hp and profile not in ('source_all','all_routes','core_course'):continue
                        swept=linked_takes(hp,b,bs,lv4,br,h4)
                        if not swept and profile not in ('source_all','all_routes','core_course'):continue
                        rows.append((b,lv4,br,tuple(swept)))
        reaction_context_cache[key]=tuple(sorted(rows,key=lambda r:(r[0].end,r[0].available_at,r[1].id)))
        return reaction_context_cache[key]

    for story in stories:
        if story.details.get('owner_selection') == 'BLOCKED_COUNTERWEEKLY':
            support.append(dict(route='owner_selection',story_id=story.id,status='BLOCKED_COUNTERWEEKLY'))
        story_can_emit=activity.can_emit(story,eligibility_start)
        for tf in policy.entry_tfs:
            if tf not in structures or tf not in bars_by_tf:
                continue
            bs=bars_by_tf[tf]; result=structures[tf]
            h4=structures.get('H4')
            # Direct readiness: known liquidity, no future sweep/reaction gate.
            if story_can_emit and tf in ('H4','H2') and ('direct_h4' if tf=='H4' else 'direct_h2') in enabled:
                breaks=[e for e in result.events if e.kind in BREAKS and e.side==story.side
                        and e.available_at>=story.clock.occurred_from and e.evidence_status=='KNOWN']
                h4breaks=tuple(e for e in (h4.events if h4 else ()) if e.kind in BREAKS and e.side==story.side
                              and e.available_at>=story.clock.occurred_from and e.evidence_status=='KNOWN') if tf=='H2' else ()
                for br in breaks:
                    parents=[br] if tf=='H4' else []
                    if tf=='H2':
                        # Own H2 structure must occur in the H4 breakout candle,
                        # or in its subsequent episode before a newer H4 BO.
                        enclosing=[]; preceding=[]
                        for p in h4breaks:
                            pb=next((z for z in bars_by_tf.get('H4',()) if z.id in p.bar_ids),None)
                            if pb is not None and pb.start<=br.clock.occurred_from and br.clock.occurred_to<=pb.end:
                                enclosing.append(p)
                            elif p.available_at<=br.clock.occurred_from:
                                preceding.append(p)
                        parents=enclosing or ([max(preceding,key=lambda p:(p.available_at,p.id))] if preceding else [])
                    if not parents:
                        continue
                    parent=min(parents,key=lambda p:(max(p.available_at,br.available_at),p.id))
                    origin_bars=[b for b in bs if b.id in br.bar_ids]
                    if not origin_bars:
                        continue
                    origin_segment_start=segment_starts[tf][origin_bars[-1].segment_id]
                    for pool in pools(tf,story.side,max([b.available_at for b in bs],default=br.available_at),
                                      br.clock.occurred_from,segment_start=origin_segment_start):
                        if not _pool_parent_matches(pool, br):
                            continue
                        at=max(story.available_at,parent.available_at,br.available_at,pool.available_at)
                        known=[b for b in bs if b.available_at<=at]
                        if not known: continue
                        segment_start=segment_starts[tf][known[-1].segment_id]
                        break_bars=[x for x in bs if x.id in br.bar_ids]
                        if (br.clock.occurred_from<segment_start or pool.formed_at<segment_start
                                or not break_bars or break_bars[-1].segment_id!=known[-1].segment_id): continue
                        if tf=='H2':
                            parent_bars=[x for x in bars_by_tf.get('H4',()) if x.id in parent.bar_ids]
                            if not parent_bars or parent_bars[-1].end<=segment_start: continue
                        lv=select_level(tf,story.side,at,known[-1].close_ticks,
                                        level_id=pool.details.get('reaction_level_id'))
                        if lv:
                            reason=('direct_liquidity_already_taken' if _pool_taken_by(pool,at,bs)
                                    else _direct_episode_reason(br,at,episode_events[tf],lv))
                            if reason is None and tf=='H2':
                                reason=_direct_episode_reason(parent,at,episode_events['H4'])
                            if reason:
                                support.append(dict(route='direct_entry_episode',story_id=story.id,
                                    tf=tf,status='RETIRED',reason=reason,parent_break_id=br.id,
                                    level_id=lv.id,pool_id=pool.id,observed_at=at.isoformat()))
                                continue
                            pb=[b for b in known if b.id in pool.bar_ids or b.id in br.bar_ids]
                            emit('direct_h4' if tf=='H4' else 'direct_h2',story,tf,lv,at,(br.id,parent.id,pool.id),pb,(pool,),
                                 phase='continuation' if br.available_at>story.available_at else 'origin',
                                 extra={'h4_breakout_closed_at':parent.available_at.isoformat()})
            # Preserve the original story-specific temporal eligibility.
            reaction_key=(tf,story.side)
            if reaction_key not in reaction_eligibility_indexes:
                reaction_eligibility_indexes[reaction_key]=_ReactionEligibilityIndex(reaction_context(tf,story.side))
            reactions,reaction_ends=reaction_eligibility_indexes[reaction_key].for_story(
                story.available_at,story.clock.occurred_from)
            retired_reactions=set()
            def reaction_for(b):
                # A closed child candle can witness the KL reaction and finish
                # confirmation together; it cannot close the containing H4.
                current=_latest_reaction(reactions,reaction_ends,b)
                if current is None:return None
                # Do not fall back to an even older reaction after the current
                # episode loses its support. A new witnessed reaction replaces it.
                reason=episode_reason(current,b,h4.events)
                if reason:
                    key=(current[0].id,current[1].id,reason)
                    if key not in retired_reactions:
                        support.append(dict(route='entry_reaction_episode',story_id=story.id,
                            tf=tf,status='RETIRED',reason=reason,
                            reaction_bar_id=current[0].id,level_id=current[1].id,
                            parent_break_id=current[2].id,observed_at=b.available_at.isoformat()))
                        retired_reactions.add(key)
                    return None
                return current
            # Only skip the exact story-publication prefix already rejected by
            # the old loop. Non-monotone receipt clocks keep the original scan;
            # original indices and preceding/following candles remain intact.
            first=_story_bar_start(publication_times[tf],story.available_at,monotone_publication[tf])
            for i in range(first,len(bs)):
                b=bs[i]
                if b.available_at<story.available_at: continue
                reaction=reaction_for(b)
                # Keep retired-reaction diagnostics for the full history, but
                # avoid candidate work when no eligible clock can be active.
                if not story_can_emit:
                    continue
                possible_clocks=(b.available_at,bs[i-1].available_at if i else b.available_at,
                                 bs[i+1].available_at if i+1<len(bs) else b.available_at)
                can_submit=(activity.active(story,b.available_at) and
                            (eligibility_start is None or max(possible_clocks)>=eligibility_start))
                if reaction:
                    rb,lv4,hbr,hp=reaction
                    episode=reaction_protection.get((rb.id,lv4.id,hbr.id),())
                    causes=(rb.id,lv4.id,hbr.id,*[p.id for p in hp],
                            *reaction_takes.get((rb.id,lv4.id,hbr.id),()))
                    at=max(story.available_at,b.available_at,rb.available_at,bs[i-1].available_at if i else b.available_at,lv4.available_at,hbr.available_at,*[p.available_at for p in hp])
                    for br in completion_events[tf].get((b.available_at,story.side),()) if hp else ():
                        if br.clock.occurred_to<rb.end: continue
                        reference_key=(tf,story.side,br.id,b.id,b.available_at)
                        if reference_key not in breakout_level_cache:
                            breakout_level_cache[reference_key]=_breakout_retest_level(br,b,result.levels,story.side,
                                lambda level,clock:cached_role(level,result,clock))
                        lv,reason=breakout_level_cache[reference_key]
                        if lv is None:
                            support.append(dict(route='breakout_retest_reference',story_id=story.id,
                                tf=tf,status='UNRESOLVED',reason=reason,breakout_event_id=br.id,
                                reference_id=br.reference_id,observed_at=at.isoformat()))
                            continue
                        model='confirmation_sweep_bos' if br.kind=='SWEEP_BOS' else 'confirmation_bo'
                        emit(model,story,tf,lv,at,(*causes,br.id),(rb,b),hp,protection_episode=episode,
                             extra={'entry_reference_policy':'exact_broken_av_retest_v1',
                                    'breakout_event_id':br.id,'broken_level_id':lv.id,
                                    'broken_level_price_ticks':lv.price_ticks,
                                    'breakout_closed_at':b.available_at.isoformat(),
                                    'entry_requires_later_retest':True})
                    # Preserve breakout-reference diagnostics above even before
                    # the entry window. The remaining routes only emit setups;
                    # emit() would reject all of them at these clocks anyway.
                    if not can_submit:continue
                    # Session OC disrespect permits variable engulf body placement.
                    for lv in result.levels:
                        if lv.kind!='OC' or lv.available_at>b.start or lv.side==story.side: continue
                        if not (b.open_ticks<=lv.price_ticks<b.close_ticks if story.side=='BUY' else b.close_ticks<lv.price_ticks<=b.open_ticks): continue
                        if hp:
                            emit('confirmation_engulfed_oc',story,tf,lv,at,(*causes,b.id),(rb,b),hp,protection_episode=episode,
                                 confirmation_bars=(bs[i-1],b) if i and _engulfs(bs[i-1],b,story.side) else ())
                        if i and _engulfs(bs[i-1],b,story.side):
                            emit('oc_break_retest',story,tf,lv,at,(*causes,b.id),(rb,bs[i-1],b),hp,protection_episode=episode,confirmation_bars=(bs[i-1],b))
                    if i and bs[i-1].segment_id==b.segment_id:
                        a=bs[i-1]
                        standing=(b.low_ticks<a.low_ticks and b.high_ticks<a.high_ticks and b.close_ticks>a.low_ticks) if story.side=='BUY' else (b.high_ticks>a.high_ticks and b.low_ticks>a.low_ticks and b.close_ticks<a.high_ticks)
                        if standing and hp:
                            lv=select_level(tf,story.side,at,b.close_ticks,kind='V' if story.side=='BUY' else 'A',formed_after=a.start)
                            if lv:
                                emit('confirmation_standing_extreme',story,tf,lv,at,(*causes,a.id,b.id),(rb,a,b),hp,
                                     protection_episode=episode,extra={'geometry':'restricted_adjacent_E5_OUR_CHOICE','reference_bar_id':a.id,
                                            'standing_through':b.end.isoformat(),'pdf_p8_mapping':'UNRESOLVED'})
                    if i and _engulfs(bs[i-1],b,story.side):
                        lv=select_level(tf,story.side,at,b.close_ticks,kind='V' if story.side=='BUY' else 'A',formed_after=bs[i-1].start)
                        if lv:
                            emit('engulf_av_retest',story,tf,lv,max(at,lv.available_at),(*causes,b.id),(rb,bs[i-1],b),hp,protection_episode=episode,confirmation_bars=(bs[i-1],b))
                        # A/V may become available with following bar; never use it early.
                        if i+1<len(bs):
                            n=bs[i+1]
                            nat=max(n.available_at,b.available_at,bs[i-1].available_at,story.available_at,at)
                            lv=select_level(tf,story.side,nat,b.close_ticks,kind='V' if story.side=='BUY' else 'A',formed_after=bs[i-1].start)
                            near=_atr(bs,b.start,policy)
                            if lv and n.segment_id==b.segment_id and near is not None:
                                d=n.low_ticks-lv.price_ticks if story.side=='BUY' else lv.price_ticks-n.high_ticks
                                approach=n.low_ticks<b.low_ticks if story.side=='BUY' else n.high_ticks>b.high_ticks
                                if 0<d<=near and approach:
                                    emit('engulf_irl_retest',story,tf,lv,nat,(*causes,b.id,n.id),(rb,b,n),hp,
                                         protection_episode=episode,confirmation_bars=(bs[i-1],b,n),extra={'inducement_bar_id':n.id,'near_ticks':near,'future_sweep_required_for_fill':False})
                if not can_submit:continue
                # Aggressive overlap route does not require new inducement.
                for gap in (imbalances if 'aggressive_kl_imbalance' in enabled else ()):
                    if gap.tf!=tf or gap.side!=story.side or gap.available_at>b.available_at: continue
                    # Evaluate once at gap availability or story readiness.
                    at=max(story.available_at,gap.available_at)
                    if b.available_at!=at: continue
                    for lv in result.levels:
                        if lv.available_at>at or not gap.low_ticks<=lv.price_ticks<=gap.high_ticks: continue
                        if any(x.start>=gap.available_at and x.available_at<=at and
                               (x.low_ticks<=gap.low_ticks if story.side=='BUY' else x.high_ticks>=gap.high_ticks) for x in bs): continue
                        emit('aggressive_kl_imbalance',story,tf,lv,at,(gap.id,), (b,),phase='continuation',
                             extra={'imbalance_id':gap.id,'imbalance_policy':'fvg_wick3_v1_OUR_CHOICE'},zone_bounds=(gap.low_ticks,gap.high_ticks))
    # Optional T3-style nested chain: H4 reaction -> H1 BO -> H1 KL
    # reaction -> H1 standing-extreme -> lower engulf/KL. Every link is explicit;
    # a lone lower engulf cannot masquerade as the entire chain.
    if 'nested_confirmation' in enabled:
        h1=structures.get('H1'); h4=structures.get('H4')
        if h1 is None or h4 is None:
            support.append(dict(route='nested_confirmation',status='UNRESOLVED',reason='missing_H1_H4_lineage'))
        else:
            h1bars=bars_by_tf.get('H1',())
            h4_level_order={level.id:index for index,level in enumerate(h4.levels)}
            pair_index=_NestedPairIndex(bars_by_tf)
            witness_cache={}
            for story in stories:
                for br in h1.events:
                    if br.kind not in BREAKS or br.side!=story.side or br.evidence_status!='KNOWN': continue
                    if br.available_at<story.available_at: continue
                    # A preceding, positively witnessed H4 KL reaction and taken IRL.
                    if br.id not in witness_cache:
                        witness_cache[br.id]=_NestedWitnessIndex(sorted((row for row in reaction_context('H1',story.side)
                            if row[0].available_at<=br.clock.occurred_from and row[3]),
                            key=lambda row:(row[0].start,h4_level_order[row[1].id])))
                    witnessed=witness_cache[br.id].query(story.available_at,story.clock.occurred_from)
                    if witnessed is None: continue
                    # Suffix selection preserves both original publication
                    # cutoffs and first chronological/formation-level ties.
                    rb,htflevel,hb,hp=witnessed
                    episode=reaction_protection.get((rb.id,htflevel.id,hb.id),())
                    for a,b in pair_index.standing_after(story.side,rb.segment_id,br.available_at):
                        if episode_reason((rb,htflevel,hb,hp),b,h4.events): continue
                        lv=select_level('H1',story.side,a.start,a.close_ticks)
                        if lv is None or not (a.low_ticks<=lv.price_ticks<=a.high_ticks): continue
                        if not (a.close_ticks>lv.price_ticks if story.side=='BUY' else a.close_ticks<lv.price_ticks): continue
                        for tf in ('M30','M15','M5'):
                            if tf not in policy.entry_tfs or tf not in structures: continue
                            lower=bars_by_tf.get(tf,())
                            # A lower engulf may close with its parent standing
                            # candle; never require it to start in the next hour.
                            for x,y in pair_index.engulf_after(tf,story.side,rb.segment_id,b.end):
                                if episode_reason((rb,htflevel,hb,hp),y,h4.events): continue
                                # No arbitrary later engulf: must still react at the
                                # nested H1 KL, with no intervening close-through.
                                if not (x.low_ticks<=lv.price_ticks<=x.high_ticks or y.low_ticks<=lv.price_ticks<=y.high_ticks): continue
                                if any(z.start>=b.end and z.end<y.start and
                                       (z.close_ticks<lv.price_ticks if story.side=='BUY' else z.close_ticks>lv.price_ticks)
                                       for z in lower): continue
                                at=max(story.available_at,hb.available_at,rb.available_at,htflevel.available_at,br.available_at,lv.available_at,a.available_at,b.available_at,x.available_at,y.available_at,*[p.available_at for p in hp])
                                if at>y.available_at and _reaction_episode_reason(
                                        (rb,htflevel,hb,hp),replace(y,available_at=at),episode_events['H4']):
                                    continue
                                child=select_level(tf,story.side,at,y.close_ticks,kind='V' if story.side=='BUY' else 'A',formed_after=x.start)
                                if child is None:
                                    support.append(dict(route='nested_confirmation',story_id=story.id,tf=tf,status='UNRESOLVED',reason='lower_AV_not_yet_available',evidence_ids=(br.id,a.id,b.id,x.id,y.id)))
                                    continue
                                chain=(hb.id,rb.id,htflevel.id,br.id,lv.id,a.id,b.id,x.id,y.id,
                                       *reaction_takes.get((rb.id,htflevel.id,hb.id),()))
                                emit('nested_confirmation',story,tf,child,at,chain,(rb,a,b,x,y),hp,
                                     protection_episode=episode,confirmation_bars=(x,y),extra={'nesting_chain_ids':chain,'parent_entry_tf':'H1',
                                            'standing_reference_bar_id':a.id,'standing_confirmation_bar_id':b.id,
                                            'lineage_policy':'T3_explicit_chain_OUR_CHOICE'})
    support.append(dict(route='entry_liquidity_forms',status='SUPPORTED',objects=tuple(formed_pools),forms=('BAR','SERIES','STRUCTURAL')))
    return EntryResult(tuple(sorted(setups.values(),key=lambda s:(s.available_at,s.id))),
                       tuple(sorted(events.values(),key=lambda e:(e.available_at,e.id))),tuple(support),imbalances)

"""Offline orchestration. Source alternatives are never called a portfolio."""
from collections import Counter
from dataclasses import replace
from datetime import timedelta
from collections.abc import Mapping
from .types import StrategyPolicy, Order, jsonable, stable_id, utc
from .feed import load_feed
from .execution_feed import prepare_execution_feed
from .aggregation import aggregate, minutes, expected_slots, calendar_open_lookup
from .structure import analyze
from .impulse import assess
from .continuity import gaps_from_base, invalidate_levels, suspend_stories
from .sessions import collect_sessions
from .stories import find_stories
from .entries import detect_setups
from .simulation import simulate, Costs




def _owner_context_blocked(setup, story):
    # A newly resolved aligned context can lift a historical initial block.
    return (story.details.get('owner_selection')=='BLOCKED_COUNTERWEEKLY'
            and setup.details.get('entry_weekly_relation')!='ALIGNED')


def _opportunity_key(setup):
    return stable_id('entry_opportunity',setup.instrument,setup.tf,setup.side,
                     setup.model,setup.available_at,setup.entry_ticks)


def _ambiguous_execution_groups(candidates, stories):
    """OUR CHOICE: unresolved simultaneous risk plans cannot become a portfolio.

    Inspect the whole availability batch before placing any order. Source
    alternatives stay intact; no future outcome or ID ordering chooses a stop.
    """
    grouped={}
    for setup in candidates:
        if setup.status!='ELIGIBLE' or _owner_context_blocked(setup,stories[setup.story_id]):
            continue
        key=_opportunity_key(setup)
        grouped.setdefault(key,[]).append(setup)
    ambiguous={}
    for key,group in grouped.items():
        if len({(s.stop_ticks,s.target_ticks,s.order_type,s.expires_at) for s in group})>1:
            ambiguous[key]=('AMBIGUOUS_EXECUTION_PLAN',tuple(group))
        elif len({s.level_id for s in group})>1:
            # Equal prices do not prove equal level/story cancellation lineage.
            ambiguous[key]=('AMBIGUOUS_LEVEL_SELECTION',tuple(group))
    return ambiguous


def _confirmed_bias_result(feed, inst, clock, lower, policy, costs, story_result,
                           structures, bars_by_tf, coverage, structural_context, gaps):
    """Current confirmed-story projection; never choose a favorable side.

    Both active directions survive projection. A display representative is not
    a new canonical story or an execution authorization. Historical graph stays
    in research artifacts rather than the application database.
    """
    from bishop.bias_snapshot import TERMINAL
    known_events=tuple(e for e in story_result.events if e.available_at<=clock)
    terminal={e.reference_id for e in known_events if e.kind in TERMINAL}
    active=[s for s in story_result.stories if s.available_at<=clock and s.id not in terminal
            and s.state=='CONFIRMED' and s.details.get('owner_selection')!='BLOCKED_COUNTERWEEKLY']
    grouped={}
    for story in active:grouped.setdefault((story.origin_tf,story.side),[]).append(story)
    reactions={r.id:r for r in story_result.reactions if r.available_at<=clock}
    observations={e.id:e for structure in structures.values() for e in structure.events if e.available_at<=clock}
    bars={b.id:b for rows in bars_by_tf.values() for b in rows}
    levels={l.id:l for structure in structures.values() for l in structure.levels}
    turns={t.id:t for structure in structures.values() for t in structure.turns}
    def display_key(story):
        confirmation=observations.get(story.confirmation_id)
        return (story.available_at,story.clock.occurred_to,story.details.get('reaction_bar_id',''),
                tuple(confirmation.bar_ids) if confirmation else (),story.route)
    displayed=[max(rows,key=display_key) for _,rows in sorted(grouped.items())]
    ids={s.id for s in displayed};evidence_ids={i for s in displayed for i in (*s.evidence_ids,s.origin_id,s.confirmation_id)}
    retained={e.id:e for e in known_events if e.id in evidence_ids}
    # Pending evidence is explicitly pending, not a directional fallback.
    waiting={};waiting_clocks={}
    for event in known_events:
        if event.kind not in ('BIAS_REFERENCE_FROZEN','BIAS_WAIT_EXTERNAL_BREAK'):continue
        reaction_id=event.details.get('reaction_id',event.reference_id)
        reaction=reactions.get(reaction_id)
        if reaction is None:continue
        origin_tf=reaction.details.get('origin_tf',reaction.tf)
        key=(origin_tf,event.side,event.details.get('confirmation_tf'))
        observed=reaction.available_at
        if key not in waiting_clocks or observed>waiting_clocks[key]:
            waiting[key]={};waiting_clocks[key]=observed
        if observed==waiting_clocks[key]:waiting[key][event.id]=event
    from .stories import _invalidated
    for event in (event for group in waiting.values() for event in group.values()):
        reaction_id=event.details.get('reaction_id',event.reference_id)
        reaction=reactions.get(reaction_id)
        origin=bars.get(reaction.details.get('origin_bar_id')) if reaction else None
        if origin is not None and not _invalidated(reaction,origin,clock,bars_by_tf[origin.tf],structures):
            retained[event.id]=event

    base=tuple(feed['bars']);start=next((b.start for b in base if b.segment_id==base[-1].segment_id),None) if base else None
    end=base[-1].end if base else None
    missing=[utc(t) for t in feed['coverage'].get('missing',()) if start is None or utc(t)>=start]
    readiness={}
    for tf in policy.origin_tfs:
        rows=[s for s in active if s.origin_tf==tf];reasons=[];checked=[]
        if not base:reasons.append('EMPTY_BASE_HISTORY')
        if missing:reasons.append('MISSING_EXPECTED_BASE_SLOTS_IN_CURRENT_SEGMENT_OR_TAIL')
        if not rows:reasons.append('NO_ACTIVE_CONFIRMED_STORY')
        pending_proven=[]
        for story in rows:
            reaction=reactions.get(story.origin_id);confirmation=observations.get(story.confirmation_id)
            formation=levels.get(story.level_id) if story.level_id else None
            reference=turns.get(confirmation.reference_id) if confirmation else None
            required=set(reaction.bar_ids if reaction else ())|set(confirmation.bar_ids if confirmation else ())
            if formation is not None:required.update(formation.bar_ids)
            if reference is not None:required.update(reference.bar_ids)
            if reaction is not None and story.level_id is None and reaction.reference_id in bars:required.add(reaction.reference_id)
            if reaction is None or confirmation is None or reference is None or (story.level_id is not None and formation is None):
                reasons.append('STORY_DEPENDENCY_NOT_PROVEN')
            if any(obj is not None and obj.available_at>clock for obj in (reaction,confirmation,formation,reference)):
                reasons.append('STORY_DEPENDENCY_UNPUBLISHED')
            for ident in required:
                bar=bars.get(ident)
                if (bar is None or not bar.complete or start is None or bar.start<start
                        or bar.end>end or bar.available_at>clock):
                    reasons.append('STORY_DEPENDENCY_OUTSIDE_CURRENT_OBSERVED_SEGMENT')
            if story.id in ids:checked.append({'story_id':story.id,'reaction_id':story.origin_id,'confirmation_id':story.confirmation_id,
                            'reference_id':confirmation.reference_id if confirmation else None,'bar_ids':sorted(required)})
        if not rows and base and not missing:
            for wait in retained.values():
                if wait.kind!='BIAS_WAIT_EXTERNAL_BREAK' or wait.tf!=tf:continue
                reaction=reactions.get(wait.reference_id)
                frozen=next((e for e in retained.values() if e.kind=='BIAS_REFERENCE_FROZEN'
                             and e.details.get('reaction_id')==wait.reference_id),None)
                liquidity_origin=reaction is not None and reaction.kind=='PRIOR_CANDLE_SWEEP'
                formation=(bars.get(reaction.reference_id) if liquidity_origin else levels.get(reaction.reference_id)) if reaction else None
                reference=turns.get(frozen.reference_id) if frozen else None
                if reaction is None or frozen is None or formation is None or reference is None:continue
                source_ids={formation.id} if liquidity_origin else set(formation.bar_ids)
                required=set(reaction.bar_ids)|set(frozen.bar_ids)|source_ids|set(reference.bar_ids)
                if any(obj.available_at>clock for obj in (reaction,frozen,formation,reference)):continue
                if not required or any(ident not in bars or not bars[ident].complete or bars[ident].start<start
                                       or bars[ident].end>end or bars[ident].available_at>clock for ident in required):continue
                pending_proven.append(wait.id)
                checked.append({'pending_event_id':wait.id,'reaction_id':reaction.id,
                                'frozen_reference_id':reference.id,'bar_ids':sorted(required)})
            if pending_proven:reasons.remove('NO_ACTIVE_CONFIRMED_STORY')
        readiness[tf]={'ready':not reasons,'proof_kind':'CONFIRMED_STORIES' if rows else 'PENDING_EXTERNAL_BREAK' if pending_proven else 'UNRESOLVED',
                       'proven_pending_event_ids':pending_proven,'scope':'CURRENT_SEGMENT_ONLY','start':start,'observed_end':end,
                       'as_of':clock,'reasons':sorted(set(reasons)),
                       'checked_story_count':len(rows),'checked_evidence':checked,'historical_missing_slots':feed['coverage'].get('missing_slots',0)}
    degraded=(not base or feed['coverage']['status']!='COMPLETE'
              or any(tf not in bars_by_tf or not bars_by_tf[tf] for tf in policy.origin_tfs)
              or any(v['status']=='UNRESOLVED_RESOLUTION' for v in coverage.values()))
    reaction_ids={s.origin_id for s in displayed}
    reaction_ids.update(e.details.get('reaction_id',e.reference_id) for e in retained.values() if e.kind in ('BIAS_REFERENCE_FROZEN','BIAS_WAIT_EXTERNAL_BREAK'))
    result={'schema_version':'bishop_confirmed_bias_v1','scope':'CONFIRMED_BIAS_ONLY',
            'story_context_evaluated':True,'run_id':stable_id('confirmed_bias_run',feed['hashes'],clock,lower,policy.id),
            'status':'PARTIAL_UNVALIDATED' if degraded else 'COMPUTED_UNVALIDATED',
            'as_of':clock,'scan_start':lower,'instrument':inst,'input':feed['hashes'],'policy':policy,'costs':costs,
            'selection':{'mode':'NOT_RUN_CONFIRMED_BIAS_ONLY','rejected':[],'aliases':[]},
            'coverage':{'base':feed['coverage'],'timeframes':coverage},'structural_context':structural_context,
            'story_context_readiness':readiness,'stories':displayed,
            'story_reactions':tuple(reactions[ident] for ident in sorted(reaction_ids) if ident in reactions),
            'bias_confirmation_events':tuple(observations[s.confirmation_id] for s in displayed if s.confirmation_id in observations),
            'story_events':tuple(sorted(retained.values(),key=lambda e:(e.available_at,e.kind))),
            'active_story_groups':[{'origin_tf':tf,'side':side,'count':len(rows),
                                    'all_ids_hash':stable_id('active_story_ids',tuple(sorted(s.id for s in rows))),
                                    'displayed_story_id':max(rows,key=display_key).id}
                                   for (tf,side),rows in sorted(grouped.items())],
            'data_gap_events':gaps[-1:] if gaps else (), 'setups':[],'orders':[],'observations':[],
            'positions':[],'actions':[],'execution_events':[],'liquidity_take_events':[],
            'summary':{'stories':len(active),'displayed_stories':len(displayed),'historical_stories_evaluated':len(story_result.stories),'setups':0,'orders':0,'outcomes':{}},
            'support':[r for r in story_result.support if r.get('reaction_id') in reaction_ids],
            'teacher_acceptance':'NOT_REPLAYED',
            'limitations':['Confirmed reaction-to-break story bias only; no entry or execution.',
                           'Both active directions are retained as conflict; display representatives are not selected trades.']}
    return jsonable(result)


def run(feed_or_path, manifest=None, *, as_of, history_start=None,
        scan_start=None, policy=None, costs=None, max_open_orders=10,
        include_diagnostics=False, management_actions=(), bias_only=False, execution_feed=None, refinement_directory=None, detection_only=False, confirmed_story_bias_only=False, detection_feed=None, compact_story_diagnostics=False):
    """Compute a frozen local run; never fetch data, dispatch, or trade.

    Costs must be supplied explicitly, including an explicit zero-cost hypothesis.
    source_all simulates independent alternatives, with no portfolio claim.
    compact_story_diagnostics omits nonterminal successor observations only;
    setup selection, first flips, cancellations and paper execution are retained.
    """
    if type(compact_story_diagnostics) is not bool:
        raise ValueError('compact_story_diagnostics must be boolean')
    management_actions=tuple(dict(a) for a in management_actions)
    if type(confirmed_story_bias_only) is not bool:raise ValueError('confirmed_story_bias_only must be boolean')
    if confirmed_story_bias_only and (bias_only or detection_only or management_actions or execution_feed is not None or refinement_directory is not None):
        raise ValueError('confirmed-story bias mode cannot execute entries, orders or structural-only scans')
    if type(detection_only) is not bool:raise ValueError('detection_only must be boolean')
    if detection_only and (bias_only or management_actions or execution_feed is not None or refinement_directory is not None):
        raise ValueError('detection-only cannot run execution, management or bias-only modes')
    if type(bias_only) is not bool:
        raise ValueError('bias_only must be boolean')
    if bias_only and management_actions:
        raise ValueError('bias-only scans cannot manage orders')
    clock=utc(as_of)
    policy=StrategyPolicy(**policy) if isinstance(policy,dict) else policy or StrategyPolicy()
    if not isinstance(policy,StrategyPolicy): raise ValueError('StrategyPolicy required')
    if detection_feed is not None and (bias_only or confirmed_story_bias_only or policy.source_profile!='nested_confirmation'):
        raise ValueError('Mixed child detection is an explicit nested-confirmation-only path')
    if costs is None: raise ValueError('explicit execution costs required')
    costs=Costs(**costs) if isinstance(costs,dict) else costs
    if not isinstance(costs,Costs): raise ValueError('Costs required')
    if type(max_open_orders) is not int or max_open_orders<1: raise ValueError('positive integer max_open_orders required')
    feed=dict(feed_or_path) if isinstance(feed_or_path,Mapping) else load_feed(feed_or_path,manifest,clock,history_start)
    inst=feed['instrument']; base=tuple(feed['bars'])
    if any(b.available_at>clock for b in base): raise ValueError('feed contains future bars')
    if any(a.start>=b.start for a,b in zip(base,base[1:])): raise ValueError('feed must be ordered unique')
    # Snapshot rebuilding cannot preserve earlier gap/structure decisions when
    # an older candle first arrives after a newer one. Require receipt-order
    # replay before supporting such feeds; never silently rewrite history.
    if any(a.available_at>b.available_at for a,b in zip(base,base[1:])):
        raise ValueError('nonmonotone bar publication requires receipt-order replay; late internal bars unsupported')
    if any(b.instrument!=inst.symbol for b in base): raise ValueError('feed instrument mismatch')
    lower=utc(scan_start) if scan_start else None
    if lower and lower>clock: raise ValueError('scan_start after as_of')
    calendar=feed.get('manifest',{}).get('calendar',inst.calendar_id)
    opened=calendar_open_lookup(calendar)
    # Mapping inputs are a typed local adapter, not a validation escape hatch.
    if base:
        base_tf=base[0].tf; duration=minutes(base_tf)
        if duration is None or duration<1: raise ValueError('intraday base feed required')
        segmented=[]; segment=0; previous=None
        for bar in base:
            if bar.tf!=base_tf or bar.end-bar.start!=timedelta(minutes=duration):
                raise ValueError('mixed timeframe or incorrect base duration')
            if (bar.start.timestamp()/60)%duration or not bar.complete:
                raise ValueError('complete duration-aligned base bars required')
            if not opened(bar.start): raise ValueError('input outside declared calendar')
            if previous is not None:
                if bar.start<previous.end: raise ValueError('overlapping input')
                if next(expected_slots(previous.end,bar.start,base_tf,calendar,open_lookup=opened),None) is not None: segment+=1
            segmented.append(replace(bar,segment_id=str(segment))); previous=bar
        base=tuple(segmented)
        start=utc(history_start) if history_start else base[0].start
        if start>clock or (start.timestamp()/60)%duration: raise ValueError('invalid history_start')
        base=tuple(b for b in base if b.start>=start)
        horizon=clock-timedelta(seconds=clock.timestamp()%(duration*60))
        wanted=set(expected_slots(start,horizon,base_tf,calendar,open_lookup=opened)); present={b.start for b in base}
        missing=sorted(wanted-present)
        feed['coverage']={'status':'INCOMPLETE' if missing else 'COMPLETE','expected_slots':len(wanted),'present_slots':len(wanted&present),'missing_slots':len(missing),'missing':[t.isoformat() for t in missing]}
    else:
        feed['coverage']={'status':'EMPTY','expected_slots':0,'present_slots':0}
    feed['hashes']={**feed.get('hashes',{}),'manifest':stable_id('manifest',feed.get('manifest',{})),'prefix':stable_id('feed_prefix',inst,base)}
    execution_base=base
    execution_audit=None
    execution_kwargs={}
    if refinement_directory is not None and execution_feed is None:
        raise ValueError('refinement evidence requires a separate execution feed')
    if execution_feed is not None:
        if bias_only: raise ValueError('bias-only scans cannot refine execution')
        fine,execution_audit=prepare_execution_feed(execution_feed,feed,base,lower,clock)
        execution_base=tuple(fine['bars'])
        if refinement_directory is not None:
            from .refinement_evidence import load_refinement_evidence
            evidence=load_refinement_evidence(refinement_directory,base,fine)
            execution_kwargs['refinement_evidence']=evidence
            execution_audit['refinement']=evidence.audit
    session_result=collect_sessions(base,inst,clock,feed.get('manifest',{}).get('sessions',()),calendar=calendar,policy=policy)
    entry_frames=() if bias_only else ('H1',) if confirmed_story_bias_only else ('H2',*policy.entry_tfs)
    if detection_feed is not None:entry_frames=('H1',*entry_frames)
    frames=tuple(dict.fromkeys((*policy.origin_tfs,'W','D','H4',*entry_frames,*(p.tf for p in session_result.liquidity))))
    bars_by_tf={}; coverage={}; support=[{'component':'session_liquidity',**dict(d)} for d in session_result.diagnostics]
    for tf in frames:
        if base and (minutes(tf) is not None and (minutes(tf)<minutes(base[0].tf) or minutes(tf)%minutes(base[0].tf))):
            coverage[tf]={'status':'UNRESOLVED_RESOLUTION','base_tf':base[0].tf}
            support.append({'component':'aggregation','tf':tf,'status':'UNRESOLVED_RESOLUTION'})
            continue
        result=aggregate(base,tf,inst,clock,calendar=calendar)
        bars_by_tf[tf]=result['bars']; coverage[tf]=result['coverage']
    detection_audit=None
    if detection_feed is not None:
        from .detection_feed import prepare_detection_frames
        bars_by_tf,child_coverage,detection_audit=prepare_detection_frames(detection_feed,feed,base,bars_by_tf,lower,clock)
        coverage.update(child_coverage)
        support=[row for row in support if not (row.get('component')=='aggregation' and row.get('tf') in child_coverage)]
        feed['hashes']['detection_child']=detection_audit['hashes']
    gaps=gaps_from_base(base,policy)
    structures={tf:invalidate_levels(assess(analyze(bs,policy,supplemental_liquidity=tuple(p for p in session_result.liquidity if p.tf==tf)),bs,policy),gaps,policy) for tf,bs in bars_by_tf.items()}
    from bishop.structural_context import summarize as summarize_structure
    structural_context=summarize_structure(structures,clock)
    if bias_only or confirmed_story_bias_only:
        from bishop.structural_context import current_segment_readiness
        current_segment_readiness(structural_context,structures,bars_by_tf,base,feed['coverage'],clock)
    if bias_only:
        from .stories import StoryResult
        story_result=StoryResult(stories=(), events=(), reactions=(), support=())
    else:
        story_options={'include_successor_diagnostics':False} if detection_only or compact_story_diagnostics else {}
        story_result=suspend_stories(find_stories(bars_by_tf,structures,policy,**story_options),gaps,bars_by_tf,policy)
    if confirmed_story_bias_only:
        return _confirmed_bias_result({**feed,'bars':base},inst,clock,lower,policy,costs,story_result,
                                      structures,bars_by_tf,coverage,structural_context,gaps)
    if bias_only:
        from types import SimpleNamespace
        entry_result=SimpleNamespace(setups=(), events=(), support=(), imbalances=())
    else:
        entry_result=detect_setups(bars_by_tf,structures,story_result,inst,policy,story_events=story_result.events,eligibility_start=lower)
    candidates=sorted((s for s in entry_result.setups if (lower is None or s.available_at>=lower) and s.available_at<=clock),key=lambda s:(s.available_at,policy.entry_tfs.index(s.tf) if s.tf in policy.entry_tfs else len(policy.entry_tfs),s.id))
    if detection_only:
        from .entries import _StoryActivityIndex
        activity=_StoryActivityIndex(story_result.events)
        used={s.story_id for s in candidates}
        evidence_stories=tuple(s for s in story_result.stories if s.id in used or activity.can_emit(s,lower))
        selected_ids={s.id for s in evidence_stories}
        reaction_ids={s.origin_id for s in evidence_stories}
        evidence_ids={ident for s in evidence_stories for ident in (*s.evidence_ids,s.confirmation_id)}
        def support_counts(rows):
            counts=Counter((str(r.get('route','')),str(r.get('status','')),str(r.get('reason',''))) for r in rows)
            return [{'route':route,'status':status,'reason':reason,'count':count}
                    for (route,status,reason),count in sorted(counts.items())]
        return jsonable({
            'schema_version':'bishop_detection_v2','scope':'DETECTION_ONLY_NOT_EXECUTED',
            'run_id':stable_id('detection_run','ENTRY_STATE_PROJECTION_V2',feed.get('hashes'),clock,lower,policy.id),
            'status':'COMPUTED_DETECTION_UNVALIDATED','as_of':clock,'instrument':inst,'input':feed.get('hashes',{}),'policy':policy,
            'graph_projection':'ENTRY_STATE_ONLY; successor diagnostic observations omitted; terminal boundaries preserved',
            'stories':evidence_stories,'story_reactions':tuple(r for r in story_result.reactions if r.id in reaction_ids),
            'story_events':tuple(e for e in story_result.events if e.reference_id in selected_ids or e.id in evidence_ids),
            'entry_support_summary':support_counts(entry_result.support),
            'story_support_summary':support_counts(story_result.support),
            'coverage':{'base':feed.get('coverage',{}),'timeframes':coverage},
            'detection_input':detection_audit,
            'summary':{'stories':len(story_result.stories),'setups':len(candidates),'orders':0,'outcomes':{}},
            'setups':candidates,'orders':[],'observations':[],
            'selection':{'mode':'NOT_RUN_DETECTION_ONLY','rejected':[],'aliases':[]},
            'teacher_acceptance':'NOT_REPLAYED',
            'limitations':['Detection only: no selection, fills, outcomes or performance computed.',
                           'Teacher-example identity and alternate-feed alignment remain unverified.']})
    stories={s.id:s for s in story_result.stories}
    cancellation_events={}
    for event in story_result.events:
        if (event.kind in ('STORY_INVALIDATED','STORY_DESTINATION_REACHED','STORY_CANCELLED','STORY_FLIPPED')
                or event.details.get('pending_action')=='CANCEL_DEPENDENT'):
            cancellation_events.setdefault(event.reference_id,[]).append(event)
    orders=[]; rejected=[]; actions=[dict(a) for a in management_actions]; execution_cache={}
    economic_signals={}
    aliases=[]
    alternatives=policy.source_profile in ('source_all','all_routes')
    ambiguous={} if alternatives else _ambiguous_execution_groups(candidates,stories)
    for setup in candidates:
        if setup.status!='ELIGIBLE': continue
        story=stories[setup.story_id]
        if _owner_context_blocked(setup,story):
            rejected.append({'setup_id':setup.id,'reason':'BLOCKED_COUNTERWEEKLY'}); continue
        opportunity_key=_opportunity_key(setup)
        if opportunity_key in ambiguous:
            reason,_=ambiguous[opportunity_key]
            rejected.append({'setup_id':setup.id,'reason':reason,
                             'opportunity_id':opportunity_key})
            continue
        # Same pattern/level/clock/risk from another context is one signal.
        # Later confirmations remain distinct; source_all retains alternatives.
        economic_key=stable_id('economic_signal',setup.instrument,setup.tf,setup.side,setup.model,setup.level_id,setup.available_at,setup.entry_ticks,setup.stop_ticks,setup.target_ticks,setup.order_type,setup.expires_at)
        if not alternatives and economic_key in economic_signals:
            canonical=economic_signals[economic_key]
            aliases.append({'setup_id':setup.id,'story_id':setup.story_id,'canonical_setup_id':canonical.setup_id,'order_id':canonical.id,'economic_signal_id':economic_key})
            continue
        # Prospective cap uses only execution information available at submission.
        # Censored exposure remains reserved: unknown execution is not a free slot.
        active=0
        if not alternatives:
            for previous in orders:
                key=(previous.id,setup.available_at)
                if key not in execution_cache:
                    execution_cache[key]=simulate((previous,),tuple(b for b in execution_base if b.available_at<=setup.available_at),inst,costs,setup.available_at,actions,calendar=calendar,**execution_kwargs)
                obs=execution_cache[key]['observations']
                if not obs or obs[0].get('outcome') not in ('WIN','LOSS','BREAK_EVEN','CANCELLED','REPLACED','EXPIRED'):
                    active+=1
            if active>=max_open_orders:
                rejected.append({'setup_id':setup.id,'reason':'EXPOSURE_CAP'}); continue
        order=Order(id=stable_id('order',setup.id,policy.id),setup_id=setup.id,instrument=setup.instrument,tf=setup.tf,model=setup.model,side=setup.side,kind=setup.order_type,clock=setup.clock,entry_ticks=setup.entry_ticks,stop_ticks=setup.stop_ticks,target_ticks=setup.target_ticks,expires_at=setup.expires_at,details={'story_id':setup.story_id,'policy_id':policy.id,'economic_signal_id':economic_key,'context_policy':'first_causal_context_canonical'})
        orders.append(order)
        economic_signals[economic_key]=order
        for event in cancellation_events.get(setup.story_id,()):
            if event.available_at>=setup.available_at:
                actions.append({'order_id':order.id,'kind':'CANCEL','available_at':event.available_at,'reason':event.kind})
    known_orders={o.id for o in orders}
    if any(a.get('order_id') not in known_orders for a in management_actions):
        raise ValueError('management action references unknown or unselected order')
    execution=simulate(orders,execution_base,inst,costs,clock,actions,calendar=calendar,**execution_kwargs)
    support.extend(story_result.support); support.extend(entry_result.support)
    unavailable=[tf for tf in (*policy.origin_tfs,*(() if bias_only else policy.entry_tfs)) if not bars_by_tf.get(tf)]
    support.extend({'component':'required_history','tf':tf,'status':'INSUFFICIENT_COMPLETE_BARS'} for tf in dict.fromkeys(unavailable))
    degraded=not base or feed['coverage']['status']!='COMPLETE' or bool(unavailable) or any(v['status']=='UNRESOLVED_RESOLUTION' for v in coverage.values())
    result={'schema_version':'bishop_offline_v2_1','scope':'BIAS_ONLY' if bias_only else 'PAPER_ENTRIES','story_context_evaluated':not bias_only,'run_id':stable_id('run','selection_entry_weekly_context_v4_terminal_target_proof',feed.get('hashes'),clock,lower,policy.id,costs,max_open_orders,management_actions,*(('BIAS_STRUCTURE_ONLY_V2',) if bias_only else ())),
            'status':'PARTIAL_UNVALIDATED' if degraded else 'COMPUTED_UNVALIDATED','as_of':clock,'scan_start':lower,'instrument':inst,'input':feed.get('hashes',{}),'policy':policy,'costs':costs,
            'selection':{'mode':'INDEPENDENT_ALTERNATIVES' if alternatives else 'PROSPECTIVE_CAPPED','max_open_orders':None if alternatives else max_open_orders,'rejected':rejected,'aliases':aliases,'conflicts':[{'opportunity_id':key,'reason':reason,'setup_ids':tuple(s.id for s in group)} for key,(reason,group) in ambiguous.items()],'dedup_policy':'same_model_level_clock_risk_v2_wait_conflicts','ambiguity_policy':'WAIT_CONFLICTING_SIMULTANEOUS_PLANS_OR_LEVELS_OUR_CHOICE'},
            'coverage':{'base':feed.get('coverage',{}),'timeframes':coverage},'support':support,
            'structural_context':structural_context,
            'stories':story_result.stories,'story_events':story_result.events,'data_gap_events':gaps,
            'liquidity_take_events':tuple(e for e in entry_result.events if e.kind=='LIQUIDITY_FIRST_TAKEN'),
            'setups':candidates,'orders':orders,'actions':actions,
            'execution_events':execution['events'],'observations':execution['observations'],'positions':execution['positions'],
            'summary':{'stories':len(story_result.stories),'setups':len(candidates),'orders':len(orders),'outcomes':dict(Counter(o.get('outcome','UNKNOWN') for o in execution['observations']))},
            'teacher_acceptance':'NOT_REPLAYED','limitations':['OHLC execution censors ambiguous intrabar sequences.','Numerical policies are implementation choices; teacher replay acceptance is pending.']}
    if include_diagnostics: result['diagnostics']={'structures':structures,'entry_events':entry_result.events,'imbalances':entry_result.imbalances,'reactions':story_result.reactions}
    if detection_audit is not None:
        result['detection_input']=detection_audit
        if detection_audit['coverage']['status']!='COMPLETE':
            result['status']='PARTIAL_UNVALIDATED'
    if execution_audit is not None:
        result['execution_input']=execution_audit
        if execution_audit['coverage']['status']!='COMPLETE':
            result['status']='PARTIAL_UNVALIDATED'
        result['run_id']=stable_id('run_execution',result['run_id'],execution_audit)
    return jsonable(result)

"""Immutable sponsoring objectives, independent of the terminal entry timeframe.

A context snapshot never substitutes an entry-TF target or a later winner.
Missing links remain unresolved. ERL touch consumes liquidity; an ordinary KL
contact alone does not retire a still-valid opposing role.
"""
from dataclasses import dataclass, field
from .types import _freeze, stable_id, utc

BREAKS = frozenset(('BREAKOUT', 'BOS', 'SWEEP_BOS', 'EXTERNAL_BREAK'))


@dataclass(frozen=True)
class TargetContext:
    instrument: str
    tf: str
    side: str
    sponsor_id: str
    scope_id: str | None
    available_at: object
    objective_kind: str | None = None
    objective_ref_id: str | None = None
    objective_price_ticks: int | None = None
    objective_available_at: object | None = None
    objective_formed_at: object | None = None
    objective_bar_ids: tuple = ()
    objective_role: str | None = None
    status: str = 'UNRESOLVED'
    reasons: tuple = ()
    provenance: object = field(default_factory=dict)
    id: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, 'available_at', utc(self.available_at))
        for name in ('objective_available_at', 'objective_formed_at'):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, utc(getattr(self, name)))
        object.__setattr__(self, 'objective_bar_ids', tuple(self.objective_bar_ids))
        object.__setattr__(self, 'reasons', tuple(self.reasons))
        object.__setattr__(self, 'provenance', _freeze(self.provenance))
        values = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != 'id'}
        object.__setattr__(self, 'id', stable_id('target_context', values))


def _snapshot(sponsor, at, side, *, reference=None, kind=None, role=None,
              selected_range=None, reasons=()):
    return TargetContext(
        instrument=sponsor.instrument, tf=sponsor.tf, side=side,
        sponsor_id=sponsor.id, scope_id=sponsor.scope_id, available_at=at,
        objective_kind=kind, objective_ref_id=reference.id if reference else None,
        objective_price_ticks=reference.price_ticks if reference else None,
        objective_available_at=reference.available_at if reference else None,
        objective_formed_at=reference.formed_at if reference else None,
        objective_bar_ids=reference.bar_ids if reference else (),
        objective_role=role, status='UNRESOLVED' if reasons else 'KNOWN',
        reasons=tuple(dict.fromkeys(reasons)),
        provenance={'policy': 'explicit_sponsoring_objective_v1',
                    'sponsor_available_at': sponsor.available_at,
                    'range_version_id': selected_range.version_id if selected_range else None,
                    'range_available_at': selected_range.available_at if selected_range else None})


def _sponsor_reasons(sponsor, at, side):
    reasons=[]
    if sponsor.kind not in BREAKS or sponsor.evidence_status != 'KNOWN':
        reasons.append('context_sponsor_not_confirmed')
    if sponsor.available_at > at:
        reasons.append('context_sponsor_unpublished')
    if sponsor.side != side:
        reasons.append('context_sponsor_direction_mismatch')
    if sponsor.scope_id is None:
        reasons.append('context_scope_unresolved')
    return reasons


def _range_reasons(sponsor, selected, at, side, *, erl):
    reasons=[]
    if selected is None:
        return ['context_range_unresolved']
    if selected.id != sponsor.scope_id:
        reasons.append('context_range_not_sponsor_scope')
    if selected.available_at > at:
        reasons.append('context_range_unpublished')
    if selected.status == 'BROKEN':
        reasons.append('context_range_origin_broken')
    if selected.direction != side:
        reasons.append('context_range_direction_mismatch')
    if erl and selected.details.get('endpoint_broken'):
        reasons.append('context_endpoint_delivered')
    if erl and selected.details.get('endpoint_stage') != 'CONFIRMED_DELIVERY':
        reasons.append('context_endpoint_unconfirmed')
    return reasons


def _reference_reasons(sponsor, reference, at):
    if reference is None:
        return ['context_objective_unresolved']
    reasons=[]
    if reference.instrument != sponsor.instrument or reference.tf != sponsor.tf:
        reasons.append('context_objective_instrument_or_timeframe_mismatch')
    if reference.available_at > at:
        reasons.append('context_objective_unpublished')
    return reasons


def _segment_bars(context, bars, at):
    # Do not skip an unpublished internal row to pretend the older history is
    # still contiguous. Scheduled market closures preserve segment identity.
    same=tuple(b for b in bars if b.instrument == context.instrument and b.tf == context.tf)
    visible=[i for i,b in enumerate(same) if b.complete and b.available_at <= at]
    if not visible:
        return (), ('context_price_history_unresolved',)
    last=visible[-1];segment=same[last].segment_id;known=[]
    for i in range(last, -1, -1):
        bar=same[i]
        if not bar.complete or bar.available_at > at or bar.segment_id != segment:
            break
        known.append(bar)
    known.reverse()
    if context.objective_formed_at is not None and context.objective_formed_at < known[0].start:
        return tuple(known), ('context_objective_before_contiguous_history',)
    return tuple(known), ()


def validate_context(context, at, entry, side, bars, events=()):
    """Return unchanged objective price or reasons; never select a replacement."""
    if context is None:
        return None, ('context_objective_unresolved',)
    at=utc(at);reasons=list(context.reasons)
    if context.status != 'KNOWN':
        reasons.append('context_objective_not_known')
    if context.available_at > at:
        reasons.append('context_snapshot_unpublished')
    if context.side != side:
        reasons.append('context_direction_mismatch')
    if context.objective_price_ticks is None or context.objective_ref_id is None:
        reasons.append('context_objective_unresolved')
    elif (1 if side == 'BUY' else -1)*(context.objective_price_ticks-entry) <= 0:
        reasons.append('context_objective_not_ahead')
    if context.objective_available_at is None or context.objective_available_at > at:
        reasons.append('context_objective_unpublished')
    known,history_reasons=_segment_bars(context, bars, at)
    reasons.extend(history_reasons)
    # Closed child candles can retire an objective before its parent closes.
    # They may extend coverage, but never bridge an unobserved interval.
    children=sorted((b for b in bars if b.instrument==context.instrument
                     and b.tf!=context.tf and b.complete and b.available_at<=at),
                    key=lambda b:(b.start,b.end))
    covered=known[-1].end if known else None
    for bar in children:
        if covered is not None and bar.start<=covered and bar.end>covered:
            covered=bar.end
    if covered is None or covered<at:
        reasons.append('context_entry_interval_unobserved')
    if context.objective_kind == 'ERL' and context.objective_price_ticks is not None:
        for bar in (*known,*children):
            if bar.id in context.objective_bar_ids or bar.end <= context.objective_formed_at:
                continue
            hit=(bar.high_ticks >= context.objective_price_ticks if side == 'BUY'
                 else bar.low_ticks <= context.objective_price_ticks)
            if hit:
                reasons.append('context_objective_consumed_or_ordering_unknown')
                break
    for event in events:
        if (event.instrument != context.instrument or event.tf != context.tf
                or event.available_at > at):
            continue
        if (event.kind == 'RANGE_BROKEN' and event.scope_id == context.scope_id
                and context.provenance.get('range_available_at') is not None
                and event.available_at >= context.provenance['range_available_at']):
            reasons.append('context_range_origin_broken')
        if event.reference_id != context.objective_ref_id:
            continue
        if event.kind == 'LEVEL_UNAVAILABLE':
            reasons.append('context_objective_unavailable')
        if (context.objective_kind == 'KL' and event.kind == 'LEVEL_ROLE_CHANGE'
                and event.available_at > context.available_at
                and event.side != context.objective_role):
            reasons.append('context_objective_role_lost')
    reasons=tuple(dict.fromkeys(reasons))
    return (None, reasons) if reasons else (context.objective_price_ticks, ())


def context_from_reference(sponsor, selected_range, reference, at, side, role):
    """Snapshot an explicitly linked opposing KL, never a nearest junction."""
    at=utc(at);reasons=_sponsor_reasons(sponsor, at, side)
    reasons.extend(_range_reasons(sponsor, selected_range, at, side, erl=False))
    reasons.extend(_reference_reasons(sponsor, reference, at))
    links={selected_range.details.get(k) for k in ('target_level_id','opposing_level_id')
           if selected_range and selected_range.details.get(k) is not None}
    if len(links) > 1:
        reasons.append('context_objective_links_ambiguous')
    if reference is None or reference.id not in links:
        reasons.append('context_kl_not_explicitly_linked')
    expected='SELL' if side == 'BUY' else 'BUY'
    normalized={'RESISTANCE':'SELL','SUPPORT':'BUY'}.get(role,role)
    if normalized != expected:
        reasons.append('context_objective_role_not_opposing')
    return _snapshot(sponsor, at, side, reference=reference, kind='KL', role=normalized,
                     selected_range=selected_range, reasons=reasons)


def resolve_context(sponsor, structure, bars, at, side, role_lookup=None):
    """Resolve an explicit scope objective once, at reaction publication."""
    at=utc(at);reasons=_sponsor_reasons(sponsor, at, side)
    versions={}
    for selected in structure.ranges:
        old=versions.get(selected.id)
        if selected.available_at <= at and (old is None or selected.available_at >= old.available_at):
            versions[selected.id]=selected
    selected=versions.get(sponsor.scope_id)
    links={selected.details.get(k) for k in ('target_level_id','opposing_level_id')
           if selected and selected.details.get(k) is not None}
    if links:
        if len(links) != 1:
            return _snapshot(sponsor, at, side, selected_range=selected,
                             reasons=(*reasons,'context_objective_links_ambiguous'))
        refs=[level for level in structure.levels if level.id in links and level.available_at <= at]
        if len(refs) != 1:
            return _snapshot(sponsor, at, side, selected_range=selected,
                             reasons=(*reasons,'context_linked_kl_unresolved_or_ambiguous'))
        reference=refs[0]
        if role_lookup is None:
            from .structure import role_at
            role=role_at(reference,structure.events,at)
        else:
            role=role_lookup(reference,at)
        context=context_from_reference(sponsor,selected,reference,at,side,role)
    else:
        reasons.extend(_range_reasons(sponsor,selected,at,side,erl=True))
        refs=[pool for pool in structure.liquidity if selected is not None
              and pool.id == selected.endpoint_liquidity_id and pool.available_at <= at]
        reference=refs[0] if len(refs) == 1 else None
        reasons.extend(_reference_reasons(sponsor,reference,at))
        if reference is not None and reference.kind != ('HIGH' if side == 'BUY' else 'LOW'):
            reasons.append('context_endpoint_kind_mismatch')
        context=_snapshot(sponsor,at,side,reference=reference,kind='ERL',
                          selected_range=selected,reasons=reasons)
    # Entry distance is not available yet. Use a one-tick point on the correct
    # side solely to validate history/lifecycle, without choosing any entry.
    proxy=(context.objective_price_ticks or 0)-(1 if side=='BUY' else -1)
    _,carry_reasons=validate_context(context,at,proxy,side,bars,events=structure.events)
    if carry_reasons:
        from dataclasses import replace
        context=replace(context,status='UNRESOLVED',reasons=carry_reasons)
    return context


def resolve_h4_key_level(sponsor, structure, bars, at, entry, side, role_lookup=None):
    """v16 1098.8–1155.3: nearest opposing H4 KL from known entry.

    This explicit route does not replace the distinct context-ERL procedure.
    Missing range scope is recorded, never inferred from price containment.
    """
    at=utc(at)
    reasons=[r for r in _sponsor_reasons(sponsor,at,side) if r!='context_scope_unresolved']
    if sponsor.tf!='H4':reasons.append('context_sponsor_not_h4')
    if role_lookup is None:
        from .structure import RoleIndex
        role_lookup=RoleIndex(structure.events).role_at
    expected='SELL' if side=='BUY' else 'BUY'
    sign=1 if side=='BUY' else -1
    candidates=[]
    for level in structure.levels:
        if (level.instrument!=sponsor.instrument or level.tf!='H4'
                or level.kind not in ('A','V','OC') or level.available_at>at
                or sign*(level.price_ticks-entry)<=0):continue
        raw_role=role_lookup(level,at)
        role={'RESISTANCE':'SELL','SUPPORT':'BUY'}.get(raw_role,raw_role)
        if role==expected:candidates.append(level)
    reference=min(candidates,key=lambda l:(sign*(l.price_ticks-entry),l.id)) if candidates else None
    if reference is None:reasons.append('context_opposing_h4_kl_unresolved')
    context=_snapshot(sponsor,at,side,reference=reference,kind='KL',role=expected,reasons=reasons)
    from dataclasses import replace
    context=replace(context,provenance={**context.provenance,
        'policy':'nearest_opposing_h4_kl_from_entry_v1',
        'source':'video-16-storyline-1:1098.8-1155.3',
        'entry_ticks':entry,'candidate_ids':tuple(l.id for l in sorted(candidates,key=lambda l:l.id)),
        'scope_policy':'EXPLICIT_H4_SPONSOR_NO_INFERRED_RANGE'})
    _,carry_reasons=validate_context(context,at,entry,side,bars,events=structure.events)
    return replace(context,status='UNRESOLVED',reasons=carry_reasons) if carry_reasons else context

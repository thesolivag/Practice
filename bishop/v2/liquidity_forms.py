"""Explicit later near-KL inducement; numerical relation is OUR CHOICE.

RS 267.6–345.5 permits later candle/series/structure; E5 240.5–284.2
permits later formation rather than an immediate next-candle-only rule.
Video11 1593–1634 and1819–1834 explicitly show A/V approach inducement,
including a third H4 candle. The composite geometry remains OUR CHOICE.
This bounded subtype requires directional approach without KL contact.
"""
from .types import Liquidity, stable_id
from .structure import role_at

BREAKS=frozenset(('BREAKOUT','BOS','SWEEP_BOS','EXTERNAL_BREAK'))


def later_kl_irl(bars, levels, events, policy, role_lookup=None):
    """Return closed, parent/KL-linked BAR pools, never a future-sweep test.

    One closest usable KL beyond the wick is selected per side/bar before
    future outcomes. Other levels cannot borrow this pool's inducement identity.
    A delayed approach publishes its pool only when that bar is available.
    """
    bs=tuple(sorted((b for b in bars if b.complete),key=lambda b:b.start))
    events=tuple(events); levels=tuple(levels)
    lookup=role_lookup or (lambda level,at:role_at(level,events,at))
    segment_start={}
    epoch_start=None
    prior=None
    for b in bs:
        if (prior is None or prior.segment_id!=b.segment_id or prior.tf!=b.tf
                or prior.instrument!=b.instrument or prior.end!=b.start):epoch_start=b.start
        segment_start[b.id]=epoch_start
        prior=b
    out=[]
    for previous,bar in zip(bs,bs[1:]):
        if (previous.instrument!=bar.instrument or previous.tf!=bar.tf
                or previous.segment_id!=bar.segment_id or previous.end!=bar.start
                or previous.available_at>bar.start):continue
        for side in ('BUY','SELL'):
            approaching=(bar.high_ticks>previous.high_ticks if side=='SELL'
                         else bar.low_ticks<previous.low_ticks)
            if not approaching:continue
            parents=[e for e in events if e.kind in BREAKS and e.side==side
                     and e.instrument==bar.instrument and e.tf==bar.tf
                     and e.evidence_status=='KNOWN' and e.available_at<=bar.start
                     and e.clock.occurred_from>=segment_start[bar.id]]
            if not parents:continue
            parent=max(parents,key=lambda e:e.available_at)
            opposite='SELL' if side=='BUY' else 'BUY'
            candidates=[]
            for level in levels:
                if (level.instrument!=bar.instrument or level.tf!=bar.tf
                        or level.available_at>bar.start
                        or lookup(level,bar.start) not in (side,'SUPPORT' if side=='BUY' else 'RESISTANCE')):continue
                distance=level.price_ticks-bar.high_ticks if side=='SELL' else bar.low_ticks-level.price_ticks
                if distance<=0:continue # Touch/equality is reaction, not new inducement.
                invalid=False
                for event in events:
                    if not parent.available_at<event.available_at<=bar.available_at:continue
                    if (event.reference_id==level.id and
                            (event.kind=='LEVEL_UNAVAILABLE' or
                             (event.kind=='LEVEL_ROLE_CHANGE' and event.side==opposite))):invalid=True
                    if (parent.scope_id is not None and event.scope_id==parent.scope_id
                            and event.kind in ('RANGE_BROKEN',*BREAKS)):invalid=True
                if not invalid:candidates.append((distance,level.id,level))
            if not candidates:continue
            level=min(candidates,key=lambda row:row[:2])[2]
            out.append(Liquidity(id=stable_id('later_kl_irl',parent.id,level.id,bar.id,policy.id),
                instrument=bar.instrument,tf=bar.tf,kind='HIGH' if side=='SELL' else 'LOW',
                price_ticks=bar.high_ticks if side=='SELL' else bar.low_ticks,
                formed_at=bar.end,available_at=max(parent.available_at,level.available_at,bar.available_at),
                form='BAR',bar_ids=(bar.id,),policy_id=policy.id,
                details={'role':'IRL','reaction_level_id':level.id,'parent_break_id':parent.id,
                         'breakout_id':parent.id,'previous_bar_id':previous.id,
                         'convention':'OUR_CHOICE_later_adjacent_approach_without_KL_contact_v1',
                         'source':'RS267.6-345.5;E5 240.5-284.2;video11 1593-1634,1819-1834;research composite'}))
    return tuple(out)

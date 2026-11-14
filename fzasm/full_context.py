"""Full-context research specification v1; mechanical choices are not teacher validation.

Every level and map carries its knowledge time. No extrapolated destinations.
See reports/FZ_ASM_FULL_RESEARCH_SPEC.md for source/assumption boundaries.
"""
from dataclasses import replace
from .types import BiasDirection as B, MapType as M, LevelType as L, KeyLevel, DailyMapResult


def active_levels(candles, tolerance=0.):
    """Closed-bar OB+FVG and adjacent A/V body junctions; terminal close invalidation."""
    levels=[]
    for i in range(1,len(candles)):
        a,b=candles[i-1:i+1]
        if a.available_at != b.timestamp:
            continue
        direction=B.BULLISH if a.is_bearish and b.is_bullish else B.BEARISH if a.is_bullish and b.is_bearish else None
        if direction and abs(a.close-b.open)<=tolerance:
            levels.append(KeyLevel(L.OPEN_CLOSE,direction,a.close,a.close,b.available_at,b.timeframe,
                source_candle=a,metadata={'rule':'adjacent_body_junction','confirmed_by':b.timestamp.isoformat()}))
        if i<2:continue
        a,b,c=candles[i-2:i+1]
        if a.available_at!=b.timestamp or b.available_at!=c.timestamp:continue
        long=a.is_bearish and b.is_bullish and c.low>a.high and b.close>a.body_high
        short=a.is_bullish and b.is_bearish and c.high<a.low and b.close<a.body_low
        if long or short:
            levels.append(KeyLevel(L.ORDER_BLOCK,B.BULLISH if long else B.BEARISH,
                a.body_high if long else a.high,a.low if long else a.body_low,
                c.available_at,c.timeframe,source_candle=a,
                metadata={'rule':'opposing_origin_body_departure_with_fvg','has_fvg':True}))
    # A broken OB can flip once. Junctions do not automatically flip.
    result=[]
    for level in levels:
        broken=next((c for c in candles if c.timestamp>=level.timestamp and
            (c.close<level.price_bottom if level.direction==B.BULLISH else c.close>level.price_top)),None)
        if broken is None:
            result.append(level)
        elif level.level_type==L.ORDER_BLOCK:
            flipped=replace(level,level_type=L.BREAKER_BLOCK,
                direction=B.BEARISH if level.direction==B.BULLISH else B.BULLISH,
                timestamp=broken.available_at,
                metadata=dict(level.metadata,rule='closed_far_edge_breaker',original_available_at=level.timestamp.isoformat()))
            if not any(c.timestamp>=flipped.timestamp and
                (c.close<flipped.price_bottom if flipped.direction==B.BULLISH else c.close>flipped.price_top)
                for c in candles):result.append(flipped)
    return result


def _map(kind,direction,origin,target,known,refs,rule):
    return DailyMapResult(kind,direction,origin,target,(origin+target)/2,0.,rule,known,refs)


def _alive(candidate, after):
    long=candidate.bias==B.BULLISH
    return not any((c.low<candidate.origin_level or c.high>=candidate.target_level) if long else
                   (c.high>candidate.origin_level or c.low<=candidate.target_level) for c in after)


def map_candidates(daily, tolerance=0.):
    """All active map candidates, rather than an unsupported fixed map priority.

    Structural swings use one closed neighbour each side, on body edges.
    A body break sponsors a range; its destination is the observed extension
    high/low, available at close. Further extension updates it until retracement.
    """
    candidates=[]
    for i in range(1,len(daily)):
        prev,cur=daily[i-1:i+1]
        # Broker D1 can bridge weekends; input loader audits missing weekdays.
        low=cur.low<prev.low and prev.low<cur.close<=prev.high and cur.high<prev.high
        high=cur.high>prev.high and prev.low<=cur.close<prev.high and cur.low>prev.low
        if low or high:
            direction=B.BULLISH if low else B.BEARISH
            candidate=_map(M.MAP_2_CANDLE_RANGE_CRT,direction,cur.low if low else cur.high,
                prev.high if low else prev.low,cur.available_at,[prev,cur],'single_sided_daily_range_sweep')
            candidates.append(candidate)
            # Confluence must exist before the sweep daily candle opened.
            prior_levels=active_levels(daily[:i],tolerance)
            if any(p.direction==direction and p.timestamp<=cur.timestamp and p.is_tested_by(cur) for p in prior_levels):
                candidates.append(replace(candidate,map_type=M.MAP_4_CRT_POI_CONFLUENCE,
                                          notes='daily_range_sweep_at_preexisting_daily_level'))
        for long in (True,False):
            run=[]
            for candle in reversed(daily[:i]):
                if candle.is_bearish if long else candle.is_bullish:run.append(candle)
                else:break
            if len(run)<2:continue
            lo=min(c.low for c in run);hi=max(c.high for c in run)
            swept=(cur.low<lo<cur.close and cur.high<hi) if long else (cur.high>hi>cur.close and cur.low>lo)
            if swept:
                candidates.append(_map(M.MAP_3_CONSECUTIVE_LEG_SWEEP,B.BULLISH if long else B.BEARISH,
                    cur.low if long else cur.high,hi if long else lo,cur.available_at,list(reversed(run))+[cur],
                    'uninterrupted_opposing_daily_leg_sweep'))
        # Pivots must be confirmed before the breaking candle opens.
        for long in (True,False):
            pivots=[j for j in range(1,i-1) if
                ((daily[j].body_high>daily[j-1].body_high and daily[j].body_high>=daily[j+1].body_high) if long else
                 (daily[j].body_low<daily[j-1].body_low and daily[j].body_low<=daily[j+1].body_low))]
            if not pivots:continue
            j=pivots[-1];boundary=daily[j].body_high if long else daily[j].body_low
            crossed=(prev.close<=boundary<cur.close) if long else (prev.close>=boundary>cur.close)
            if not crossed:continue
            # Retain the most recent uninterrupted extension from the break.
            end=i
            while end+1<len(daily) and ((daily[end+1].close>daily[end].close and daily[end+1].high>daily[end].high) if long else
                                       (daily[end+1].close<daily[end].close and daily[end+1].low<daily[end].low)):
                end+=1
            segment=daily[j:end+1]
            origin=min(c.low for c in segment) if long else max(c.high for c in segment)
            target=max(c.high for c in segment) if long else min(c.low for c in segment)
            candidates.append(_map(M.MAP_1_STRUCTURAL_RANGE,B.BULLISH if long else B.BEARISH,
                origin,target,daily[end].available_at,segment,'body_pivot_break_observed_extension_range'))
    active=[m for m in candidates if _alive(m,[c for c in daily if c.timestamp>=m.timestamp])]
    # Map5 is a rejection within a previously sponsored active range, not a
    # target manufactured from the width of a POI.
    if len(daily)>=2:
        cur=daily[-1]
        for sponsor in active[:]:
            if sponsor.timestamp>cur.timestamp:continue
            for p in active_levels(daily[:-1],tolerance):
                if p.timestamp>cur.timestamp or p.direction!=sponsor.bias or not p.is_tested_by(cur):continue
                long=sponsor.bias==B.BULLISH
                rejected=cur.close>p.price_top if long else cur.close<p.price_bottom
                if not rejected:continue
                pierced=cur.low<p.price_bottom if long else cur.high>p.price_top
                active.append(replace(sponsor,map_type=M.MAP_5B_SWEEP_INVALIDATION if pierced else M.MAP_5A_REJECTION,
                    timestamp=cur.available_at,reference_candles=sponsor.reference_candles+[cur],
                    notes='rejection_in_previously_sponsored_range; sponsor='+sponsor.map_type.value))
    return active


def choose_map(candidates, price):
    """Conservative research policy: conflicting active directions mean abstain."""
    if not candidates:return None,'NO_ACTIVE_DAILY_MAP'
    if len({c.bias for c in candidates})!=1:return None,'CONFLICTING_DAILY_MAPS'
    long=candidates[0].bias==B.BULLISH
    favorable=[c for c in candidates if (c.target_level>price if long else c.target_level<price)]
    if not favorable:return None,'NO_UNREACHED_DESTINATION'
    # Closest known destination prevents silently ignoring an intervening target.
    return min(favorable,key=lambda c:(abs(c.target_level-price),-c.timestamp.timestamp(),c.map_type.value)),''

"""Causal lower-timeframe swing break and local A/V/FVG recognition.

One-bar-left/right pivots are explicit research parameters. Events may occur
inside the sweeping hour; orders cannot exist until that hour has closed.
"""
from .types import BiasDirection


def recognize_retests(candles, sweep, now):
    bars=[c for c in candles if c.available_at<=now and c.timestamp>=sweep.swept_candle.timestamp]
    if not sweep.swept or sweep.sweep_candle.available_at>now or len(bars)<5:
        return []
    if len({c.timeframe for c in bars})!=1 or bars[-1].timeframe not in ('M5','M10','M15'):
        return []
    if any(a.available_at!=b.timestamp for a,b in zip(bars,bars[1:])):
        return []
    long=sweep.direction==BiasDirection.BULLISH
    during=[i for i,c in enumerate(bars) if sweep.sweep_candle.timestamp<=c.timestamp<sweep.sweep_candle.available_at]
    if not during:return []
    extreme=min(during,key=lambda i:bars[i].low) if long else max(during,key=lambda i:bars[i].high)
    # Protected swing preceding the sweep extreme, confirmed by its right neighbour.
    pivots=[i for i in range(1,extreme) if
            (bars[i].high>bars[i-1].high and bars[i].high>=bars[i+1].high if long else
             bars[i].low<bars[i-1].low and bars[i].low<=bars[i+1].low)]
    if not pivots:return []
    pivot=pivots[-1];boundary=bars[pivot].high if long else bars[pivot].low
    broken=next((i for i in range(extreme+1,len(bars)) if
                 (bars[i].close>boundary if long else bars[i].close<boundary)),None)
    if broken is None:return []
    known=max(sweep.sweep_candle.available_at,bars[broken].available_at)
    if now<known:return []
    after=[c for c in bars if c.timestamp>=sweep.sweep_candle.available_at]
    if any(c.low<sweep.sweep_price if long else c.high>sweep.sweep_price for c in after):return []
    common={'structure_rule':'protected_pivot_before_sweep_extreme','pivot_span':1,
            'structure_boundary':boundary,'pivot_time':bars[pivot].timestamp.isoformat(),
            'sweep_extreme_time':bars[extreme].timestamp.isoformat(),
            'break_time':bars[broken].available_at.isoformat(),'context_available_at':known.isoformat()}
    candidates=[]
    # Freeze the opposing launch candle at the break; never choose a later candle
    # because its subsequent retest or profit looks better.
    opposing=[i for i in range(extreme,broken) if (bars[i].is_bearish if long else bars[i].is_bullish)]
    if opposing:
        origin=opposing[-1];c=bars[origin]
        entry=c.body_high if long else c.body_low
        candidates.append(dict(common,route='order_block',entry=entry,zone_low=c.low if long else c.body_low,
                               zone_high=c.body_high if long else c.high,formed_at=known.isoformat(),
                               origin_time=c.timestamp.isoformat(),local_extreme=min(b.low for b in bars[origin:broken+1]) if long else max(b.high for b in bars[origin:broken+1])))
    for k in range(max(broken,2),len(bars)):
        a,c=bars[k-2],bars[k]
        if not (c.low>a.high if long else c.high<a.low):continue
        low,high=(a.high,c.low) if long else (c.high,a.low)
        # Exact local candle junction, not an unrelated H4 POI boundary.
        junctions=[]
        for j in range(1,k):
            left,right=bars[j-1],bars[j]
            reversal=(left.is_bearish and right.is_bullish) if long else (left.is_bullish and right.is_bearish)
            if reversal and low<=left.close<=high:
                junctions.append((j,left.close))
        if not junctions:continue
        j,entry=junctions[-1]
        candidates.append(dict(common,route='fvg_av_overlap',entry=entry,zone_low=low,zone_high=high,
                               formed_at=max(known,c.available_at).isoformat(),gap_available_at=c.available_at.isoformat(),
                               origin_time=bars[j-1].timestamp.isoformat(),
                               local_extreme=min(b.low for b in bars[j-1:k+1]) if long else max(b.high for b in bars[j-1:k+1])))
    result=[]
    for item in candidates:
        # A past fill cannot become a new order. A plan is emitted only at its
        # formation clock; later replay must manage the original pending order.
        if item['formed_at']!=now.isoformat():continue
        if item['route']=='fvg_av_overlap' and any(
            c.timestamp.isoformat()>=item['gap_available_at'] and c.available_at<=now and
            (c.low<=item['entry'] if long else c.high>=item['entry']) for c in bars):
            continue
        if not (item['entry']<bars[-1].close if long else item['entry']>bars[-1].close):continue
        result.append(item)
    return result

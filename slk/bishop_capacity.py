"""Causal occupancy upper bound; never infer profit from unknown execution."""
from bisect import bisect_left
from bishop.v2.types import utc


def occupies(row,bars,now):
    now=utc(now);obs=row['observation'];outcome=obs['outcome']
    if outcome!='CENSORED':return outcome in ('OPEN','PENDING')
    if row.get('capacity_released_at'):
        return utc(row['capacity_released_at'])>now
    order=row['order']
    # This proof supports static limit orders only. It never assumes a fill,
    # assigns a result, or silently treats a gap as a closed market.
    if order.kind!='LIMIT':return True
    if any(a.get('kind') not in ('CANCEL','REPLACE') for a in row['actions']):return True
    deadlines=([order.expires_at] if order.expires_at else [])+[
        utc(a['available_at']) for a in row['actions'] if a.get('kind') in ('CANCEL','REPLACE')
        and order.available_at<=utc(a['available_at'])<=now]
    if not deadlines:return True
    deadline=min(deadlines)
    # After pending expiry/cancellation no new fill is possible. A later
    # complete bar touching an exit proves any potentially filled branch flat.
    i=bisect_left(bars,deadline,key=lambda b:b.start)
    for b in bars[i:]:
        if not b.complete or b.available_at>now:continue
        stop=b.low_ticks<=order.stop_ticks if order.side=='BUY' else b.high_ticks>=order.stop_ticks
        target=b.high_ticks>=order.target_ticks if order.side=='BUY' else b.low_ticks<=order.target_ticks
        if stop or target:
            row['capacity_released_at']=b.available_at.isoformat()
            row['capacity_proof']={'policy':'expired_or_cancelled_then_exit_touch_v1',
                'pending_deadline':deadline.isoformat(),'bar_id':b.id,'observed_at':now.isoformat()}
            return False
    return True

from dataclasses import replace
from test_fzasm_reference import reference
from fzasm.block_audit import block_candidates


def test_retains_main_and_user_secondary_without_hardcoded_selection():
    h,m,s=reference(); clock=h[2].available_at
    rows=block_candidates(m,s,clock)
    times={r['origin_time'][11:16] for r in rows}
    assert {'02:10','02:30','02:40'} <= times
    assert rows[0]['role']=='sweep_origin_candidate'
    assert all(r['classification']=='unvalidated_order_block_candidate' for r in rows)
    changed=[replace(c,high=999,low=1,close=900) if c.available_at>clock else c for c in m]
    assert block_candidates(changed,s,clock)==rows
    assert block_candidates(m,s,clock.replace(minute=55,hour=2))==[]

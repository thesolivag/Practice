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


def test_real_gbpusd_keeps_origin_before_directional_sweep_extreme():
    import pandas as pd
    from pathlib import Path
    from fzasm.data import df_to_candles
    from fzasm.types import TimeFrame
    from fzasm.sessions import HourlySweepDetector
    df=pd.read_csv(Path(__file__).parent/'data/gbpusd_block_20261110_m5.csv',index_col='time',parse_dates=True)
    m=df_to_candles(df,TimeFrame.M5)
    h=df_to_candles(df.resample('1h').agg({'open':'first','high':'max','low':'min','close':'last'}),TimeFrame.H1)
    s=HourlySweepDetector.detect_h1_sweep(h)
    rows=block_candidates(m,s,h[-1].available_at)
    main=next(r for r in rows if r['role']=='sweep_origin_candidate')
    assert main['origin_time']=='2026-11-10T11:00:00+00:00'
    assert len(rows)==4

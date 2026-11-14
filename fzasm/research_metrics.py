"""Resolved-trade metrics; costs are sensitivity assumptions, not execution simulation."""
import pandas as pd

def metrics(rows,cost_pips=0.,pip_size=.0001,cost_r=0.):
    closed=rows[rows.status=='CLOSED'].copy()
    closed=closed.sort_values(['exit_time','signal_id'],kind='stable')
    risk=(closed.entry_price-closed.stop_price).abs()
    r=closed.result_r.astype(float)-cost_pips*pip_size/risk-cost_r
    equity=0.;peak=0.;drawdown=0.;streak=0;longest=0
    for value in r:
        equity+=value;peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
        streak=streak+1 if value<0 else 0;longest=max(longest,streak)
    return dict(setups=len(rows),resolved=len(closed),wins=int((r>0).sum()),losses=int((r<0).sum()),
        win_rate=float((r>0).mean()) if len(r) else None,result_r=float(r.sum()),
        resolved_exit_drawdown_r=drawdown,max_resolved_losing_streak=longest,
        unknown=int((rows.status=='UNKNOWN').sum()),unfilled=int((rows.status=='UNFILLED').sum()),
        unavailable=int((rows.status=='UNAVAILABLE').sum()))

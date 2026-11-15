"""Outcome-blind context annotation and predeclared historical comparisons."""
from functools import lru_cache
from collections import Counter
import json
import pandas as pd
from .full_context import map_candidates,active_levels,_alive
from .sessions import HourlySweepDetector
from .types import BiasDirection as B

@lru_cache(maxsize=400)
def cached_maps(daily,pip_size):
    return map_candidates(list(daily),pip_size)

FEATURES=('aligned_map','opposing_map','map_conflict','h4_touch','h2_touch','htf_touch','aligned_range_half')

def context_features(signal,series,pip_size):
    # Only identity, decision clock, side and saved sweep evidence enter this function.
    now=pd.Timestamp(signal['timestamp']);long=float(signal['entry_price'])>float(signal['stop_price'])
    side=B.BULLISH if long else B.BEARISH
    closed={tf:[c for c in bars if c.available_at<=now] for tf,bars in series.items()}
    daily=closed['D1'];maps=cached_maps(tuple(daily),pip_size)
    maps=[m for m in maps if _alive(m,[c for c in closed['H1'] if c.timestamp>=m.timestamp])]
    aligned=[m for m in maps if m.bias==side];opposing=[m for m in maps if m.bias!=side]
    evidence=json.loads(signal['entry_evidence']);extreme=evidence.get('sweep_extreme')
    sweeps=[];h=closed['H1']
    for i in range(1,len(h)):
        if h[i].timestamp.date()!=now.date() or h[i].timestamp.hour>=6:continue
        s=HourlySweepDetector.detect_h1_sweep(h[max(0,i-2):i+1])
        if s and s.direction==side and extreme is not None and abs(s.sweep_price-float(extreme))<pip_size/100:
            sweeps.append(s)
    out=dict(aligned_map=bool(aligned),opposing_map=bool(opposing),map_conflict=bool(aligned and opposing),
        sweep_match_count=len(sweeps),context_at=now.isoformat(),context_valid=len(daily)>=3,
        map_evidence=json.dumps([dict(type=m.map_type.value,side=m.bias.value,origin=m.origin_level,target=m.target_level,known_at=m.timestamp.isoformat()) for m in maps]))
    out.update({k:None for k in ('h4_touch','h2_touch','htf_touch','aligned_range_half')})
    details=[]
    if len(sweeps)==1:
        sweep=sweeps[0].sweep_candle;hits=[]
        for tf in ('H4','H2'):
            prior=[c for c in closed[tf] if c.available_at<=sweep.timestamp][-240:]
            levels=active_levels(prior,pip_size)
            touched=[p for p in levels if p.direction==side and p.is_tested_by(sweep)]
            out[tf.lower()+'_touch']=bool(touched);hits.extend(touched)
            details.extend(dict(tf=tf,type=p.level_type.value,low=p.price_bottom,high=p.price_top,known_at=p.timestamp.isoformat()) for p in touched)
        out['htf_touch']=bool(hits)
        out['aligned_range_half']=any((m.origin_level<=p.mid_price<=m.equilibrium_50 if long else m.equilibrium_50<=p.mid_price<=m.origin_level) for m in aligned for p in hits)
        out['sweep_at']=sweep.timestamp.isoformat()
    out['level_evidence']=json.dumps(details)
    return out


def partition(timestamp):
    t=pd.Timestamp(timestamp)
    if t<pd.Timestamp('2026-06-26T00:00Z'):return 'discovery'
    if t>=pd.Timestamp('2026-07-06T00:00Z'):return 'validation'
    return 'embargo'


def summarize(rows):
    resolved=rows[(rows.status=='CLOSED') & rows.result_r.notna()]
    if len(rows) and rows.phase.iloc[0]=='discovery':
        resolved=resolved[pd.to_datetime(resolved.exit_time,utc=True,errors='coerce')<pd.Timestamp('2026-07-01T00:00Z')]
    net=resolved.result_r.astype(float)-.08
    ordered=resolved.assign(net=net).sort_values(['exit_time','signal_id'])
    equity=ordered.groupby('exit_time').net.sum().cumsum()
    dd=(equity.cummax().clip(lower=0)-equity).max() if len(equity) else None
    return dict(signals=len(rows),resolved=len(resolved),unknown=int((rows.status=='UNKNOWN').sum()),
        unfilled=int((rows.status=='UNFILLED').sum()),unavailable=int((rows.status=='UNAVAILABLE').sum()),
        boundary_excluded=int((rows.status=='CLOSED').sum())-len(resolved),
        wins=int((net>0).sum()),win_rate=float((net>0).mean()) if len(net) else None,
        gross_r=float(resolved.result_r.sum()) if len(net) else None,net_r=float(net.sum()) if len(net) else None,
        mean_net_r=float(net.mean()) if len(net) else None,drawdown_r=float(dd) if dd is not None else None,
        resolved_months=resolved.timestamp.str[:7].nunique())


def comparisons(table):
    records=[]
    for (pair,policy,target,phase),g in table.groupby(['symbol','entry_policy','target','phase']):
        if phase=='embargo':continue
        for feature in FEATURES:
            valid=g[g.context_valid.eq(True) & g[feature].notna()]
            for flag in (False,True):
                sub=valid[valid[feature].eq(flag)]
                records.append(dict(symbol=pair,entry_policy=policy,target=target,phase=phase,feature=feature,present=flag,**summarize(sub)))
    return pd.DataFrame(records)


def candidates(stats):
    # Discovery only: single-factor hypotheses, no pairwise combinatorial search.
    out=[]
    d=stats[stats.phase=='discovery']
    for keys,g in d.groupby(['symbol','entry_policy','target','feature']):
        yes=g[g.present.eq(True)];no=g[g.present.eq(False)]
        if len(yes)!=1 or len(no)!=1:continue
        a,b=yes.iloc[0],no.iloc[0]
        if a.resolved>=30 and b.resolved>=30 and a.resolved_months>=3 and a.mean_net_r>0 and a.mean_net_r>b.mean_net_r:
            out.append(dict(zip(['symbol','entry_policy','target','feature'],keys),discovery_mean_net_r=float(a.mean_net_r),discovery_lift=float(a.mean_net_r-b.mean_net_r)))
    return out

"""Bounded full-context replay; single structural exit and separate fixed-R studies."""
from bisect import bisect_right
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import pandas as pd
import numpy as np
from .data import df_to_candles,resample_ohlc
from .types import TimeFrame, BiasDirection
from .execution import TradeOutcome
from .full_model import FullASMEngine


class FullOutcome(TradeOutcome):
    # No unsupported half-off / break-even rule for the structural destination.
    attrs=('r1_result_r','r2_result_r','r3_result_r','r4_result_r','structural_result_r')

    def target_r(self,attr):
        if attr=='structural_result_r':return self.r(self.setup.take_profit_2)
        return super().target_r(attr)


def replay_full(symbol,df,daily,start,end,out,policy='auto',cost_r=.08):
    start,end=pd.Timestamp(start),pd.Timestamp(end)
    if start.tzinfo is None or end.tzinfo is None or start.utcoffset().total_seconds()!=0 or end.utcoffset().total_seconds()!=0 or not pd.Timedelta(0)<end-start<=pd.Timedelta(days=31):
        raise ValueError('Specify timezone-aware start/end, at most31 days')
    if cost_r<0:raise ValueError('Costs must be nonnegative')
    if df.empty or df.index.tz is None or df.index.has_duplicates or not df.index.is_monotonic_increasing:
        raise ValueError('Need nonempty ordered unique timezone-aware M1 data')
    if any(t.utcoffset().total_seconds()!=0 or t.second or t.microsecond for t in df.index):
        raise ValueError('M1 opens must be UTC minute boundaries')
    values=df.loc[:,['open','high','low','close']].astype(float)
    if not np.isfinite(values.to_numpy()).all() or ((values.low>values.min(axis=1)) | (values.high<values.max(axis=1))).any():
        raise ValueError('Invalid M1 OHLC')
    df=values[df.index+pd.Timedelta(minutes=1)<=end]
    if not (df.index>=start).any():raise ValueError('No M1 data inside the requested window')
    if df.empty or df.index[0]>=start:raise ValueError('Pre-period M1 warmup is required')
    if not any(c.available_at<=start for c in daily):raise ValueError('Pre-period native daily history required')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    series={tf:df_to_candles(resample_ohlc(df,rule),TimeFrame(tf)) for tf,rule in
        {'M5':'5min','M10':'10min','M15':'15min','H1':'1h','H2':'2h','H4':'4h'}.items()}
    series['D1']=daily
    clocks={tf:[c.available_at for c in bars] for tf,bars in series.items()}
    minutes=df_to_candles(df,TimeFrame.M1)
    engine=FullASMEngine(extra_pairs={symbol},entry_policy=policy)
    trades=[];active=[];session=[];decisions=[]
    for i,c in enumerate(minutes):
        now=c.available_at
        if not session or session[0].timestamp.date()!=c.timestamp.date():session=[]
        if c.timestamp.hour<6:session.append(c)
        if now<=start:continue
        for t in list(active):
            t.evaluate_bar(c,i)
            if t.closed:active.remove(t)
        if now.minute%5:continue
        slices={}
        for tf,bars in series.items():
            n=bisect_right(clocks[tf],now)
            slices[tf]=bars[:n] if tf=='D1' else bars[max(0,n-240):n]
        slices['M1']=minutes[max(0,i-360):i+1]
        plan=engine.scan_asset(symbol,slices,now)
        if now.hour<6:
            decisions.append(dict(engine.last_review,signal=plan is not None))
        if plan is None:continue
        complete=bool(session) and session[0].timestamp==now.replace(hour=0,minute=0,second=0,microsecond=0) and session[-1].available_at==now and all(a.available_at==b.timestamp for a,b in zip(session,session[1:]))
        asian=(max(b.high for b in session) if plan.bias==BiasDirection.BULLISH else min(b.low for b in session)) if complete else None
        t=FullOutcome(plan,i,asian_target=asian,include_asian=True)
        trades.append(t);active.append(t)
    for t in active:t.end_of_data(end)
    rows=[];plans=[]
    for i,t in enumerate(trades):
        plan=t.setup;sid=f'{symbol}:{policy}:{plan.timestamp.isoformat()}:{i}'
        plans.append(dict(signal_id=sid,**asdict(plan)))
        for attr in t.attrs:
            value=getattr(t,attr)
            rows.append(dict(signal_id=sid,symbol=symbol,policy=policy,route=plan.entry_model.value,
                month=plan.timestamp.strftime('%Y-%m'),decision_at=plan.timestamp.isoformat(),
                entry=plan.entry_price,stop=plan.stop_loss,target=attr,
                target_price=(t.asian_target if attr=='asian_result_r' else plan.entry_price+t.sign*t.unit_risk*t.target_r(attr)),
                status=t.status[attr],reason=t.reasons.get(attr,''),gross_r=value,
                net_r=value-cost_r if value is not None else None,
                exit_at=t.exit_times[attr].isoformat() if attr in t.exit_times else None))
    columns=['signal_id','symbol','policy','route','month','decision_at','entry','stop','target','target_price','status','reason','gross_r','net_r','exit_at']
    table=pd.DataFrame(rows,columns=columns);table.to_csv(out/'trades.csv',index=False)
    monthly=[]
    for (month,route,target),g in table.groupby(['month','route','target']):
        resolved=g[g.status=='CLOSED'];n=len(resolved)
        monthly.append(dict(month=month,symbol=symbol,policy=policy,route=route,target=target,
            signals=len(g),resolved=n,unknown=int((g.status=='UNKNOWN').sum()),
            unfilled=int((g.status=='UNFILLED').sum()),unavailable=int((g.status=='UNAVAILABLE').sum()),
            wins=int((resolved.gross_r>0).sum()),win_rate=float((resolved.gross_r>0).mean()) if n else None,
            gross_r=float(resolved.gross_r.sum()) if n else None,net_r=float(resolved.net_r.sum()) if n else None))
    pd.DataFrame(monthly).to_csv(out/'monthly.csv',index=False)
    (out/'plans.json').write_text(json.dumps(plans,default=str,indent=2))
    (out/'decisions.json').write_text(json.dumps(decisions,default=str,indent=2))
    manifest=dict(version=engine.VERSION,symbol=symbol,policy=policy,start=str(start),end=str(end),
        m1_first=str(df.index[0]),m1_last=str(df.index[-1]),m1_rows=len(df),
        m1_missing_intervals=int((df.index.to_series().diff()>pd.Timedelta(minutes=1)).sum()),
        m1_sha256=hashlib.sha256(pd.util.hash_pandas_object(df,index=True).values.tobytes()).hexdigest(),
        daily_sha256=hashlib.sha256(json.dumps([asdict(c) for c in daily],default=str,sort_keys=True).encode()).hexdigest(),
        signals=len(trades),diagnostics=dict(engine.diagnostics),teacher_validated=False,
        costs=f'{cost_r}R per resolved filled trade; assumption, not measured bid/ask execution',
        session='00:00–06:00UTC; all intraday candles UTC research aggregation; native D1 availability',
        stop='sweep extreme plus3 instrument pips',structural_exit='single full exit; no partials or break-even',
        uncertainty='Unknowns excluded from realized sums, never counted as zero-return resolved trades',
        history='All supplied daily history; at most240 closed bars per intraday timeframe',
        position_policy='Independent setup outcomes; overlapping positions allowed, not a funded portfolio simulation',
        no_signal_months='No trade rows means no signals, not a missing profitable configuration',
        limitations='Research rules include assumptions; no proof of teacher equivalence or profitability')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return trades,manifest

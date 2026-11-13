"""Continuous M1 replay of independent entry/stop/target scenarios.

Monthly reports checkpoint the same replay; positions are never reset at a
month boundary. No outcome participates in signal, stop or target selection.
"""
from pathlib import Path
from dataclasses import replace
from bisect import bisect_right
import argparse
import hashlib
import json
import pandas as pd
from .data import load_minute_df, resample_ohlc, df_to_candles
from .types import TimeFrame, BiasDirection
from .engine import FZASMEngine
from .execution import TradeOutcome
from . import instruments
from .study_report import write_study_report

PAIRS=('USDJPY','EURJPY','GBPJPY','AUDJPY','NZDJPY','CADJPY','CHFJPY','XAUUSD','EURUSD','GBPUSD')
POLICIES=('h1_av','h1_av_m5','swing_ob','swing_fvg')
TARGETS={'r1_result_r':'1R','r2_result_r':'2R','r3_result_r':'3R','r4_result_r':'4R',
         'asian_result_r':'ASIAN_EXTREME','fz_result_r':'FZ_RESEARCH'}


def variants(setup):
    """Same signal, exact sweep or three broker-defined pips outside it."""
    long=setup.bias==BiasDirection.BULLISH
    for name,buffer in [('sweep_exact',0.),('sweep_plus_3p',3*instruments.pip(setup.symbol))]:
        stop=setup.h1_sweep.sweep_price+(-buffer if long else buffer)
        valid=stop<setup.entry_price if long else stop>setup.entry_price
        candidate=replace(setup,stop_variant=name,stop_loss=stop if valid else setup.stop_loss,
                          risk_reward=abs(setup.take_profit_2-setup.entry_price)/abs(setup.entry_price-stop) if valid else 0.,
                          entry_evidence=dict(setup.entry_evidence,study_stop=stop,study_stop_buffer_price=buffer))
        yield candidate,valid


def records_of(trades):
    records=[]
    for policy,t in trades:
        s=t.setup
        for attr,target in TARGETS.items():
            records.append(dict(signal_id=f'{s.symbol}:{policy}:{s.timestamp.isoformat()}:{s.entry_model.value}',
                symbol=s.symbol,entry_policy=policy,stop_variant=s.stop_variant,target=target,
                timestamp=s.timestamp.isoformat(),status=t.status[attr],result_r=getattr(t,attr),
                exit_time=t.exit_times[attr].isoformat() if attr in t.exit_times else '',
                reason=t.reasons.get(attr,''),entry_price=s.entry_price,
                stop_price=s.entry_evidence['study_stop'],asian_target=t.asian_target,
                target_price=((None if s.daily_map.entry_only else s.take_profit_2) if attr=='fz_result_r' else t.asian_target if attr=='asian_result_r'
                              else s.entry_price+t.sign*t.unit_risk*int(attr[1])),
                fill_bar_open=t.filled_at.isoformat() if t.filled_at else '',
                entry_evidence=json.dumps(s.entry_evidence,sort_keys=True)))
    return records


def replay(pair,df,out_dir,policies=POLICIES,engine_factory=FZASMEngine,requested_start=None,requested_end=None,native_daily=None):
    if df.empty:raise ValueError('No M1 data; refusing an empty success')
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    requested_start=pd.Timestamp(requested_start) if requested_start is not None else pd.Timestamp(year=df.index[0].year,month=1,day=1,tz='UTC')
    requested_end=pd.Timestamp(requested_end) if requested_end is not None else df.index[-1]+pd.Timedelta(minutes=1)
    series={tf:df_to_candles(resample_ohlc(df,rule),TimeFrame(tf)) for tf,rule in
            {'M5':'5min','M10':'10min','M15':'15min','H1':'1h','H2':'2h','H4':'4h','D1':'1D'}.items()}
    if native_daily is not None:
        series['D1']=list(native_daily)
        if not series['D1']:raise ValueError('No completed native D1 candles; refusing a zero-bias replay')
    available={tf:[c.available_at for c in bars] for tf,bars in series.items()}
    engines={p:engine_factory(extra_pairs={pair},entry_policy=p,confirmation_tf='M5') for p in policies}
    minutes=df_to_candles(df,TimeFrame.M1)
    trades=[];active=[];months=set();session=[];current_month=None
    def checkpoint(at,final=False):
        coverage=[]
        report_end=requested_end if final else pd.Timestamp(at)
        requested_months=pd.date_range(requested_start,report_end,freq='MS',inclusive='left')
        for begin in requested_months:
            month=begin.strftime('%Y-%m')
            # Calendar completeness and replay completeness are distinct from provider gaps.
            begin=pd.Timestamp(month+'-01',tz='UTC');end=begin+pd.offsets.MonthBegin(1)
            scope=df[(df.index>=begin)&(df.index<end)&(df.index<pd.Timestamp(at))]
            for p in policies:
                coverage.append(dict(symbol=pair,entry_policy=p,month=month,
                    status='missing' if scope.empty else 'complete' if pd.Timestamp(at)>=end and df.index[0]<=begin else 'partial',
                    replay_through=at.isoformat(),m1_rows=len(scope),
                    missing_intervals=int((scope.index.to_series().diff()>pd.Timedelta(minutes=1)).sum()),
                    final_snapshot=final))
        records=records_of(trades)
        write_study_report(records,out,coverage)
        (out/'progress.json').write_text(json.dumps(dict(replay_through=at.isoformat(),final=final,
            signals=len(trades)//2,open_scenarios=sum(t.status[a] in ('PENDING','OPEN') for _,t in trades for a in t.attrs)),indent=2))
        print(f'CHECKPOINT {pair} {at.isoformat()} signals={len(trades)//2} final={final}',flush=True)
    for i,candle in enumerate(minutes):
        if candle.available_at<requested_start:continue
        month=candle.timestamp.strftime('%Y-%m')
        if current_month is not None and month!=current_month:checkpoint(candle.timestamp)
        current_month=month;months.add(month)
        for t in list(active):
            t.evaluate_bar(candle,i)
            if t.closed:active.remove(t)
        now=candle.available_at
        # Session extreme is frozen using completed M1 data at the signal clock.
        session_start=now.replace(hour=0,minute=0,second=0,microsecond=0)
        if not session or session[0].timestamp.date()!=candle.timestamp.date():session=[]
        if candle.timestamp.hour<6:session.append(candle)
        if candle.available_at.hour>=6 and candle.available_at.minute>0:session=[]
        end=bisect_right(available['M5'],now)
        if not end or available['M5'][end-1]!=now:continue
        slices={}
        for tf,bars in series.items():
            n=bisect_right(available[tf],now);slices[tf]=bars[max(0,n-240):n]
        for policy,engine in engines.items():
            setup=engine.scan_asset(pair,slices,current_time=now)
            if setup is None:continue
            complete=bool(session) and session[0].timestamp==session_start and session[-1].available_at==now and all(a.available_at==b.timestamp for a,b in zip(session,session[1:]))
            asian=(max(c.high for c in session) if setup.bias==BiasDirection.BULLISH else min(c.low for c in session)) if complete else None
            setup=replace(setup,entry_evidence=dict(setup.entry_evidence,asian_target_frozen_at=now.isoformat(),
                asian_session_start=session_start.isoformat(),asian_history_complete=complete,entry_policy=policy))
            for candidate,valid in variants(setup):
                outcome=TradeOutcome(candidate,i,asian_target=asian,include_asian=True)
                if candidate.daily_map.entry_only:
                    outcome.finish('fz_result_r','UNAVAILABLE',now,reason='NO_DAILY_MAP_IN_ENTRY_ONLY_STUDY')
                if not valid:
                    for attr in outcome.attrs:outcome.finish(attr,'UNAVAILABLE',now,reason='NONPOSITIVE_STOP_RISK')
                trades.append((policy,outcome))
                if not outcome.closed:active.append(outcome)
    for t in active:t.end_of_data(minutes[-1].available_at)
    checkpoint(minutes[-1].available_at,True)
    (out/'manifest.json').write_text(json.dumps(dict(symbol=pair,first=df.index[0].isoformat(),last=df.index[-1].isoformat(),
        rows=len(df),sha256=hashlib.sha256(pd.util.hash_pandas_object(df,index=True).values.tobytes()).hexdigest(),
        entry_policies=list(policies),targets=TARGETS,stops=['sweep_exact','sweep_plus_3p'],
        requested_start=requested_start.isoformat(),requested_end=requested_end.isoformat(),
        warmup='No prior-year input: January starts cold; early daily-map/POI eligibility may be suppressed',
        checkpoint_type='Cumulative report snapshots, not resumable execution state',
        context_mode='asian_only' if any(getattr(t.setup.daily_map,'entry_only',False) for _,t in trades) else engines[policies[0]].__class__.__name__,
        daily_source='broker-native completed D1' if native_daily is not None else 'strict M1 aggregation',
        aggregate_counts={tf:len(bars) for tf,bars in series.items()},
        engine_diagnostics={p:dict(getattr(e,'diagnostics',{})) for p,e in engines.items()},
        calendar='Native daily boundaries; UTC intraday research calendar' if native_daily is not None else 'UTC research calendar',session='00:00–06:00 UTC; inherited prime sweep hours 00,01,02',
        costs='gross; excludes spread, commission, financing and slippage',
        fz_exit='Existing research exit: half at map equilibrium, move remainder to breakeven, half at map target; not teacher-validated',
        m5_routes='swing_ob and swing_fvg remain provisional; report separately'),indent=2))
    return trades


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pair',choices=PAIRS,required=True)
    ap.add_argument('--year',type=int,default=2026);ap.add_argument('--as-of',required=True)
    ap.add_argument('--native-daily',required=True,help='Broker-native daily CSV; no M1-derived daily fallback');ap.add_argument('--out',default='reports/expanded-study');ap.add_argument('--download-m1',action='store_true')
    args=ap.parse_args();cutoff=pd.Timestamp(args.as_of)
    if cutoff.tzinfo is None:raise ValueError('as-of must include UTC timezone')
    if args.download_m1:
        from .minute_cache import prepare
        prepare(args.pair,args.year,as_of=cutoff)
    df=load_minute_df(args.pair,args.year,args.year)
    df=df[df.index+pd.Timedelta(minutes=1)<=cutoff]
    from .native_daily import candles_from_native_daily
    native=pd.read_csv(args.native_daily,index_col='time',parse_dates=True)
    daily,daily_audit=candles_from_native_daily(native,cutoff)
    if daily_audit['missing_weekday_gaps']:raise ValueError('Native daily history has unverified gaps; refusing to bridge them')
    replay(args.pair,df,Path(args.out)/args.pair,native_daily=daily,requested_start=pd.Timestamp(year=args.year,month=1,day=1,tz='UTC'),requested_end=cutoff)

if __name__=='__main__':main()

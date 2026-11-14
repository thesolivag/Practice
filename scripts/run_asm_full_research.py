"""Run a bounded full-ASM research sample from existing data; never downloads prices."""
import argparse,json,math
from pathlib import Path
import pandas as pd
from fzasm.data import load_minute_df
from fzasm.native_daily import candles_from_native_daily
from fzasm.full_replay import replay_full
from fzasm import instruments


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pair',required=True)
    ap.add_argument('--start',required=True);ap.add_argument('--end',required=True)
    ap.add_argument('--m1',help='Local UTC M1 CSV; otherwise use restored cache and prior-pair warmup')
    ap.add_argument('--native-daily',default='reports/prior-pair/native_D1.csv')
    ap.add_argument('--policy',choices=['auto','h1_av','h1_av_m5','swing_ob','swing_fvg'],default='auto')
    ap.add_argument('--cost-r',type=float,default=.08)
    ap.add_argument('--out',default='reports/full-asm-research')
    a=ap.parse_args();start,end=pd.Timestamp(a.start),pd.Timestamp(a.end)
    if start.tzinfo is None or end.tzinfo is None or not pd.Timedelta(0)<end-start<=pd.Timedelta(days=31):
        ap.error('Use aware UTC start/end and a window of at most31 days')
    prior=Path('reports/prior-pair')
    meta=prior/'COMPLETE.json'
    if meta.exists():
        info=json.loads(meta.read_text())
        instruments.register(a.pair,int(round(-math.log10(info['pip']))))
    if a.m1:
        df=pd.read_csv(a.m1,index_col=0,parse_dates=True)
    else:
        df=load_minute_df(a.pair,start.year,end.year)
        warmup=prior/'warmup_M1.csv'
        if warmup.exists():
            w=pd.read_csv(warmup,index_col=0,parse_dates=True)
            df=pd.concat([w[w.index<df.index.min()],df]).sort_index()
    df=df[(df.index>=start-pd.Timedelta(days=14))&(df.index+pd.Timedelta(minutes=1)<=end)]
    raw=pd.read_csv(a.native_daily,index_col=0,parse_dates=True)
    # One following row supplies native availability; never admit its future OHLC.
    raw=raw[(raw.index>=start-pd.Timedelta(days=120))&(raw.index<=end+pd.Timedelta(days=4))]
    daily,audit=candles_from_native_daily(raw,end)
    if audit['missing_weekday_gaps']:
        raise ValueError('Native daily history has unverified gaps; no silent bridging')
    out=Path(a.out)
    trades,manifest=replay_full(a.pair,df,daily,start,end,out,a.policy,a.cost_r)
    (out/'daily_audit.json').write_text(json.dumps(audit,indent=2))
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()

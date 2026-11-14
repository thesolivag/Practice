"""Deterministic audit samples from existing outcomes; no backtest rerun."""
import argparse,json
from pathlib import Path
import pandas as pd
from fzasm.data import load_minute_df,resample_ohlc
ap=argparse.ArgumentParser();ap.add_argument('--pair',required=True);pair=ap.parse_args().pair
root=Path('saved-outcomes');out=Path('reports/trade-audit')/pair;out.mkdir(parents=True,exist_ok=True)
r=pd.read_csv(root/'asian_only/outcomes.csv');r=r[(r.stop_variant=='sweep_exact')&(r.target=='4R')].sort_values('timestamp')
df=load_minute_df(pair,2026,2026);rows=[]
# Calendar anchors chosen before looking at individual chart appearance.
for label,policy,status,sign,anchor in [('h1_win','h1_av','CLOSED',1,'2026-01-01'),('h1_loss','h1_av','CLOSED',-1,'2026-05-01'),('h1_unfilled','h1_av','UNFILLED',0,'2026-09-01'),('m5_loss','swing_fvg','CLOSED',-1,'2026-05-01')]:
 c=r[(r.entry_policy==policy)&(r.status==status)]
 if sign:c=c[c.result_r*sign>0]
 after=c[pd.to_datetime(c.timestamp,utc=True)>=pd.Timestamp(anchor,tz='UTC')]
 if len(after):c=after
 if c.empty:continue
 trade=c.iloc[0].to_dict();at=pd.Timestamp(trade['timestamp']);exit_at=pd.Timestamp(trade['exit_time'])
 begin=at-pd.Timedelta(hours=24);end=min(exit_at+pd.Timedelta(hours=2),at+pd.Timedelta(days=6))
 bars=df[(df.index>=begin)&(df.index<end)]
 prefix=out/label
 bars.to_csv(str(prefix)+'_M1.csv');resample_ohlc(bars,'1h').to_csv(str(prefix)+'_H1.csv');resample_ohlc(bars,'5min').to_csv(str(prefix)+'_M5.csv')
 trade['selection']=dict(rule='First eligible at/after fixed calendar anchor; fallback earliest',anchor=anchor,label=label)
 trade['entry_evidence']=json.loads(trade['entry_evidence'])
 (out/(label+'.json')).write_text(json.dumps(trade,indent=2,default=str));rows.append(trade)
(out/'index.json').write_text(json.dumps(rows,indent=2,default=str))

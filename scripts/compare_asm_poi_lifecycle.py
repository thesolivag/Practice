"""Matched filter ablation using archived price data; no network market requests."""
from pathlib import Path
from functools import partial
import json
import pandas as pd
from fzasm.data import load_minute_df,resample_ohlc,df_to_candles
from fzasm.native_daily import candles_from_native_daily
from fzasm.study import replay,records_of
from fzasm.engine import FZASMEngine
from fzasm.asian_only import AsianOnlyEngine
from fzasm.types import TimeFrame

source=Path('reports/frozen-input')
out=Path('reports/poi-lifecycle-comparison');out.mkdir(parents=True,exist_ok=True)
scope=json.loads((source/'scope.json').read_text())
start=pd.Timestamp(scope['start']);cutoff=pd.Timestamp(scope['cutoff'])
warmup=pd.Timestamp('2026-10-01T00:00:00Z')
modes=[('original',FZASMEngine),
 ('lifecycle',partial(FZASMEngine,poi_lifecycle=True)),
 ('daily_on_lifecycle',partial(FZASMEngine,daily_filter=True,entry_only_targets=True,poi_lifecycle=True)),
 ('daily_off_lifecycle',partial(FZASMEngine,daily_filter=False,entry_only_targets=True,poi_lifecycle=True))]
scope.update(warmup=str(warmup),source_artifact=14023956100,
 modes={name:'Research lifecycle variant' if name!='original' else 'Unchanged baseline' for name,_ in modes},
 comparison='Original versus lifecycle changes only zone availability/retirement; daily arms use fixed targets')
(out/'scope.json').write_text(json.dumps(scope,indent=2))
summary=[]
for pair in ['NZDJPY','EURUSD','GBPUSD']:
 cached=load_minute_df(pair,2026,2026)
 saved=pd.read_csv(source/f'{pair}_M1.csv',index_col=0,parse_dates=True)
 common=cached.index.intersection(saved.index)
 cols=['open','high','low','close']
 if len(common) and not ((cached.loc[common,cols]-saved.loc[common,cols]).abs()<1e-8).all().all():
  raise RuntimeError('Snapshot/cache OHLC conflict '+pair)
 df=pd.concat([cached[cached.index<saved.index[0]],saved]).sort_index()
 df=df[(df.index>=warmup)&(df.index+pd.Timedelta(minutes=1)<=cutoff)]
 if df.index[0]>warmup+pd.Timedelta(days=1):raise RuntimeError('Missing October warmup '+pair)
 daily_frame=pd.read_csv(source/f'{pair}_D1.csv',index_col=0,parse_dates=True)
 daily,audit=candles_from_native_daily(daily_frame,cutoff)
 if audit['missing_weekday_gaps']:raise RuntimeError('Unverified D1 gaps '+pair)
 for name,factory in modes:
  trades=replay(pair,df,out/name/pair,engine_factory=factory,requested_start=start,requested_end=cutoff,native_daily=daily)
  records=records_of(trades)
  summary.append(dict(pair=pair,mode=name,signals=len(trades)//2,rows=len(records)))
  print('MATCHED='+json.dumps(summary[-1]),flush=True)
 # Also retain the old seven-day warmup arm to measure the initialization effect.
 replay(pair,df[df.index>=start-pd.Timedelta(days=7)],out/'short_warmup_control'/pair,
        requested_start=start,requested_end=cutoff,native_daily=daily)
 if pair=='NZDJPY':
  clock=pd.Timestamp('2026-11-11T03:00:00Z');refs={}
  for history,frame in [('october',df),('short',df[df.index>=start-pd.Timedelta(days=7)])]:
   closed={tf:[c for c in df_to_candles(resample_ohlc(frame,rule),TimeFrame(tf)) if c.available_at<=clock][-240:] for tf,rule in {'H1':'1h','H2':'2h','H4':'4h','M5':'5min'}.items()}
   closed['D1']=[c for c in daily if c.available_at<=clock][-240:]
   for name,factory in modes:
    for policy in ['h1_av','h1_av_m5','swing_ob','swing_fvg']:
     e=factory(extra_pairs={pair},entry_policy=policy);s=e.scan_asset(pair,closed,clock)
     refs[history+':'+name+':'+policy]=dict(entry=s.entry_price if s else None,diagnostics=dict(e.diagnostics),context=getattr(e,'last_context_review',None),pois=getattr(e,'last_poi_review',[]))
  (out/'NZDJPY-reference.json').write_text(json.dumps(refs,indent=2,default=str))
(out/'summary.json').write_text(json.dumps(summary,indent=2))

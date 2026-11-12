"""Short cached-M1 validation with genuine broker D1, no annual replay."""
from pathlib import Path
import json
import pandas as pd
from slk.store import _open_client
from fzasm.data import load_minute_df,resample_ohlc,df_to_candles
from fzasm.native_daily import candles_from_native_daily
from fzasm.study import replay,POLICIES
from fzasm.types import TimeFrame
from fzasm.engine import FZASMEngine
from fzasm.sessions import HourlySweepDetector
from fzasm.recognition import recognize_retests

out=Path('reports/native-daily-validation');out.mkdir(parents=True,exist_ok=True)
cutoff=pd.Timestamp('2026-11-12T00:00:00Z');start=pd.Timestamp('2026-11-01T00:00:00Z')
pairs=['NZDJPY','GBPUSD','EURUSD'];native={};audits={}
client=_open_client()
try:
 for pair in pairs:
  rows=client.trendbar_rows(pair,'D1',int(pd.Timestamp('2026-09-01T00:00:00Z').timestamp()),int((cutoff+pd.Timedelta(minutes=1)).timestamp()))
  frame=pd.DataFrame([r[:5] for r in rows],columns=['time','open','high','low','close'])
  frame['time']=pd.to_datetime(frame.time,unit='s',utc=True);frame=frame.set_index('time').sort_index()
  frame.to_csv(out/f'{pair}_native_D1.csv')
  native[pair],audits[pair]=candles_from_native_daily(frame,cutoff)
  (out/f'{pair}_daily_audit.json').write_text(json.dumps(audits[pair],indent=2,default=str))
  if audits[pair]['missing_weekday_gaps']:raise RuntimeError('Unverified native D1 gaps for '+pair)
  if not native[pair]:raise RuntimeError('No closed native D1 for '+pair)
finally:client.close()
(out/'daily_audit.json').write_text(json.dumps(audits,indent=2,default=str))
summary=[]
for pair in pairs:
 df=load_minute_df(pair,2026,2026)
 df=df[(df.index>=pd.Timestamp('2026-10-01T00:00:00Z'))&(df.index+pd.Timedelta(minutes=1)<=cutoff)]
 trades=replay(pair,df,out/pair,requested_start=start,requested_end=cutoff,native_daily=native[pair])
 counts={p:len({t.setup.timestamp for pp,t in trades if pp==p}) for p in POLICIES}
 manifest=json.loads((out/pair/'manifest.json').read_text())
 result=dict(symbol=pair,signals_by_model=counts,aggregate_counts=manifest['aggregate_counts'],diagnostics=manifest['engine_diagnostics'])
 summary.append(result);print('SHORT_VALIDATION='+json.dumps(result),flush=True)
 if pair=='NZDJPY':
  clock=pd.Timestamp('2026-11-11T03:00:00Z')
  series={tf:df_to_candles(resample_ohlc(df,rule),TimeFrame(tf)) for tf,rule in {'M5':'5min','H1':'1h','H2':'2h','H4':'4h'}.items()}
  closed={tf:[c for c in bars if c.available_at<=clock][-240:] for tf,bars in series.items()}
  closed['D1']=[c for c in native[pair] if c.available_at<=clock][-240:]
  sweep=HourlySweepDetector.detect_h1_sweep(closed['H1'])
  ob=next((r for r in recognize_retests(closed['M5'],sweep,clock) if r['route']=='order_block'),None)
  ref=dict(native_d1_available=len(closed['D1']),main_order_block=ob,full_context={})
  for p in POLICIES:
   e=FZASMEngine(extra_pairs={pair},entry_policy=p);plan=e.scan_asset(pair,closed,clock)
   ref['full_context'][p]=dict(entry=plan.entry_price if plan else None,diagnostics=dict(e.diagnostics))
  (out/'NZDJPY-reference.json').write_text(json.dumps(ref,indent=2));print('REFERENCE_VALIDATION='+json.dumps(ref),flush=True)
(out/'summary.json').write_text(json.dumps(summary,indent=2))
if not any(sum(r['signals_by_model'].values()) for r in summary):
 raise RuntimeError('Short validation still has zero qualified signals; inspect diagnostics, do not launch annual study')

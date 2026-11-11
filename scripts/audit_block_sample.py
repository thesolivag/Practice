"""Bounded cross-symbol candidate audit. No orders, P&L or outcome selection."""
from pathlib import Path
import json, hashlib
import pandas as pd
from slk.store import _open_client
from fzasm.data import resample_ohlc, df_to_candles
from fzasm.types import TimeFrame
from fzasm.sessions import HourlySweepDetector
from fzasm.block_audit import block_candidates

out=Path('reports/block-sample');out.mkdir(parents=True,exist_ok=True)
start=pd.Timestamp('2026-11-10T00:00:00Z');end=pd.Timestamp('2026-11-11T10:00:00Z')
# Fixed before looking at results. No entire-catalogue scan.
symbols=['EURUSD','GBPUSD']
client=_open_client(); summaries=[]
try:
 for symbol in symbols:
  rows=[]
  for lo in pd.date_range(start,end,freq='4h',inclusive='left'):
   hi=min(lo+pd.Timedelta(hours=4),end)
   rows.extend(r[:5] for r in client.trendbar_rows(symbol,'M1',int(lo.timestamp()),int(hi.timestamp())) if lo.timestamp()<=r[0]<hi.timestamp())
  df=pd.DataFrame(rows,columns=['time','open','high','low','close']).sort_values('time')
  if df.empty or df.time.duplicated().any():raise RuntimeError('Empty/duplicate data for '+symbol)
  df.time=pd.to_datetime(df.time,unit='s',utc=True)
  raw=df.to_csv(index=False).encode();(out/f'{symbol}_M1.csv').write_bytes(raw)
  df=df.set_index('time');h=df_to_candles(resample_ohlc(df,'1h'),TimeFrame.H1);m=df_to_candles(resample_ohlc(df,'5min'),TimeFrame.M5)
  events=[];sweeps=0
  for i in range(1,len(h)):
   s=HourlySweepDetector.detect_h1_sweep(h[:i+1])
   if not s or not s.swept:continue
   sweeps+=1;clock=h[i].available_at
   blocks=block_candidates(m,s,clock)
   if blocks:
    events.append(dict(clock=clock.isoformat(),direction=s.direction.value,blocks=blocks))
    if len(events)<=2:
     candles=[dict(time=c.timestamp.isoformat(),open=c.open,high=c.high,low=c.low,close=c.close) for c in m if h[i-1].timestamp<=c.timestamp and c.available_at<=clock]
     print('BLOCK_CHART='+json.dumps(dict(symbol=symbol,event=events[-1],candles=candles)))
  meta=dict(symbol=symbol,start=str(start),end=str(end),rows=len(df),sha256=hashlib.sha256(raw).hexdigest(),h1_sweeps=sweeps,candidate_setups=len(events),scope='H1 close decisions only; no daily map/session qualification or trade results',events=events)
  (out/f'{symbol}.json').write_text(json.dumps(meta,indent=2));summaries.append(meta)
  print('BLOCK_SUMMARY='+json.dumps(meta))
finally:client.close()

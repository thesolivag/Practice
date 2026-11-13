"""Read-only GitHub comparison; fixed shared cutoff and no broker orders."""
from pathlib import Path
import json
import pandas as pd
from slk.store import _open_client
from fzasm.data import load_minute_df,resample_ohlc,df_to_candles
from fzasm.native_daily import candles_from_native_daily
from fzasm.study import replay,records_of
from fzasm.engine import FZASMEngine
from fzasm.asian_only import AsianOnlyEngine
from fzasm import instruments
from fzasm.types import TimeFrame

out=Path('reports/asian-only-comparison');out.mkdir(parents=True,exist_ok=True)
cutoff=pd.Timestamp.now(tz='UTC').floor('min');start=pd.Timestamp('2026-11-01T00:00:00Z')
(out/'scope.json').write_text(json.dumps(dict(start=str(start),cutoff=str(cutoff),
 modes={'filtered':'Existing D1 + H4 POI + prime hours','asian_only':'H1 sweep in 00–06 UTC; no daily, H4 POI or prime-hours gate'},
 targets='1R/2R/3R/4R and frozen Asian extreme; FZ target unavailable in entry-only',
 costs='Gross BID results; no spread/commission/slippage',h2='Entry-only uses H1; no H2 fallback'),indent=2))
summary=[]
client=_open_client()
try:
 for pair in ['NZDJPY','EURUSD','GBPUSD']:
  info=client.symbol(pair);instruments.register(pair,info.get('pip_position'),info.get('digits'))
  df=load_minute_df(pair,2026,2026)
  df=df[(df.index>=start-pd.Timedelta(days=7))&(df.index+pd.Timedelta(minutes=1)<=cutoff)]
  if df.empty:raise RuntimeError('Missing cached warmup '+pair)
  batches=[]
  for lo in pd.date_range(df.index[-1]+pd.Timedelta(minutes=1),cutoff,freq='4h',inclusive='left'):
   hi=min(lo+pd.Timedelta(hours=4),cutoff)
   rows=client.trendbar_rows(pair,'M1',int(lo.timestamp()),int(hi.timestamp()))
   batches.extend(r[:5] for r in rows if lo.timestamp()<=r[0]<hi.timestamp())
  if batches:
   new=pd.DataFrame(batches,columns=['time','open','high','low','close']);new['time']=pd.to_datetime(new.time,unit='s',utc=True)
   df=pd.concat([df,new.set_index('time')]).sort_index();df=df[~df.index.duplicated(keep='first')]
  df=df[df.index+pd.Timedelta(minutes=1)<=cutoff]
  if cutoff-df.index[-1]>pd.Timedelta(minutes=30):raise RuntimeError('Stale M1 data '+pair)
  df.to_csv(out/f'{pair}_M1.csv')
  rows=client.trendbar_rows(pair,'D1',int(pd.Timestamp('2026-09-01T00:00:00Z').timestamp()),int(cutoff.timestamp()))
  d=pd.DataFrame([r[:5] for r in rows],columns=['time','open','high','low','close']);d['time']=pd.to_datetime(d.time,unit='s',utc=True);d=d.set_index('time').sort_index()
  daily,audit=candles_from_native_daily(d,cutoff);d.to_csv(out/f'{pair}_D1.csv')
  if audit['missing_weekday_gaps']:raise RuntimeError('Unverified daily gaps '+pair)
  for name,factory in [('filtered',FZASMEngine),('asian_only',AsianOnlyEngine)]:
   trades=replay(pair,df,out/name/pair,engine_factory=factory,requested_start=start,requested_end=cutoff,native_daily=daily)
   records=records_of(trades)
   result=dict(pair=pair,mode=name,signals=len(trades)//2,rows=len(records),status_counts=pd.Series([r['status'] for r in records]).value_counts().to_dict())
   summary.append(result);print('COMPARISON='+json.dumps(result),flush=True)
  if pair=='NZDJPY':
   clock=pd.Timestamp('2026-11-11T03:00:00Z')
   closed={tf:[c for c in df_to_candles(resample_ohlc(df,rule),TimeFrame(tf)) if c.available_at<=clock][-240:] for tf,rule in {'H1':'1h','H2':'2h','H4':'4h','M5':'5min'}.items()}
   closed['D1']=[c for c in daily if c.available_at<=clock]
   refs={}
   for name,factory in [('filtered',FZASMEngine),('asian_only',AsianOnlyEngine)]:
    for policy in ['h1_av','h1_av_m5','swing_ob','swing_fvg']:
     e=factory(extra_pairs={pair},entry_policy=policy);s=e.scan_asset(pair,closed,clock)
     refs[name+':'+policy]=dict(entry=s.entry_price if s else None,diagnostics=dict(e.diagnostics),context=getattr(e,'last_context_review',None))
   (out/'NZDJPY-reference.json').write_text(json.dumps(refs,indent=2,default=str))
finally:client.close()
(out/'summary.json').write_text(json.dumps(summary,indent=2))

"""Frozen January–October research, serial provider collection, causal gap quarantine."""
import argparse,json
from pathlib import Path
from functools import partial
import pandas as pd
from slk.store import _open_client
from fzasm.data import load_minute_df
from fzasm.native_daily import candles_from_native_daily
from fzasm.engine import FZASMEngine
from fzasm.study import replay,records_of
from fzasm import instruments
from fzasm.research_metrics import metrics

ap=argparse.ArgumentParser();ap.add_argument('--pair',required=True);args=ap.parse_args();pair=args.pair
out=Path('reports/frozen-year')/pair;out.mkdir(parents=True,exist_ok=True)
start=pd.Timestamp('2026-01-01T00:00:00Z');end=pd.Timestamp('2026-11-01T00:00:00Z');warmup=pd.Timestamp('2025-12-01T00:00:00Z')
cached=load_minute_df(pair,2026,2026);cached=cached[(cached.index>=start)&(cached.index+pd.Timedelta(minutes=1)<=end)]
if cached.empty or cached.index[0]>start+pd.Timedelta(days=4) or cached.index[-1]<end-pd.Timedelta(days=4):raise RuntimeError('Incomplete annual M1 cache '+pair)
client=_open_client()
try:
 info=client.symbol(pair);instruments.register(pair,info.get('pip_position'),info.get('digits'))
 rows=client.trendbar_rows(pair,'D1',int(pd.Timestamp('2025-11-01T00:00:00Z').timestamp()),int(end.timestamp()))
 d=pd.DataFrame([r[:5] for r in rows],columns=['time','open','high','low','close']);d['time']=pd.to_datetime(d.time,unit='s',utc=True);d=d.set_index('time').sort_index()
 d.to_csv(out/'native_D1.csv');daily,audit=candles_from_native_daily(d,end)
 if len(daily)<180 or d.index[0]>=start or d.index[-1]<end-pd.Timedelta(days=4):raise RuntimeError('Insufficient native D1 coverage')
 (out/'daily_audit.json').write_text(json.dumps(audit,indent=2))
 batches=[];chunkroot=Path('data/asm-warmup')/pair;chunkroot.mkdir(parents=True,exist_ok=True)
 for lo in pd.date_range(warmup,start,freq='4h',inclusive='left'):
  hi=lo+pd.Timedelta(hours=4)
  hours=pd.date_range(lo,hi,freq='h',inclusive='left').tz_convert('America/New_York')
  if all(t.dayofweek==5 or (t.dayofweek==4 and t.hour>=17) or (t.dayofweek==6 and t.hour<17) for t in hours):continue
  path=chunkroot/(str(int(lo.timestamp()))+'.json')
  if path.exists():batch=json.loads(path.read_text())
  else:
   batch=[list(r[:5]) for r in client.trendbar_rows(pair,'M1',int(lo.timestamp()),int(hi.timestamp())) if lo.timestamp()<=r[0]<hi.timestamp()]
   if batch:path.write_text(json.dumps(batch))
  batches.extend(batch)
finally:client.close()
w=pd.DataFrame(batches,columns=['time','open','high','low','close']);w['time']=pd.to_datetime(w.time,unit='s',utc=True);w=w.set_index('time').sort_index()
if w.empty or w.index[0]>warmup+pd.Timedelta(days=3):raise RuntimeError('Missing December warmup')
df=pd.concat([w,cached]).sort_index()
if df.index.has_duplicates:raise RuntimeError('Duplicate M1 timestamps')
w.to_csv(out/'warmup_M1.csv')
# Missing weekdays are not bridged into an apparent multi-day map.
# Quarantine map evaluation until three subsequent native bars establish fresh context.
gaps=[(pd.Timestamp(g['open']),pd.Timestamp(g['next_open'])) for g in audit['missing_weekday_gaps']]
class GuardedEngine(FZASMEngine):
 def scan_asset(self,symbol,candles_by_tf,current_time=None,force_session=False):
  data=dict(candles_by_tf);reset=None
  for lo,hi in gaps:
   if current_time>=lo+pd.Timedelta(hours=26):
    reset=hi
    if current_time<hi:
     self._contexts.pop(symbol,None);self.diagnostics['native_daily_gap_quarantine']+=1;return None
  if reset is not None:
   data['D1']=[c for c in data.get('D1',[]) if c.timestamp>=reset]
   if len(data['D1'])<3:
    self._contexts.pop(symbol,None);self.diagnostics['native_daily_gap_quarantine']+=1;return None
  return super().scan_asset(symbol,data,current_time,force_session)
summary=[]
for mode,enabled in [('daily_on',True),('daily_off',False)]:
 factory=partial(GuardedEngine,daily_filter=enabled,entry_only_targets=True,poi_lifecycle=True)
 trades=replay(pair,df,out/mode,engine_factory=factory,requested_start=start,requested_end=end,native_daily=daily)
 records=pd.DataFrame(records_of(trades))
 if len(records):
  records['month']=pd.to_datetime(records.timestamp,utc=True).dt.strftime('%Y-%m')
  for period,frame in [('ALL',records)]+list(records.groupby('month')):
   for (policy,stop,target),group in frame.groupby(['entry_policy','stop_variant','target']):
    for cost in [0.,.5,1.,2.]:
     summary.append(dict(pair=pair,mode=mode,period=period,entry_policy=policy,stop_variant=stop,target=target,cost_pips=cost,**metrics(group,cost,instruments.pip(pair))))
pd.DataFrame(summary).to_csv(out/'risk_cost_metrics.csv',index=False)
(out/'COMPLETE.json').write_text(json.dumps(dict(pair=pair,start=str(start),end=str(end),warmup=str(warmup),pip=instruments.pip(pair),
 native_gap_quarantine=audit['missing_weekday_gaps'],m1_rows=len(df),
 limitations=['Native weekday gaps quarantine BOTH arms, including daily-off, for matched coverage','UTC intraday research calendar','Fixed pip round-trip deductions are sensitivity scenarios, not historical bid/ask execution','Drawdown and streaks use resolved exits only; exclude unresolved and unrealized exposure','Four entry models overlap; do not sum them','November excluded; end-of-October open trades remain unresolved']),indent=2))

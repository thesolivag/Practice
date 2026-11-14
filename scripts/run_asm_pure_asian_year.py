"""The November pure Asian entry model, replayed on January–October data."""
import argparse,json
from pathlib import Path
import pandas as pd
from fzasm.data import load_minute_df
from fzasm.asian_only import AsianOnlyEngine
from fzasm.study import replay,records_of
import os
from fzasm.research_metrics import metrics
ap=argparse.ArgumentParser();ap.add_argument('--pair',required=True);pair=ap.parse_args().pair
out=Path('reports/frozen-year')/pair;out.mkdir(parents=True,exist_ok=True)
source=Path('reports/prior-pair')
from fzasm import instruments
import math
meta=json.loads((source/'COMPLETE.json').read_text())
instruments.register(pair,int(round(-math.log10(meta['pip']))))
w=pd.read_csv(source/'warmup_M1.csv',index_col=0,parse_dates=True)
d=load_minute_df(pair,2026,2026)
start=pd.Timestamp('2026-01-01T00:00Z');end=pd.Timestamp('2026-11-01T00:00Z')
d=d[(d.index>=start)&(d.index+pd.Timedelta(minutes=1)<=end)]
df=pd.concat([w[w.index<start],d]).sort_index()
if df.index.has_duplicates or d.empty:raise RuntimeError('Invalid M1 input')
# No daily evaluation, no H4 requirement, no daily-gap quarantine, no prime-hour gate.
buffer_only=os.environ.get('ASM_BUFFER_ONLY')=='1'
trades=replay(pair,df,out/'asian_only',engine_factory=AsianOnlyEngine,requested_start=start,requested_end=end,
              stop_variants=('sweep_plus_3p',) if buffer_only else None)
if buffer_only:
 for _,trade in trades:
  plan=trade.setup
  sign=1 if plan.stop_loss>plan.entry_price else -1
  assert plan.stop_variant=='sweep_plus_3p'
  assert abs(plan.stop_loss-(plan.h1_sweep.sweep_price+sign*3*instruments.pip(pair)))<1e-8
records=pd.DataFrame(records_of(trades));summary=[]
if len(records):
 records['month']=pd.to_datetime(records.timestamp,utc=True).dt.strftime('%Y-%m')
 for period,frame in [('ALL',records)]+list(records.groupby('month')):
  for (policy,stop,target),group in frame.groupby(['entry_policy','stop_variant','target']):
   for label,cost in [('gross',0.),('user_4_per_50_risk',.08)]:
    summary.append(dict(pair=pair,mode='asian_only',period=period,entry_policy=policy,stop_variant=stop,target=target,cost_model=label,cost_r=cost,**metrics(group,cost_r=cost)))
pd.DataFrame(summary).to_csv(out/'risk_cost_metrics.csv',index=False)
(out/'COMPLETE.json').write_text(json.dumps(dict(pair=pair,stop_variants=['sweep_plus_3p'] if buffer_only else ['sweep_exact','sweep_plus_3p'],native_gap_quarantine=[],start=str(start),end=str(end),
 model='Same AsianOnlyEngine as November sample: completed H1 sweep during 00–06 UTC, four entry routes, no H2 fallback',
 costs='0.08R per resolved filled trade is user example, not verified broker billing; unresolved costs excluded',
 target='1R/2R/3R/4R and known Asian opposite extreme; daily FZ target unavailable',
 expiry='Pending orders expire at 06:00 UTC; filled trades can continue beyond Asian session',
 source='Original annual cache plus archived December warmup',
 limitations='Gross BID replay; unknown outcomes separate, no daily-gap exclusion, no live orders'),indent=2))

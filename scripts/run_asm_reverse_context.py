"""Annotate frozen trades; do not reselect entries or replay outcomes."""
import argparse,json,hashlib,math
from pathlib import Path
import pandas as pd
from fzasm.data import load_minute_df,df_to_candles,resample_ohlc
from fzasm.native_daily import candles_from_native_daily
from fzasm.types import TimeFrame
from fzasm.reverse_context import context_features,partition,comparisons

p=argparse.ArgumentParser();p.add_argument('--pair',required=True);a=p.parse_args()
prior=Path('reports/prior-pair');ledger=Path('reports/ledger/asian_only/outcomes.csv')
meta=json.loads((prior/'COMPLETE.json').read_text());pip=float(meta['pip'])
ledger_meta=json.loads(Path('reports/ledger/COMPLETE.json').read_text())
assert ledger_meta['stop_variants']==['sweep_plus_3p']
assert pd.Timestamp(ledger_meta['end'])==pd.Timestamp('2026-11-01T00:00Z')
rows=pd.read_csv(ledger);rows=rows[rows.stop_variant=='sweep_plus_3p'].copy()
assert not rows.duplicated(['signal_id','target']).any()
assert set(rows.symbol)=={a.pair}
raw=pd.read_csv(prior/'native_D1.csv',index_col=0,parse_dates=True)
daily,audit=candles_from_native_daily(raw,pd.Timestamp('2026-11-01T00:00Z'))
df=load_minute_df(a.pair,2026,2026)
w=pd.read_csv(prior/'warmup_M1.csv',index_col=0,parse_dates=True)
df=pd.concat([w[w.index<df.index.min()],df]).sort_index()
assert not df.index.has_duplicates
series={tf:df_to_candles(resample_ohlc(df,rule),TimeFrame(tf)) for tf,rule in [('H1','1h'),('H2','2h'),('H4','4h')]};series['D1']=daily
features=[]
# Outcomes deliberately not passed to context extraction.
for _,s in rows.drop_duplicates('signal_id').iterrows():
    safe={k:s[k] for k in ['timestamp','entry_price','stop_price','entry_evidence']}
    now=pd.Timestamp(s.timestamp);frames=series
    prior_gaps=[g for g in audit['missing_weekday_gaps'] if pd.Timestamp(g['open'])+pd.Timedelta(hours=26)<=now]
    if prior_gaps:
        reset=max(pd.Timestamp(g['next_open']) for g in prior_gaps)
        frames={**series,'D1':[c for c in daily if c.timestamp>=reset]}
    f=context_features(safe,frames,pip)
    features.append(dict(signal_id=s.signal_id,**f))
out=Path('reports/reverse')/a.pair;out.mkdir(parents=True,exist_ok=True)
ft=pd.DataFrame(features);ft.to_csv(out/'features.csv',index=False)
joined=rows.merge(ft,on='signal_id',validate='many_to_one');assert len(joined)==len(rows)
joined['phase']=joined.timestamp.map(partition)
joined.to_csv(out/'annotated_outcomes.csv',index=False)
comparisons(joined).to_csv(out/'comparisons.csv',index=False)
manifest=dict(pair=a.pair,source_run=43574624074,source_ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest(),
 native_daily_sha256=hashlib.sha256((prior/'native_D1.csv').read_bytes()).hexdigest(),
 m1_sha256=hashlib.sha256(pd.util.hash_pandas_object(df,index=True).values.tobytes()).hexdigest(),
 signals=len(ft),outcome_rows=len(rows),unmatched_or_ambiguous_sweeps=int((ft.sweep_match_count!=1).sum()),
 invalid_context=int((~ft.context_valid).sum()),native_daily_audit=audit,
 limitations=['Frozen prior entry ledger; not a repaired-engine rerun','Previously examined historical validation, not untouched holdout','Research map detectors are not teacher-certified','Missing/ambiguous sweep context not inferred from outcome','0.08R assumed cost; independent scenarios not portfolio profit'])
(out/'manifest.json').write_text(json.dumps(manifest,indent=2,default=str))
print(json.dumps({k:v for k,v in manifest.items() if k!='native_daily_audit'},indent=2))

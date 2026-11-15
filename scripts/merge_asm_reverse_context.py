import json
from pathlib import Path
import pandas as pd
from fzasm.reverse_context import comparisons,candidates,summarize
root=Path('pair-artifacts');out=Path('reports/reverse-summary');out.mkdir(parents=True,exist_ok=True)
expected=['USDJPY','EURJPY','GBPJPY','AUDJPY','NZDJPY','CADJPY','CHFJPY','XAUUSD','EURUSD','GBPUSD']
files=list(root.rglob('annotated_outcomes.csv'));frames=[pd.read_csv(p) for p in files]
if not frames:raise RuntimeError('No completed pair evidence')
table=pd.concat(frames,ignore_index=True)
missing=sorted(set(expected)-set(table.symbol));stats=comparisons(table)
pooled=table.copy();pooled['symbol']='ALL_PAIRS';stats=pd.concat([stats,comparisons(pooled)],ignore_index=True)
stats.to_csv(out/'context_comparisons.csv',index=False)
selected=candidates(stats)
(out/'discovery_candidates.json').write_text(json.dumps(selected,indent=2))
validation=[]
for c in selected:
    match=stats[(stats.phase=='validation') & stats.present.eq(True)]
    for k in ['symbol','entry_policy','target','feature']:match=match[match[k]==c[k]]
    for r in match.to_dict('records'):validation.append(dict(c,**{('validation_'+k):v for k,v in r.items() if k not in c}))
pd.DataFrame(validation).to_csv(out/'candidate_validation.csv',index=False)
monthly=[]
for (symbol,policy,target,phase,month),g in table.groupby(['symbol','entry_policy','target','phase',table.timestamp.str[:7]]):
    monthly.append(dict(symbol=symbol,policy=policy,target=target,phase=phase,month=month,**summarize(g)))
pd.DataFrame(monthly).to_csv(out/'baseline_monthly.csv',index=False)
(out/'REPORT.md').write_text(f'''# ASM reverse-context research

Source ledger:43574624074. Completed pairs:{table.symbol.nunique()}/10. Missing:{missing}.
Discovery candidates meeting frozen thresholds:{len(selected)}. See candidate_validation.csv for their historical validation results, including failures. Do not add target variants, routes or overlapping feature groups together.

Discovery:Jan1–Jun25 decisions, resolved exits beforeJul1. Embargo:Jun26–Jul5. Validation:Jul6–Oct31. Historical data was previously examined; this is not an untouched holdout. All outcomes remain visible; unknowns excluded from resolved-return means, not assigned zero. Costs0.08R assumed. Minimum30 resolved in both feature-present and feature-absent discovery groups, at least3 resolved months in the present group, positive mean netR and improvement over absent group. Seven fixed single-factor features; no combinatorial search. Multiple comparisons can produce chance candidates; no significance or income claim. Raw baseline and feature comparisons preserve unfilled/unavailable/unknown counts.

Map and level detectors are research interpretations. Matching a feature does not prove teacher fidelity. Incomplete pair coverage prevents an all-market conclusion.
''')
print((out/'REPORT.md').read_text())

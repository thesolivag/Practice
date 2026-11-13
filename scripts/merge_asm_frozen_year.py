from pathlib import Path
import json
import pandas as pd
from fzasm.study import PAIRS
root=Path('pair-artifacts');out=Path('reports/frozen-summary');out.mkdir(parents=True,exist_ok=True)
metrics=[];status=[]
for pair in PAIRS:
 found=list(root.glob('asm-frozen-'+pair+'/COMPLETE.json'))
 if len(found)!=1:
  status.append(dict(pair=pair,status='MISSING_OR_INCOMPLETE'));continue
 p=found[0].parent;meta=json.loads(found[0].read_text())
 status.append(dict(pair=pair,status='COMPLETE_WITH_QUARANTINES' if meta['native_gap_quarantine'] else 'COMPLETE',native_gap_count=len(meta['native_gap_quarantine'])))
 f=p/'risk_cost_metrics.csv'
 if f.exists() and f.stat().st_size>1:metrics.append(pd.read_csv(f))
pd.DataFrame(status).to_csv(out/'coverage.csv',index=False)
if metrics:pd.concat(metrics,ignore_index=True).to_csv(out/'all_pair_monthly_risk_cost_metrics.csv',index=False)
lines=['# Frozen ASM January–October 2026 study','', 'November excluded. Each model/stop/target is an alternative; do not sum overlapping model profits.', '', '| Pair | Coverage |','|---|---|']
lines += [f"| {r['pair']} | {r['status']} |" for r in status]
lines += ['', 'Reports include gross and 0.5/1/2-pip round-trip cost sensitivity. These are assumptions, not measured net returns. Drawdown and streaks use resolved exits only; unknown trades remain excluded. Missing pair jobs are not zero trades. See each pair artifact for raw outcomes, monthly coverage, native daily audit and diagnostics.']
(out/'REPORT.md').write_text('\n'.join(lines)+'\n')

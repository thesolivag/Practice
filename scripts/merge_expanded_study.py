"""Merge available pair artifacts; expose absent/unfinished jobs as missing coverage."""
import argparse,json
from pathlib import Path
import pandas as pd
from fzasm.study import PAIRS,POLICIES
from fzasm.study_report import write_study_report

ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out',required=True);ap.add_argument('--as-of',required=True)
a=ap.parse_args();root=Path(a.input);records=[];coverage=[];sources=[]
for path in sorted(root.rglob('outcomes.csv')):
 frame=pd.read_csv(path)
 if not frame.empty:records.extend(frame.where(pd.notnull(frame),None).to_dict('records'))
 cp=path.parent/'coverage.csv'
 if cp.exists():
  rows=pd.read_csv(cp).to_dict('records')
  final=(path.parent/'manifest.json').exists()
  for r in rows:
   if not final:r['status']='partial'
  coverage.extend(rows)
 sources.append(str(path))
cutoff=pd.Timestamp(a.as_of);year=cutoff.year
known={(r['symbol'],r['entry_policy'],r['month']) for r in coverage}
for pair in PAIRS:
 for policy in POLICIES:
  for date in pd.date_range(pd.Timestamp(year=year,month=1,day=1,tz='UTC'),cutoff,freq='MS',inclusive='left'):
   key=(pair,policy,date.strftime('%Y-%m'))
   if key not in known:coverage.append(dict(symbol=pair,entry_policy=policy,month=key[2],status='missing'))
write_study_report(records,a.out,coverage)
Path(a.out,'sources.json').write_text(json.dumps(dict(artifacts=sources,as_of=a.as_of,expected_pairs=PAIRS,policies=POLICIES),indent=2))
print(f'Merged {len(sources)} pair artifacts; missing coverage remains explicit')

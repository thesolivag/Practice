from pathlib import Path
import json
import pandas as pd
from fzasm.data import df_to_candles,resample_ohlc
from fzasm.types import TimeFrame
from fzasm.sessions import HourlySweepDetector
from fzasm.block_audit import block_candidates
p=Path('evidence/block-audit/cross-symbol.json');data=json.loads(p.read_text())
for j,item in enumerate(data['charts']):
 df=pd.DataFrame(item['candles']);df['time']=pd.to_datetime(df.time,utc=True);df=df.set_index('time')
 m=df_to_candles(df,TimeFrame.M5)
 # H1 from 12 contiguous M5 bars; resample_ohlc expects M1, so aggregate explicitly.
 hh=df.resample('1h').agg({'open':'first','high':'max','low':'min','close':'last'})
 h=df_to_candles(hh,TimeFrame.H1);s=HourlySweepDetector.detect_h1_sweep(h)
 rows=block_candidates(m,s,h[-1].available_at)
 item['event']['blocks']=rows
 if j==0:df.to_csv('tests/data/gbpusd_block_20261110_m5.csv')
 print(item['event']['clock'],[(r['origin_time'],r['role']) for r in rows])
Path('evidence/block-audit/cross-symbol-rechecked.json').write_text(json.dumps(data,indent=2))

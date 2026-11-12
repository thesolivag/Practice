"""Read-only cached NZDJPY data audit; no downloads or strategy changes."""
import json
from pathlib import Path
import pandas as pd
from fzasm.data import load_minute_df,resample_ohlc,df_to_candles
from fzasm.types import TimeFrame
from fzasm.maps import DailyMapEvaluator
from fzasm.engine import FZASMEngine

df=load_minute_df('NZDJPY',2026,2026)
clock=pd.Timestamp('2026-11-11T03:00:00Z')
rules={'M5':'5min','H1':'1h','H2':'2h','H4':'4h','D1':'1D'}
series={tf:df_to_candles(resample_ohlc(df,rule),TimeFrame(tf)) for tf,rule in rules.items()}
closed={tf:[c for c in bars if c.available_at<=clock][-240:] for tf,bars in series.items()}
e=FZASMEngine(extra_pairs={'NZDJPY'},entry_policy='h1_av_m5')
counts=df.resample('1D').size()
result=dict(m1_rows=len(df),first=df.index[0].isoformat(),last=df.index[-1].isoformat(),
 aggregate_counts={tf:len(bars) for tf,bars in series.items()},
 reference_closed_counts={tf:len(bars) for tf,bars in closed.items()},
 days_with_any_minutes=int((counts>0).sum()),days_with_1440_minutes=int((counts==1440).sum()),
 daily_minute_count_distribution={str(k):int(v) for k,v in counts.value_counts().sort_index().items()},
 reference_daily_map_available=DailyMapEvaluator.evaluate(closed['D1']) is not None,
 reference_full_context_available=e._build_context('NZDJPY',closed,clock) is not None)
Path('reports/zero-signal-diagnostic').mkdir(parents=True,exist_ok=True)
Path('reports/zero-signal-diagnostic/NZDJPY.json').write_text(json.dumps(result,indent=2))
print('ZERO_SIGNAL_DIAGNOSTIC='+json.dumps(result))

from pathlib import Path
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from fzasm.data import resample_ohlc,df_to_candles
from fzasm.types import TimeFrame
from fzasm.sessions import HourlySweepDetector
from fzasm.block_audit import block_candidates

out=Path('evidence/block-audit');out.mkdir(parents=True,exist_ok=True)
d=pd.read_csv('evidence/nzdjpy-reference/NZDJPY_M1.csv',index_col='time',parse_dates=True)
h=df_to_candles(resample_ohlc(d,'1h'),TimeFrame.H1)
m=df_to_candles(resample_ohlc(d,'5min'),TimeFrame.M5)
records=[]
for i in range(1,len(h)):
 s=HourlySweepDetector.detect_h1_sweep(h[:i+1])
 if not s or not s.swept: continue
 clock=h[i].available_at
 rows=block_candidates(m,s,clock)
 if not rows:continue
 records.append(dict(clock=clock.isoformat(),direction=str(s.direction),candidates=rows))
 bars=[c for c in m if h[i-1].timestamp<=c.timestamp and c.available_at<=clock]
 fig,ax=plt.subplots(figsize=(12,6))
 for j,c in enumerate(bars):
  color='#008f75' if c.close>=c.open else '#d94b65'
  ax.vlines(j,c.low,c.high,color=color)
  ax.add_patch(Rectangle((j-.3,min(c.open,c.close)),.6,max(abs(c.close-c.open),.0003),color=color))
 for n,r in enumerate(rows):
  j=next(j for j,c in enumerate(bars) if c.timestamp.isoformat()==r['origin_time'])
  color=plt.get_cmap('tab10')(n)
  ax.add_patch(Rectangle((j,r['zone_low']),len(bars)-j,r['zone_high']-r['zone_low'],facecolor=color,alpha=.13,edgecolor=color))
  label=r['role'].replace('_',' ')+' '+(pd.Timestamp(r['origin_time'])+pd.Timedelta(hours=1)).strftime('%H:%M')
  if r['origin_time']=='2026-11-11T02:30:00+00:00':label+=' | YOUR violation block reference'
  ax.plot([],[],color=color,label=label)
  ax.text(j,bars[j].high,str(n+1),color=color)
 ax.set_xticks(range(0,len(bars),4),[(bars[j].timestamp+pd.Timedelta(hours=1)).strftime('%H:%M') for j in range(0,len(bars),4)])
 ax.ticklabel_format(axis='y',useOffset=False)
 ax.set_title('NZDJPY M5 candidate audit | '+clock.strftime('%Y-%m-%d %H:%M UTC')+' decision\nAll candidates retained; no future retest used to choose a winner')
 ax.set_xlabel('Candle open time WAT (UTC+1) | IC Markets BID; screenshot is FOREX.com')
 ax.legend(fontsize=8);ax.grid(alpha=.2)
 fig.tight_layout();fig.savefig(out/f"{clock.strftime('%Y%m%d-%H%M')}.png",dpi=140);plt.close(fig)
(out/'all-setups.json').write_text(json.dumps(records,indent=2))
print('Audited setups:',len(records));print([(r['clock'],len(r['candidates'])) for r in records])

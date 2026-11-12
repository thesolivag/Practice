from pathlib import Path
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from fzasm.data import df_to_candles,resample_ohlc
from fzasm.types import TimeFrame
from fzasm.sessions import HourlySweepDetector
from fzasm.recognition import recognize_retests
p=Path('evidence/main-block-repair');p.mkdir(parents=True,exist_ok=True)
d=pd.read_csv('tests/data/nzdjpy_20261111_m1.csv',index_col='time',parse_dates=True)
h=df_to_candles(resample_ohlc(d,'1h'),TimeFrame.H1);m=df_to_candles(resample_ohlc(d,'5min'),TimeFrame.M5)
s=HourlySweepDetector.detect_h1_sweep(h[:3]);clock=h[2].available_at
ob=next(x for x in recognize_retests(m,s,clock) if x['route']=='order_block')
bars=[c for c in m if c.available_at<=clock and c.timestamp>=pd.Timestamp('2026-11-11T01:00:00Z')]
fig,ax=plt.subplots(figsize=(13,7));fig.patch.set_facecolor('#101b29');ax.set_facecolor('#101b29')
for i,c in enumerate(bars):
 color='#45cfab' if c.is_bullish else '#ef7589'
 ax.vlines(i,c.low,c.high,color=color)
 ax.add_patch(Rectangle((i-.28,min(c.open,c.close)),.56,max(abs(c.close-c.open),.0005),facecolor=color))
origin=next(i for i,c in enumerate(bars) if c.timestamp.isoformat()==ob['origin_time'])
ax.add_patch(Rectangle((origin,ob['zone_low']),len(bars)-origin,ob['zone_high']-ob['zone_low'],color='#6cb9ff',alpha=.2))
ax.scatter(origin,bars[origin].high,marker='v',s=100,color='#ffce65',label='New main origin: 03:10 WAT')
ax.axhline(ob['entry'],color='#6cb9ff',ls='--',label=f"New main-block entry {ob['entry']:.3f}")
ax.axhline(89.130,color='#bdadce',ls=':',label='Previous lower entry 89.130 (replaced)')
ax.axhline(s.sweep_price,color='#ef7589',ls='--',label=f'Exact sweep stop {s.sweep_price:.3f}')
ax.axhline(s.sweep_price+.03,color='#ef7589',ls=':',label=f'Buffered stop {s.sweep_price+.03:.3f}')
ax.axhline(ob['structure_boundary'],color='#ffce65',ls=':',label=f"M5 CHoCH boundary {ob['structure_boundary']:.3f}")
ticks=list(range(0,len(bars),3));ax.set_xticks(ticks,[(bars[i].timestamp+pd.Timedelta(hours=1)).strftime('%H:%M') for i in ticks]);ax.tick_params(colors='white')
ax.ticklabel_format(axis='y',useOffset=False);ax.grid(alpha=.15)
ax.set_title('NZDJPY | repaired main order-block selection\nNovember 11, 2026 — only candles closed by 04:00 WAT',color='white',loc='left',fontsize=14)
ax.set_xlabel('Candle OPEN times in WAT (UTC+1)',color='white')
ax.legend(facecolor='#22354b',labelcolor='white',fontsize=9,loc='upper left',bbox_to_anchor=(1.01,1))
fig.subplots_adjust(left=.08,right=.72,bottom=.22,top=.85)
fig.text(.08,.07,'The earlier upper origin is now used by the trading selector, not only the review helper.\nZone = source candle body-to-wick (89.134–89.185): exact teacher zone boundaries remain unverified.\nReal IC Markets BID data; reference screenshot is FOREX.com. This is an entry-module comparison.',color='white',fontsize=10)
fig.savefig(p/'NZDJPY-main-block-repaired.png',dpi=150)
(p/'selected-block.json').write_text(json.dumps(ob,indent=2))

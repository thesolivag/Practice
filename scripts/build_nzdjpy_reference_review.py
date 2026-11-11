"""Reproducible reference-case comparison. Screenshot labels are comparison only."""
from pathlib import Path
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_pdf import PdfPages
from fzasm.data import resample_ohlc,df_to_candles
from fzasm.types import *
from fzasm.sessions import HourlySweepDetector
from fzasm.recognition import recognize_retests
source=Path('tests/data/nzdjpy_20261111_m1.csv')
d=pd.read_csv(source,index_col='time',parse_dates=True)
h=df_to_candles(resample_ohlc(d,'1h'),TimeFrame.H1);m=df_to_candles(resample_ohlc(d,'5min'),TimeFrame.M5)
sweep=HourlySweepDetector.detect_h1_sweep(h[:3]);clock=h[2].available_at
events=recognize_retests(m,sweep,clock)
out=Path('evidence/nzdjpy-reference');out.mkdir(parents=True,exist_ok=True)
(out/'detected_events.json').write_text(json.dumps(events,indent=2))
plt.rcParams.update({'figure.facecolor':'#101b29','axes.facecolor':'#101b29','text.color':'#edf3fa','axes.labelcolor':'#edf3fa','xtick.color':'#c0d1e3','ytick.color':'#c0d1e3','font.size':11})
cases=[('H1',h[:3],h[1].close,89.118,'H1 sweep / A-junction: price matches within 0.1 pip',None),
       ('M5', [c for c in m if c.available_at<=clock],next(e['entry'] for e in events if e['route']=='fvg_av_overlap'),89.122,'FVG overlap: nearby price, DIFFERENT origin remains unverified','fvg_av_overlap'),
       ('M5', [c for c in m if c.available_at<=clock],next(e['entry'] for e in events if e['route']=='order_block'),89.125,'Order block: model selects 03:40 candle, not proven to be your block','order_block')]
with PdfPages(out/'NZDJPY-reference-review.pdf') as pdf:
 for num,(tf,bars,entry,user_entry,title,route) in enumerate(cases,1):
  fig,ax=plt.subplots(figsize=(13,7));fig.subplots_adjust(left=.08,right=.75,bottom=.24,top=.85)
  for i,c in enumerate(bars):
   color='#49d9ae' if c.close>=c.open else '#f67c8b'
   ax.vlines(i,c.low,c.high,color=color,lw=1.2)
   ax.add_patch(Rectangle((i-.28,min(c.open,c.close)),.56,max(abs(c.close-c.open),.0005),facecolor=color))
  lines=[('Model entry',entry,'#6cb9ff','--'),('Your marked entry',user_entry,'#eeeeee',':'),('Model SL: 3-pip buffer',89.215,'#ff7888','--'),('Your marked SL',89.192 if route=='order_block' else 89.190,'#ffce65',':')]
  for label,value,color,style in lines:ax.axhline(value,color=color,ls=style,label=f'{label}: {value:.3f}')
  if tf=='H1':
   ax.axhline(h[1].high,color='#a9a1ed',ls=':',label=f'Previous high {h[1].high:.3f}')
   ax.axhline(h[1].low,color='#58d0bd',ls=':',label=f'Previous low standing {h[1].low:.3f}')
   ax.scatter(2,h[2].high,color='#ffce65',s=80,zorder=5)
  else:
   item=next(e for e in events if e['route']==route)
   ax.axhspan(item['zone_low'],item['zone_high'],color='#62c8ee',alpha=.22)
   ax.axhline(item['structure_boundary'],color='#a9a1ed',ls=':',label=f"Protected low {item['structure_boundary']:.3f}")
   origin=next(i for i,c in enumerate(bars) if c.timestamp.isoformat()==item['origin_time'])
   ax.scatter(origin,bars[origin].high,color='#ffce65',marker='v',s=100,zorder=5,label='Chosen level-origin candle')
   br=next(i for i,c in enumerate(bars) if c.available_at.isoformat()==item['break_time'])
   ax.scatter(br,bars[br].close,color='#bca7ff',s=85,zorder=5,label='First close below protected low')
  tick=list(range(0,len(bars),max(1,len(bars)//8)));ax.set_xticks(tick,[(bars[i].timestamp+pd.Timedelta(hours=1)).strftime('%H:%M') for i in tick])
  ax.set_xlabel('November 11, 2026 — candle OPEN times in UTC+1, matching your chart')
  ax.ticklabel_format(axis='y',style='plain',useOffset=False);ax.grid(alpha=.12)
  ax.set_title('NZDJPY '+tf+' | '+title+'\nDecision at 04:00 UTC+1 (03:00 UTC); no candles after the decision',loc='left',fontsize=12,color='white',pad=16)
  ax.legend(loc='upper left',bbox_to_anchor=(1.01,1),facecolor='#23354a',labelcolor='white',fontsize=9)
  fig.text(.08,.09,'Data: IC Markets bid candles; your reference is FOREX.com. Feed differences do not prove rule equivalence.\nH1 high: 89.185. Previous low remains intact. Default model SL: 89.215 — farther away than yours.\nEntry-module audit only: full daily-bias qualification and target selection are NOT established here.',fontsize=10,color='#cbd8e6')
  fig.savefig(out/f'comparison-{num}.png',dpi=150);pdf.savefig(fig);plt.close(fig)
print('Saved 3 comparison charts and PDF')

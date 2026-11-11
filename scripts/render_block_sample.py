from pathlib import Path
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
out=Path('evidence/block-audit')
data=json.loads((out/'cross-symbol-rechecked.json').read_text())
for n,item in enumerate(data['charts'],1):
 bars=item['candles'];event=item['event'];fig,ax=plt.subplots(figsize=(12,6))
 for i,c in enumerate(bars):
  color='#008f75' if c['close']>=c['open'] else '#d94b65'
  ax.vlines(i,c['low'],c['high'],color=color)
  ax.add_patch(Rectangle((i-.3,min(c['open'],c['close'])),.6,max(abs(c['close']-c['open']),.000005),color=color))
 for j,b in enumerate(event['blocks']):
  i=next(i for i,c in enumerate(bars) if c['time']==b['origin_time']);color=plt.get_cmap('tab10')(j)
  ax.add_patch(Rectangle((i,b['zone_low']),len(bars)-i,b['zone_high']-b['zone_low'],facecolor=color,alpha=.18))
  ax.plot([],[],color=color,label=f"{j+1}: {b['role']} | entry candidate {b['entry']:.5f}")
  ax.text(i,bars[i]['high'],str(j+1),color=color)
 ax.set_xticks(range(0,len(bars),4),[(pd.Timestamp(bars[i]['time'])+pd.Timedelta(hours=1)).strftime('%H:%M') for i in range(0,len(bars),4)])
 ax.set_title(item['symbol']+' '+event['direction']+' | decision '+event['clock']+'\nFirst chronological samples; candidates, not validated trades')
 ax.set_xlabel('M5 candle open time WAT | IC Markets BID | no future candles shown')
 ax.ticklabel_format(axis='y',useOffset=False);ax.legend(fontsize=8);ax.grid(alpha=.2);fig.tight_layout()
 fig.savefig(out/f'GBPUSD-{n}.png',dpi=140);plt.close(fig)

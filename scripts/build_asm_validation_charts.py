from pathlib import Path
import pandas as pd
from fzasm.data import resample_ohlc,df_to_candles
from fzasm.types import *
from fzasm.sessions import HourlySweepDetector
from fzasm.entry import EntryModelEvaluator
import argparse
parser=argparse.ArgumentParser(description="Render entry/stop placement examples from recorded GBPUSD M1 data")
parser.add_argument('--source',required=True,help='GBPUSD M1 CSV.gz with UTC time/open/high/low/close columns')
parser.add_argument('--out',default='evidence/av-validation')
args=parser.parse_args()
p=Path(args.source)
df=pd.read_csv(p,index_col='time',parse_dates=True)
h=df_to_candles(resample_ohlc(df,'1h'),TimeFrame.H1);m=df_to_candles(resample_ohlc(df,'5min'),TimeFrame.M5)
samples=[]
for i in range(24,len(h)):
 c=h[i]
 # All hours for component placement review, not session-qualified trades.
 sweep=HourlySweepDetector.detect_h1_sweep(h[:i+1])
 if not sweep:continue
 long=sweep.direction==BiasDirection.BULLISH
 prior=h[max(0,i-24):i]
 target=max(x.high for x in prior) if long else min(x.low for x in prior)
 origin=sweep.sweep_price
 dm=DailyMapResult(MapType.MAP_1_STRUCTURAL_RANGE,sweep.direction,origin,target,(origin+target)/2,0,'Chart-only prior 24H reference range; NOT scanner daily-map qualification',c.available_at)
 av=EntryModelEvaluator.evaluate_h1_av('GBPUSD',h[:i+1],sweep,dm)
 if av:samples.append(('H1',av,h[max(0,i-12):i+1]))
 for j,b in enumerate(m):
  if b.timestamp<c.available_at:continue
  if b.available_at>c.available_at+pd.Timedelta(hours=2):break
  after=[x for x in m[:j+1] if x.timestamp>=c.available_at]
  if any((x.low<origin or x.high>=target) if long else (x.high>origin or x.low<=target) for x in after):break
  s=EntryModelEvaluator.evaluate_entry('GBPUSD',m[max(0,j-30):j+1],sweep,dm,require_shift=True)
  if s:
   samples.append(('M5',s,m[max(0,j-20):j+1]));break



import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_pdf import PdfPages
import json,hashlib
out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'figure.facecolor':'#101b29','axes.facecolor':'#101b29','text.color':'#edf3fa','axes.labelcolor':'#edf3fa','xtick.color':'#c0d1e3','ytick.color':'#c0d1e3','font.size':10})
choices=[['2026-06-26T02:00:00+00:00','2026-06-26T02:20:00+00:00'],['2026-06-30T03:00:00+00:00'],['2026-07-08T02:25:00+00:00']]
records=[]
with PdfPages(out/'ASM-entry-stop-validation.pdf') as pdf:
 for num,times in enumerate(choices,1):
  selected=[next(row for row in samples if row[1].timestamp.isoformat()==t) for t in times]
  fig,axes=plt.subplots(len(selected),1,figsize=(13,6*len(selected)),squeeze=False)
  for ax,(tf,s,bars) in zip(axes[:,0],selected):
   for i,c in enumerate(bars):
    color='#49d9ae' if c.close>=c.open else '#f67c8b'
    ax.vlines(i,c.low,c.high,color=color,lw=1.3)
    ax.add_patch(Rectangle((i-.28,min(c.open,c.close)),.56,max(abs(c.close-c.open),.000005),facecolor=color,edgecolor=color))
   levels=[('Entry',s.entry_price,'#6cb9ff'),('H1 sweep SL',s.stop_loss,'#ff7888')]
   if tf=='M5' and s.stop_candidates.get('ltf_invalidation'):
    levels.append(('M5 local SL',s.stop_candidates['ltf_invalidation'],'#ffce65'))
    ax.axhline(s.entry_evidence['structure_boundary'],color='#b7a1ef',linestyle=':',alpha=.65)
    ax.text(.02,.04,'Dotted purple: four-bar break boundary',transform=ax.transAxes,color='#b7a1ef')
    if s.key_level.level_type==LevelType.FAIR_VALUE_GAP:
     ax.axhspan(s.key_level.price_bottom,s.key_level.price_top,color='#62c8ee',alpha=.14)
    origin_time=s.entry_evidence.get('local_stop_origin')
    origin_index=next((i for i,c in enumerate(bars) if c.timestamp.isoformat()==origin_time),None)
    if origin_index is not None:ax.scatter(origin_index,bars[origin_index].high,marker='v',s=75,color='#ffce65',zorder=6,label='Local stop origin candle')
   else:
    ax.plot(range(len(bars)),[c.close for c in bars],color='#c9b1ff',alpha=.65,lw=1,label='Close-price line / A-V vertex')
    ax.scatter(len(bars)-2,s.entry_price,color='#6cb9ff',s=80,zorder=7)
   for label,price,color in levels:
    ax.axhline(price,color=color,ls='--',lw=1.2)
    risk=abs(s.entry_price-price)/.0001
    ax.text(len(bars)+.1,price,f'{label} {price:.5f}'+(f' ({risk:.1f} pips)' if label!='Entry' else ''),color=color,va='center',fontsize=10)
   sweep=s.h1_sweep.sweep_price
   ax.axhline(sweep,color='#f49c83',ls=':',alpha=.5)
   for gap_i in range(1,len(bars)):
    if bars[gap_i-1].available_at != bars[gap_i].timestamp:
     ax.axvline(gap_i-.5,color='#98a5b5',ls=':',alpha=.7)
     ax.text(gap_i-.5,.98,'gap',transform=ax.get_xaxis_transform(),rotation=90,va='top',color='#98a5b5',fontsize=8)
   ax.set_xlim(-.7,len(bars)+6)
   tick=list(range(0,len(bars),max(1,len(bars)//7)));ax.set_xticks(tick,[bars[i].timestamp.strftime('%d %b\n%H:%M') for i in tick])
   ax.ticklabel_format(axis='y',style='plain',useOffset=False)
   ax.grid(alpha=.12)
   title=('Direct H1 A/V junction' if tf=='H1' else 'M5 structural break + retest')
   ax.set_title(f'GBPUSD {s.bias.value} | {title}\nDecision: {s.timestamp:%Y-%m-%d %H:%M} UTC — only candles closed by this time',loc='left',color='white',pad=15)
   if tf=='M5' and origin_index is not None or tf=='H1':ax.legend(loc='upper left',facecolor='#23354a',labelcolor='white')
   records.append({'timeframe':tf,'decision':s.timestamp.isoformat(),'entry':s.entry_price,'stops':s.stop_candidates,'evidence':s.entry_evidence,'bars':[{'time':c.timestamp.isoformat(),'open':c.open,'high':c.high,'low':c.low,'close':c.close} for c in bars]})
  fig.text(.06,.025,'REAL IC Markets M1 data, aggregated to UTC H1/M5. Placement review only: daily-map/POI qualification not asserted.\nNo future candles, fills or profit claims. Horizontal lines are pending plans. Stop buffer: 3 pips. A/V rule is provisional.',fontsize=10,color='#d1deea')
  fig.subplots_adjust(left=.08,right=.94,bottom=.15 if len(selected)==1 else .09,top=.85 if len(selected)==1 else .91,hspace=.42)
  fig.savefig(out/f'validation-{num}.png',dpi=150);pdf.savefig(fig);plt.close(fig)
(out/'evidence.json').write_text(json.dumps({'source':p.name,'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'scope':'Entry/stop component review, not qualified strategy trades','examples':records},indent=2))
print(f'Created {len(choices)} chart pages in {out}')

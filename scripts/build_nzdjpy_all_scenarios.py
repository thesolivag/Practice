"""Plot real reference candles and conditional entry geometry, never fake trades.
The year-study has no NZDJPY signals; no daily-map target is invented here.
"""
from pathlib import Path
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_pdf import PdfPages
from fzasm.data import resample_ohlc,df_to_candles
from fzasm.types import TimeFrame
from fzasm.sessions import HourlySweepDetector
from fzasm.recognition import recognize_retests,recognize_shift

root=Path('evidence/nzdjpy-all-scenarios');root.mkdir(parents=True,exist_ok=True)
df=pd.read_csv('evidence/nzdjpy-reference/NZDJPY_M1.csv',index_col='time',parse_dates=True)
h=df_to_candles(resample_ohlc(df,'1h'),TimeFrame.H1);m=df_to_candles(resample_ohlc(df,'5min'),TimeFrame.M5)
clock=pd.Timestamp('2026-11-11T03:00:00Z');day=clock.normalize()
hclosed=[c for c in h if c.available_at<=clock];s=HourlySweepDetector.detect_h1_sweep(hclosed)
shift=recognize_shift(m,s,clock);events=recognize_retests(m,s,clock)
a,b=hclosed[-2:];assert a.is_bullish and b.is_bearish
entry=a.close
session=df[(df.index>=day)&(df.index+pd.Timedelta(minutes=1)<=clock)]
assert len(session)==180 and (session.index.to_series().diff().dropna()==pd.Timedelta(minutes=1)).all()
asian=float(session.low.min())
obs={r:next(e for e in events if e['route']==r) for r in ['order_block','fvg_av_overlap']}
cases=[('01-direct-H1','Direct H1 A-shaped key level',entry,None),
       ('02-H1-M5-confirmation','H1 A-shaped key level + M5 CHoCH',entry,shift['common']),
       ('03-M5-order-block','M5 order-block route (provisional)',obs['order_block']['entry'],obs['order_block']),
       ('04-M5-FVG-key-level','M5 FVG + A/V key level (provisional)',obs['fvg_av_overlap']['entry'],obs['fvg_av_overlap'])]
plt.rcParams.update({'figure.facecolor':'#101b29','axes.facecolor':'#101b29','text.color':'#edf3fa','axes.labelcolor':'#edf3fa','xtick.color':'#b7c7d9','ytick.color':'#b7c7d9','font.size':10})
def candles(ax,bars):
 for i,c in enumerate(bars):
  color='#45cfab' if c.close>=c.open else '#ef7589'
  ax.vlines(i,c.low,c.high,color=color,lw=1)
  ax.add_patch(Rectangle((i-.29,min(c.open,c.close)),.58,max(abs(c.close-c.open),.0004),facecolor=color))
 step=max(1,len(bars)//8);ticks=list(range(0,len(bars),step))
 ax.set_xticks(ticks,[(bars[i].timestamp+pd.Timedelta(hours=1)).strftime('%H:%M') for i in ticks])
 ax.ticklabel_format(axis='y',useOffset=False);ax.grid(alpha=.12)
 ax.set_xlabel('Candle OPEN time, WAT (UTC+1)')
def line(ax,value,label,color,style='--'):
 ax.axhline(value,color=color,ls=style,lw=1,label=f'{label}: {value:.3f}')
def legend(ax):ax.legend(loc='upper left',bbox_to_anchor=(1.01,1),fontsize=8,facecolor='#213349',labelcolor='white')
records=[]
with PdfPages(root/'NZDJPY-all-scenarios.pdf') as pdf:
 fig,ax=plt.subplots(figsize=(13,7));fig.subplots_adjust(left=.08,right=.74,bottom=.22,top=.84)
 bars=[c for c in h if pd.Timestamp('2026-11-10T18:00:00Z')<=c.timestamp<clock]
 candles(ax,bars)
 for value,label,color in [(a.high,'Previous H1 high','#b69df1'),(a.low,'Previous H1 low: standing','#b69df1'),(s.sweep_price,'H1 sweep extreme','#f17b8e'),(entry,'H1 A-shaped key level','#6ab9ff'),(asian,'Asian low known at decision','#f9ce75')]:line(ax,value,label,color)
 ax.set_title('NZDJPY | H1 context before the decision\n11 November 2026; decision 04:00 WAT / 03:00 UTC',loc='left',fontsize=14)
 legend(ax);fig.text(.08,.08,'REAL IC Markets BID candles; your screenshot uses FOREX.com.\nConditional entry-pattern review: the completed year-study generated ZERO qualified NZDJPY signals.\nNo FZ map target or executed trade is asserted by these charts.',fontsize=11)
 fig.savefig(root/'00-H1-context.png',dpi=150);pdf.savefig(fig);plt.close(fig)
 for name,title,price,evidence in cases:
  fig=plt.figure(figsize=(15,13));grid=fig.add_gridspec(2,2,height_ratios=[1,1.2],hspace=.42,wspace=.72)
  ax=fig.add_subplot(grid[0,:]);pre=[c for c in m if day+pd.Timedelta(hours=1)<=c.timestamp and c.available_at<=clock]
  candles(ax,pre);line(ax,price,'Conditional entry','#6ab9ff');line(ax,s.sweep_price,'H1 sweep high','#f17b8e')
  if evidence:
   line(ax,shift['common']['structure_boundary'],'M5 protected low / CHoCH boundary','#b69df1',':')
   broken=next(i for i,c in enumerate(pre) if c.available_at.isoformat()==shift['common']['break_time'])
   ax.scatter(broken,pre[broken].close,s=65,color='#f9ce75',zorder=5)
   ax.annotate('M5 break closes 03:55 WAT',(broken,pre[broken].close),xytext=(broken-10,pre[broken].close-.045),arrowprops={'arrowstyle':'->','color':'#f9ce75'},color='#f9ce75')
  if evidence and 'zone_low' in evidence:
   ax.axhspan(evidence['zone_low'],evidence['zone_high'],alpha=.2,color='#70b9fc')
   origin=next(i for i,c in enumerate(pre) if c.timestamp.isoformat()==evidence['origin_time'])
   ax.scatter(origin,pre[origin].high,s=80,marker='v',color='#f9ce75',zorder=5)
   ax.annotate('Selected origin '+(pd.Timestamp(evidence['origin_time'])+pd.Timedelta(hours=1)).strftime('%H:%M')+' WAT',(origin,pre[origin].high),xytext=(origin-3,pre[origin].high+.03),arrowprops={'arrowstyle':'->','color':'#f9ce75'},color='#f9ce75')
  ax.set_title('Detection view: only candles closed by 04:00 WAT',loc='left');ax.legend(fontsize=8,facecolor='#213349',labelcolor='white',loc='upper left')
  post=[c for c in m if day+pd.Timedelta(hours=2)<=c.timestamp<day+pd.Timedelta(hours=10)]
  decision=next(i for i,c in enumerate(post) if c.timestamp==clock)
  for col,buffer in enumerate([0.,.03]):
   ax=fig.add_subplot(grid[1,col]);candles(ax,post)
   stop=s.sweep_price+buffer;risk=stop-price
   targets={f'{r}R':price-r*risk for r in range(1,5)}
   line(ax,price,'Entry','#6ab9ff');line(ax,stop,'SL','#f17b8e')
   for j,(label,value) in enumerate(targets.items()):line(ax,value,label,['#4dd4ad','#7ce0c4','#adebdc','#d1f6ed'][j],':')
   line(ax,asian,'Frozen Asian low','#f9ce75','-.')
   ax.axvspan(decision,len(post)-.5,color='white',alpha=.035)
   ax.axvline(decision,color='white',lw=1,ls='--')
   ax.set_title(('Exact sweep stop' if buffer==0 else 'Sweep + 3 pips stop')+f' | risk {risk/.01:.1f} pips',loc='left')
   legend(ax)
   records.append(dict(model=name,entry=price,decision=clock.isoformat(),stop=stop,stop_buffer_pips=buffer/.01,targets=targets,asian_target=asian,fz_target=None,full_strategy_signal=False))
  fig.suptitle('NZDJPY | '+title+'\nCONDITIONAL GEOMETRY — not a qualified backtest trade',fontsize=16,y=.98)
  detail=('Direct H1 and H1+M5 use the same 89.117 level here; the M5 break is already known by the H1 close.' if name.startswith(('01','02')) else 'OB origin: 03:40 WAT. It is NOT your 03:30 violation-block marking.' if name.startswith('03') else 'FVG overlap origin: 02:30 WAT (older level). This teacher match remains unverified.')
  fig.text(.06,.065,detail+'\nBottom panels include later candles for visual context only; future candles do not choose the entry or targets.\nFZ TARGET: UNAVAILABLE — no qualified daily-map target established for this illustration.\nAll fixed-R targets are independent alternatives, not four partial exits. Source: IC Markets BID; screenshot: FOREX.com.',fontsize=10)
  fig.subplots_adjust(top=.90,bottom=.18,left=.06,right=.83)
  fig.savefig(root/(name+'.png'),dpi=140);pdf.savefig(fig);plt.close(fig)
(root/'levels.json').write_text(json.dumps(records,indent=2))
print(json.dumps(dict(asian_low=asian,h1_entry=entry,scenarios=len(records),outputs=str(root))))

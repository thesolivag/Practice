"""Actual frozen IC candles and GitHub paper-fill evidence, no synthetic prices."""
import csv,gzip,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as md
from matplotlib.patches import Rectangle

OUT=Path(__file__).parent
CASE=Path('reports/implementation_review/usdcad_quote_40693590233/reports/primary_video_replay/fourth_man_decision.json')
d=json.loads(CASE.read_text());assert len(d['orders'])==1
o=d['orders'][0];obs=d['observations'][0];assert obs['outcome']=='OPEN' and obs['status']=='FILLED'
f=Path('data/teacher_icmarkets_runs/40098655754/data/teacher_icmarkets/collect_c058fc002a50237cd6d2dbb0.csv.gz')
rows=list(csv.DictReader(gzip.decompress(f.read_bytes()).decode().splitlines()))
rows=[r for r in rows if '2026-06-12T10:00'<=r['time']<'2026-06-12T21:00']
fig,ax=plt.subplots(figsize=(13,7),dpi=150);fig.patch.set_facecolor('#f7fafc');ax.set_facecolor('white')
for r in rows:
 t=datetime.fromisoformat(r['time']);x=md.date2num(t+timedelta(minutes=30));op,hi,lo,cl=[float(r[k]) for k in ('open','high','low','close')]
 color='#0a8a73' if cl>=op else '#5a6675'
 if t.hour==14:color='#2673c4'
 if t.hour==15:color='#c98700'
 ax.vlines(x,lo,hi,color=color,lw=1.5)
 ax.add_patch(Rectangle((x-.27/24,min(op,cl)),.54/24,max(abs(op-cl),.000006),facecolor=color,edgecolor=color))
start=md.date2num(datetime(2026,6,12,16,tzinfo=timezone.utc));end=md.date2num(datetime(2026,6,12,21,tzinfo=timezone.utc))
for price,color,label in [(o['entry_ticks']/1e5,'#0a8a73','LIMIT ENTRY 1.39680'),(o['stop_ticks']/1e5,'#c54343','STOP 1.39587'),(o['target_ticks']/1e5,'#7656aa','TARGET 1.40240')]:
 ax.hlines(price,start,end,color=color,lw=1.5,linestyle='--');ax.text(end+.08/24,price,label,color=color,va='center',fontsize=10,fontweight='bold')
mid=datetime.fromisoformat(obs['fill_window']['start'])+timedelta(seconds=30)
ax.annotate('M1 paper fill\n16:13–16:14 UTC',xy=(md.date2num(mid),o['entry_ticks']/1e5),xytext=(md.date2num(mid)+1.7/24,1.4003),fontsize=11,color='#0a8a73',arrowprops={'arrowstyle':'->','color':'#0a8a73'})
ax.set_xlim(md.date2num(datetime(2026,6,12,9,45,tzinfo=timezone.utc)),end+2.4/24)
ax.set_ylim(1.3953,1.4029);ax.grid(axis='y',alpha=.18);ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.5f'));ax.xaxis.set_major_locator(md.HourLocator(interval=1,tz=timezone.utc));ax.xaxis.set_major_formatter(md.DateFormatter('%H:%M',tz=timezone.utc))
ax.set_xlabel('12 June 2026 · UTC');ax.set_ylabel('USDCAD bid price')
ax.set_title('4TH MAN BUY — paper entry placed and filled',loc='left',fontsize=18,fontweight='bold',pad=18)
fig.text(.07,.035,'Blue = previous H1 candle; gold = low swept, close inside prior range, prior high untouched.\nOPEN at 13 June 00:00 UTC. Zero-cost replay; Bishop additionally used M30 engulfing. Exact teacher-trade equivalence remains unverified.',fontsize=10,color='#334155')
fig.subplots_adjust(left=.07,right=.98,bottom=.18,top=.9);fig.savefig(OUT/'comparison.png');plt.close(fig)
(OUT/'evidence.json').write_text(json.dumps(dict(run_id=40693590233,order=o,observation=obs,source_caveat=d['source_caveat']),indent=2)+'\n')

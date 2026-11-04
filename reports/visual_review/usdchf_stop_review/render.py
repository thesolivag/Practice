"""Render frozen replay candles alongside the original mentor frame."""
from pathlib import Path
import gzip,json
from datetime import timedelta,timezone
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as md
import matplotlib.image as mi
from matplotlib.patches import Rectangle
from bishop.v2.feed import load_feed
from bishop.v2.aggregation import aggregate
from bishop.v2.types import utc
out=Path(__file__).parent
pdoc=json.load(gzip.open('reports/implementation_review/primary_video_40583792823/video-t3-usdchf-buy.json.gz'));p=pdoc['plan'];r=pdoc['result']
s=next(s for s in r['setups'] if s['id']=='setup_03218dbc80d7f2b74e5dcb2a')
assert s['entry_ticks']==79838
assert s['details']['confirmation_protection_bar_ids']==['bar_b171f0effbdc5b4eb8b3f801','bar_0b219a3c3cd483f0ec9720f6']
assert s['stop_ticks']>79647
order=next((o for o in r['orders'] if o['setup_id']==s['id']),None)
obs=next((o for o in r['observations'] if order and o.get('id')==order['id']),None)
m=json.loads(Path(p['manifest_path']).read_text());f=load_feed(p['input_path'],m,p['as_of'],p['history_start']);bars=aggregate(f['bars'],'H2',f['instrument'],p['as_of'],calendar=m.get('calendar',m['calendar_id']))['bars'];tick=float(f['instrument'].tick_size)
low=next(b for b in bars if b.id=='bar_04b234709c2a7b812916b96c');assert low.low_ticks==79652
lo=min(low.start-timedelta(hours=2),utc('2026-06-10T13:00:00Z'));hi=utc('2026-06-11T15:00:00Z');bs=[b for b in bars if lo<=b.start<hi]
fig,ax=plt.subplots(figsize=(16,8),dpi=160);w=1.25/24
for b in bs:
 x=md.date2num(b.start+timedelta(hours=1));o,h,l,c=[getattr(b,k+'_ticks')*tick for k in ('open','high','low','close')];col='#13856e' if c>=o else '#3d4b60'
 ax.vlines(x,l,h,color=col);ax.add_patch(Rectangle((x-w/2,min(o,c)),w,max(abs(c-o),.000015),facecolor=col,edgecolor=col))
left=md.date2num(lo);right=md.date2num(hi);ax.set_xlim(left-.04,right+8/24);ax.set_ylim(min(b.low_ticks*tick for b in bs)-.0004,max(b.high_ticks*tick for b in bs)+.0005)
for price,color,style,label in [(.79647,'#cb343b',':','OLD BOT STOP  0.79647'),(.79838,'#2369ac','--','BOT ENTRY  0.79838')]:
 ax.hlines(price,left,right,color=color,ls=style,lw=1.8);ax.text(right+.3/24,price,label,color=color,va='center',fontsize=12,fontweight='bold')
ax.hlines(.79783,left,right,color='#8849a2',ls='--',lw=1.7)
ax.annotate('BISHOP STOP  0.79783',xy=(right,.79783),xytext=(right+.3/24,.79755),color='#8849a2',fontsize=12,fontweight='bold',arrowprops={'arrowstyle':'-','color':'#8849a2'})
newstop=s['stop_ticks']*tick
ax.hlines(newstop,md.date2num(utc('2026-06-11T07:00:00Z')),right,color='#13856e',lw=2)
ax.annotate(f'CORRECTED STOP  {newstop:.5f}',xy=(right,newstop),xytext=(right+.3/24,.79812),color='#13856e',fontsize=12,fontweight='bold',arrowprops={'arrowstyle':'-','color':'#13856e'})
ax.axvspan(md.date2num(utc('2026-06-10T15:00:00Z')),md.date2num(utc('2026-06-10T17:00:00Z')),color='#8db7e8',alpha=.3)
ax.text(md.date2num(utc('2026-06-10T16:00:00Z')),.80125,'FIRST engulfing',ha='center',fontsize=11,color='#2369ac')
ax.text(md.date2num(utc('2026-06-11T06:00:00Z')),.80125,'SECOND engulfing',ha='center',fontsize=11,color='#926100')
ax.axvspan(md.date2num(utc('2026-06-11T05:00:00Z')),md.date2num(utc('2026-06-11T07:00:00Z')),color='#ffce63',alpha=.3)
ax.annotate('First engulfing reference low 0.79652\nIt belongs to the FIRST entry',xy=(md.date2num(low.start+timedelta(hours=1)),.79652),xytext=(left+.025,.7972),arrowprops={'arrowstyle':'->','color':'#cb343b'},fontsize=11,color='#cb343b')
ax.set_title('CORRECTED — second engulfing uses its own stop candles | IC Markets H2',loc='left',fontsize=15,fontweight='bold',pad=18)
ax.xaxis.set_major_locator(md.HourLocator(interval=4,tz=timezone.utc));ax.xaxis.set_major_formatter(md.DateFormatter('%d Jun\n%H:%M UTC',tz=timezone.utc));ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.5f'));ax.grid(axis='y',alpha=.2);ax.set_ylabel('USDCHF bid price')
fig.text(.07,.025,f'Corrected bot stop {newstop:.5f}; Bishop drawing {0.79783:.5f}. Difference {abs(newstop-.79783)/.0001:.1f} pips.\nThe second confirmation replaces the first as pattern-risk evidence; nearby structure protection remains. Entries differ across feeds.',fontsize=11)
fig.subplots_adjust(left=.07,right=.98,top=.9,bottom=.18);fig.savefig(out/'bot_h2_actual_candles.png');plt.close(fig)
fig,axs=plt.subplots(2,1,figsize=(16,18),dpi=160);axs[0].imshow(mi.imread(out/'bishop_original_1485s.png'));axs[0].set_title('BISHOP — original video at 24:45 | USDCHF H2, FOREXcom\nDrawn entry 0.79860 • stop 0.79783 • target 0.80113',loc='left',fontsize=15,pad=15,fontweight='bold');axs[1].imshow(mi.imread(out/'bot_h2_actual_candles.png'))
for a in axs:a.axis('off')
fig.suptitle('USDCHF: corrected confirmation and stop linkage',fontsize=23,fontweight='bold',x=.06,ha='left',y=.98);fig.subplots_adjust(left=.045,right=.985,top=.91,bottom=.02,hspace=.1);fig.savefig(out/'comparison.png');plt.close(fig)
(out/'evidence.json').write_text(json.dumps({'run':40583792823,'source_pts':1485,'source_entry':.79860,'source_stop':.79783,'source_target':.80113,'bot_setup':s,'bot_order':order,'bot_observation':obs,'previous_bot_stop':.79647,'stop_difference_pips':round(abs(newstop-.79783)/.0001,3),'correction':'Current reference/engulf pair replaces earlier context candles as pattern-risk evidence','protected_low_start':low.start.isoformat(),'acceptance':'NOT_ESTABLISHED'},indent=2)+'\n')
print('protected low',low.start,'observation',obs)

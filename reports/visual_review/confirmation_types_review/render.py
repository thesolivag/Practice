"""Source and frozen replay evidence for breakout and swept/standing confirmation."""
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
OUT=Path(__file__).parent
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12})
navy='#17344d';red='#c7353d';blue='#2569ae';purple='#844d9c';green='#13856e'
def read(run,case,tf):
 d=json.load(gzip.open(f'reports/implementation_review/primary_video_{run}/{case}.json.gz'));p=d['plan'];r=d['result'];m=json.load(open(p['manifest_path']));f=load_feed(p['input_path'],m,p['as_of'],p['history_start']);bs=aggregate(f['bars'],tf,f['instrument'],p['as_of'],calendar=m['calendar_id'])['bars'];return r,bs,float(f['instrument'].tick_size)
def candles(ax,bs,tick,width):
 for b in bs:
  x=md.date2num(b.start+(b.end-b.start)/2);o,h,l,c=[getattr(b,k+'_ticks')*tick for k in ('open','high','low','close')];col=green if c>=o else '#3b4a60'
  ax.vlines(x,l,h,color=col,lw=1.5);ax.add_patch(Rectangle((x-width/2,min(o,c)),width,max(abs(c-o),.00001),facecolor=col,edgecolor=col))
 ax.xaxis.set_major_locator(md.HourLocator(interval=2,tz=timezone.utc));ax.xaxis.set_major_formatter(md.DateFormatter('%d Jun\n%H:%M UTC',tz=timezone.utc));ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.5f'));ax.grid(axis='y',alpha=.2)
def line(ax,p,start,end,label,col,dy=0):
 ax.hlines(p,start,end,color=col,ls='--',lw=1.8)
 ax.annotate(label,xy=(end,p),xytext=(end+.25/24,p+dy),fontsize=12,color=col,fontweight='bold',va='center',arrowprops={'arrowstyle':'-','color':col})
# Breakout: earliest actually selected Jun9 H2 BO order, never chosen by outcome.
r,allbs,tick=read(40584565827,'video-t3-gbpcad-buy','H2')
o=min((o for o in r['orders'] if o['tf']=='H2' and o['model']=='confirmation_bo' and o['clock']['available_at'].startswith('2026-06-09')),key=lambda o:(o['clock']['available_at'],o['id']))
s=next(s for s in r['setups'] if s['id']==o['setup_id']);obs=next(z for z in r['observations'] if z['id']==o['id']);assert o['entry_ticks']==186271 and o['stop_ticks']==185847
lo=utc('2026-06-08T19:00:00Z');hi=utc('2026-06-09T09:00:00Z');bs=[b for b in allbs if lo<=b.start<hi];ce=next(b for b in bs if b.end==utc(o['clock']['available_at']));assert ce.low_ticks==186159
fig,ax=plt.subplots(figsize=(17,8),dpi=160);candles(ax,bs,tick,1.3/24);left=md.date2num(lo);right=md.date2num(hi);ax.set_xlim(left-.02,right+6/24);ax.set_ylim(1.8577,1.8659)
for p,label,col in [(1.85847,'BOT STOP  1.85847',red),(1.86041,'BISHOP STOP  1.86041',purple),(1.86271,'BOT ENTRY  1.86271',blue)]:line(ax,p,left,right,label,col)
ax.axvspan(md.date2num(ce.start),md.date2num(ce.end),color='#ffcf67',alpha=.3)
ax.annotate('Breakout confirmation\n03:00–05:00 UTC\nLow 1.86159',xy=(md.date2num(ce.start+timedelta(hours=1)),ce.high_ticks*tick),xytext=(left+.015,1.86555),va='top',color=navy,fontsize=12,arrowprops={'arrowstyle':'->','color':navy})
ax.annotate('Bot still protects earlier\nliquidity-take low 1.85852',xy=(md.date2num(utc('2026-06-08T22:00:00Z')),1.85852),xytext=(left+.015,1.85945),color=red,fontsize=11,arrowprops={'arrowstyle':'->','color':red})
ax.set_title('BOT BREAKOUT — actual IC Markets H2 candles | replay order submitted at 05:00 UTC',loc='left',fontweight='bold',fontsize=15,pad=17);ax.set_ylabel('GBPCAD bid price');fig.text(.07,.025,'Stop gap: 19.4 pips. This order filled in the zero-cost replay. Earlier 03:00 plan was held by the exposure cap.\nExact correspondence with Bishop’s source entry is unverified. The wider stop is exposed here, not certified as correct.',fontsize=11);fig.subplots_adjust(left=.07,right=.98,top=.91,bottom=.18);fig.savefig(OUT/'breakout_bot.png');plt.close(fig)
fig,axs=plt.subplots(2,1,figsize=(17,18),dpi=160)
for ax,path in zip(axs,('gbpcad_420s.png','breakout_bot.png')):ax.imshow(mi.imread(OUT/path));ax.axis('off')
axs[0].set_title('BISHOP — GBPCAD H2 breakout | original video at 07:00\nDrawn entry 1.86183 • stop 1.86041 • FOREXcom',loc='left',fontsize=16,fontweight='bold',pad=16);fig.suptitle('Breakout confirmation: where the stops are placed',fontsize=23,fontweight='bold',x=.06,ha='left',y=.98);fig.subplots_adjust(left=.045,right=.985,top=.91,bottom=.025,hspace=.09);fig.savefig(OUT/'breakout_comparison.png');plt.close(fig)
bo={'run':40584565827,'setup':s,'order':o,'observation':obs,'source_stop':1.86041,'source_entry':1.86183,'source_pts':420,'trade_identity':'NOT_ESTABLISHED'}
# Standing buy: source-linked clock/pattern, with held status visible.
r,allbs,tick=read(40584728247,'video-t3-usdcad-buy-open','H1')
ss=[s for s in r['setups'] if s['tf']=='H1' and s['model']=='confirmation_standing_extreme' and s['side']=='BUY' and s['clock']['available_at']=='2026-06-12T16:00:00+00:00'];assert {s['stop_ticks'] for s in ss}=={139587};s=min(ss,key=lambda s:s['id']);rej=next(z for z in r['selection']['rejected'] if z['setup_id']==s['id']);assert rej['reason']=='AMBIGUOUS_EXECUTION_PLAN';assert not any(o['setup_id']==s['id'] for o in r['orders'])
a=next(b for b in allbs if b.id==s['details']['reference_bar_id']);b=next(b for b in allbs if b.end==utc(s['clock']['available_at']));assert b.low_ticks<a.low_ticks and a.low_ticks<b.close_ticks<a.high_ticks and b.high_ticks<a.high_ticks
lo=utc('2026-06-12T12:00:00Z');hi=utc('2026-06-12T20:00:00Z');bs=[b for b in allbs if lo<=b.start<hi]
fig,ax=plt.subplots(figsize=(17,8),dpi=160);candles(ax,bs,tick,.65/24);left=md.date2num(lo);right=md.date2num(hi);ax.set_xlim(left-.02,right+5/24);ax.set_ylim(1.39535,1.39985)
ax.axvspan(md.date2num(a.start),md.date2num(a.end),color='#8cb9ee',alpha=.25);ax.axvspan(md.date2num(b.start),md.date2num(b.end),color='#ffcf67',alpha=.35)
line(ax,1.39680,left,right,'BOT PLANNED ENTRY  1.39680',blue)
line(ax,1.39587,left,right,'BOT PROPOSED STOP  1.39587',red,-.00023)
line(ax,1.39589,left,right,'BISHOP FINAL M30 STOP  1.39589',purple,.00025)
ax.hlines(a.high_ticks*tick,md.date2num(a.start),md.date2num(b.end),color=green,ls=':',lw=2)
ax.annotate('Previous HIGH remains unswept\n1.39845 > sweep-candle high 1.39726',xy=(md.date2num(b.start+timedelta(minutes=30)),a.high_ticks*tick),xytext=(left+.01,1.3995),fontsize=11,color=green,arrowprops={'arrowstyle':'->','color':green})
ax.annotate('Previous low 1.39673 swept\nNew low 1.39592; close 1.39711\nback INSIDE previous range',xy=(md.date2num(b.start+timedelta(minutes=30)),b.low_ticks*tick),xytext=(md.date2num(b.end)+.4/24,1.39875),fontsize=11,color=navy,arrowprops={'arrowstyle':'->','color':navy})
ax.set_title('4TH MAN BUY — H1 low swept / high standing | bot plan held, not placed',loc='left',fontsize=15,fontweight='bold',pad=17);ax.set_ylabel('USDCAD bid price');fig.text(.07,.025,'Blue candle = previous candle; yellow = sweep confirmation. Bot stop = 1.39592 low minus 0.00005.\nHeld for conflicting targets (1.39726 versus 1.40240). Bishop’s displayed stop belongs to his additional M30 engulfing entry.',fontsize=11);fig.subplots_adjust(left=.07,right=.98,top=.91,bottom=.18);fig.savefig(OUT/'fourth_man_bot.png');plt.close(fig)
fig=plt.figure(figsize=(20,16),dpi=160);g=fig.add_gridspec(2,2,height_ratios=[.85,1.15],hspace=.08,wspace=.04)
for i,path,title in [(0,'usdcad_1680s.png','BISHOP H1 — low swept, high standing\nOriginal video 28:00; no separate H1 stop box'),(1,'usdcad_1710s.png','BISHOP FINAL ENTRY — additional M30 engulfing\nOriginal video 28:30; stop 1.39589')]:
 ax=fig.add_subplot(g[0,i]);ax.imshow(mi.imread(OUT/path));ax.axis('off');ax.set_title(title,fontsize=14,loc='left',fontweight='bold',pad=15)
ax=fig.add_subplot(g[1,:]);ax.imshow(mi.imread(OUT/'fourth_man_bot.png'));ax.axis('off');fig.suptitle('4th man confirmation: the pattern and stop comparison',fontsize=24,fontweight='bold',x=.045,ha='left',y=.98);fig.subplots_adjust(left=.04,right=.98,top=.88,bottom=.015);fig.savefig(OUT/'fourth_man_comparison.png');plt.close(fig)
standing={'run':40584728247,'setup':s,'selection':rej,'target_variants':sorted({x['target_ticks'] for x in ss}),'previous_candle':{'start':a.start.isoformat(),'high':a.high_ticks,'low':a.low_ticks},'sweep_candle':{'start':b.start.isoformat(),'high':b.high_ticks,'low':b.low_ticks,'close':b.close_ticks},'source_pts':[1680,1710],'source_final_entry':1.39681,'source_final_stop':1.39589,'source_entry_model':'H1_STANDING_CONTEXT_THEN_M30_ENGULF','trade_identity':'NOT_ESTABLISHED','placement':'HELD_NOT_PLACED'}
(OUT/'evidence.json').write_text(json.dumps({'breakout':bo,'fourth_man':standing},indent=2)+'\n')
print('Rendered both comparisons')

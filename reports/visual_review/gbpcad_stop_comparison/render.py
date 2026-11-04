"""Evidence chart: original mentor frame plus actual frozen IC candles; no simulation."""
from pathlib import Path
import json,gzip,hashlib
from datetime import timedelta,timezone
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as md
from matplotlib.patches import Rectangle
import matplotlib.image as mi
from bishop.v2.feed import load_feed
from bishop.v2.aggregation import aggregate
from bishop.v2.types import utc

OUT=Path(__file__).parent
REPORT=Path('reports/implementation_review/primary_video_40531068022/video-t3-gbpcad-buy.json.gz')
doc=json.loads(gzip.decompress(REPORT.read_bytes())); result=doc['result'];plan=doc['plan']
setups=[s for s in result['setups'] if s['tf']=='H2' and s['side']=='BUY' and s['model']=='confirmation_bo' and s['status']=='ELIGIBLE' and s['clock']['available_at'].startswith('2026-06-09')]
assert {s['stop_ticks'] for s in setups}=={185847}
first=min(setups,key=lambda s:(s['clock']['available_at'],s['id']))
assert first['entry_ticks']==186145 and first['clock']['available_at']=='2026-06-09T03:00:00+00:00'
first_order=next(o for o in result['orders'] if o['setup_id']==first['id'])
assert next(o for o in result['observations'] if o['id']==first_order['id'])['outcome']=='EXPIRED'
meta=json.loads(Path(plan['manifest_path']).read_text());feed=load_feed(plan['input_path'],meta,plan['as_of'],plan['history_start'])
bars=aggregate(feed['bars'],'H2',feed['instrument'],plan['as_of'],calendar=meta.get('calendar',meta['calendar_id']))['bars']
lo=utc('2026-06-08T13:00:00Z'); hi=utc('2026-06-09T11:00:00Z')
bs=[b for b in bars if lo<=b.start<hi];tick=float(feed['instrument'].tick_size)
first_take=next(b for b in bs if b.start==utc('2026-06-08T21:00:00Z'))
reaction=next(b for b in bs if b.start==utc('2026-06-08T23:00:00Z'))
confirmation=next(b for b in bs if b.start==utc('2026-06-09T01:00:00Z'))
assert first_take.low_ticks==185852 and reaction.low_ticks==186026 and confirmation.low_ticks==186062
navy='#15334b';red='#c7363e';green='#11846c';blue='#2468b4';purple='#874fa2'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12})
fig,ax=plt.subplots(figsize=(16,8),dpi=160);fig.patch.set_facecolor('white');ax.set_facecolor('#fafcfe')
width=1.30/24
for b in bs:
 x=md.date2num(b.start+timedelta(hours=1));o,h,l,c=[getattr(b,k+'_ticks')*tick for k in ('open','high','low','close')];color=green if c>=o else '#334155'
 ax.vlines(x,l,h,color=color,lw=1.5,zorder=3)
 ax.add_patch(Rectangle((x-width/2,min(o,c)),width,max(abs(c-o),.000025),facecolor=color,edgecolor=color,lw=1,zorder=4))
start=md.date2num(lo)-.7/24; end=md.date2num(hi)+6.5/24; ax.set_xlim(start,end); ax.set_ylim(1.85775,1.8673)
# Show when the example pending order becomes available, without using later candles.
issued=md.date2num(utc(first['clock']['available_at']));ax.axvline(issued,color=blue,lw=1.3,ls=':',zorder=1)
ax.axvspan(issued,md.date2num(hi),color=blue,alpha=.035)
ax.axvspan(md.date2num(confirmation.start),issued,facecolor='#ffcf67',alpha=.22,zorder=1)
line_right=md.date2num(hi)+.35/24
for y,color,style in [(1.85847,red,'-'),(1.86145,blue,'--'),(1.86041,purple,'--')]:ax.hlines(y,start,line_right,color=color,ls=style,lw=1.9,zorder=2)
ax.text(line_right+.2/24,1.85847,'BOT STOP  1.85847\nSame across all 7 H2 candidates',color=red,va='center',fontsize=12,fontweight='bold')
ax.text(line_right+.2/24,1.86145,'BOT LIMIT  1.86145\nFirst candidate, available 03:00 UTC',color=blue,va='center',fontsize=11,fontweight='bold')
ax.text(line_right+.2/24,1.86041,'BISHOP STOP  1.86041\nFOREXcom reference, not an IC fill',color=purple,va='center',fontsize=11,fontweight='bold')
ax.annotate('Earlier liquidity-take low\n1.85852 → bot subtracts 0.00005',xy=(md.date2num(first_take.start+timedelta(hours=1)),1.85852),xytext=(md.date2num(lo)+1/24,1.85794),arrowprops={'arrowstyle':'->','color':red,'lw':1.5},color=red,fontsize=11,va='bottom')
ax.annotate('Later H2 reaction low\n1.86026',xy=(md.date2num(reaction.start+timedelta(hours=1)),1.86026),xytext=(md.date2num(lo)+.6/24,1.86275),arrowprops={'arrowstyle':'->','color':navy,'lw':1.3},color=navy,fontsize=11)
ax.annotate('Bot H2 breakout confirmation\n01:00–03:00 UTC\nCandle low: 1.86062',xy=(md.date2num(confirmation.start+timedelta(hours=1)),confirmation.high_ticks*tick),xytext=(issued-5.8/24,1.8666),arrowprops={'arrowstyle':'->','color':blue,'lw':1.4},color=blue,fontsize=11,va='top')
ax.text(issued+.3/24,1.8667,'Later candles shown for context\nNot available at order placement',fontsize=10,color='#596778',va='top')
ax.xaxis.set_major_locator(md.HourLocator(byhour=[13,17,21,1,5,9],tz=timezone.utc));ax.xaxis.set_major_formatter(md.DateFormatter('%d Jun\n%H:%M UTC',tz=timezone.utc))
ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.5f'));ax.grid(axis='y',color='#e2e8f0',lw=.8,zorder=0)
ax.set_title('BOT — actual IC Markets H2 candles and recorded pending-order plan',loc='left',fontweight='bold',color=navy,pad=17,fontsize=16)
ax.set_ylabel('GBPCAD bid price');[ax.spines[s].set_visible(False) for s in ['top','right']]
fig.text(.08,.02,'Evidence: earliest 9 June H2 breakout candidate. This pending order expired unfilled. Bishop’s exact entry has not been matched.\nPurple line is his original FOREXcom drawing, overlaid only as a price reference; the two feeds are not assumed identical.',fontsize=10,color='#425466')
fig.subplots_adjust(left=.08,right=.98,bottom=.16,top=.90)
fig.savefig(OUT/'bot_h2_actual_candles.png',facecolor='white');plt.close(fig)
# Assemble an evidence report; original source screenshot is displayed intact.
fig=plt.figure(figsize=(16,18),dpi=160,facecolor='white');grid=fig.add_gridspec(2,1,height_ratios=[.98,1.02],hspace=.12)
a=fig.add_subplot(grid[0]);a.imshow(mi.imread(OUT/'bishop_original_420s.png'));a.axis('off');a.set_title('BISHOP — original video at 07:00 | GBPCAD H2, FOREXcom\nDrawn entry 1.86183 • stop 1.86041 • risk 14.2 pips',fontsize=16,fontweight='bold',loc='left',pad=15,color=navy)
a=fig.add_subplot(grid[1]);a.imshow(mi.imread(OUT/'bot_h2_actual_candles.png'));a.axis('off')
fig.suptitle('Confirmation-entry stop comparison',fontsize=22,fontweight='bold',x=.065,ha='left',y=.98,color=navy)
fig.subplots_adjust(left=.055,right=.985,top=.90,bottom=.025);fig.savefig(OUT/'comparison.png',facecolor='white');plt.close(fig)
source_video=Path('/workspace/scratch/DEFI.-.BISHOP.-.STUDY.20.Minute.Series.Part.3.TRADES.BREAKDOWN.BIAS.TO.ENTRY.CASE.STUDY_.GB.mp4')
assert hashlib.sha256(source_video.read_bytes()).hexdigest()=='ee73e7118df31d1f30524a204ffe5393bbfc05b87197f935fe01bd4687d45004'
(OUT/'evidence.json').write_text(json.dumps({'source_video_sha256':hashlib.sha256(source_video.read_bytes()).hexdigest(),'source_pts_seconds':420,'source_chart_tf':'H2','source_chart_venue':'FOREXcom','bishop_drawn_entry':1.86183,'bishop_drawn_stop':1.86041,'bishop_drawn_target':1.87039,'bot_setup_id':first['id'],'bot_available_at':first['clock']['available_at'],'bot_entry_ticks':first['entry_ticks'],'bot_stop_ticks':first['stop_ticks'],'bot_target_ticks':first['target_ticks'],'tick_size':str(feed['instrument'].tick_size),'all_seven_stop_ticks':185847,'source_entry_identity':'NOT_ESTABLISHED','bot_order_status':'EXPIRED_UNFILLED','frozen_report_sha256':hashlib.sha256(REPORT.read_bytes()).hexdigest()},indent=2)+'\n')
print(str((OUT/'comparison.png').resolve()))

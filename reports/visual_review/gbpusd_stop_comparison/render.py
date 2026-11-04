"""Actual-data stop comparison with unaltered firsthand H2 source frame."""
from pathlib import Path
import gzip,json,hashlib
from datetime import timedelta,timezone
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as md
import matplotlib.image as mi
from matplotlib.patches import Rectangle
from bishop.v2.feed import load_feed
from bishop.v2.aggregation import aggregate
from bishop.v2.entries import _engulfs
from bishop.v2.types import utc
OUT=Path(__file__).parent
REPORT=Path('reports/implementation_review/primary_video_40535518232/video-t3-gbpusd-sell-mixed-accounts.json.gz')
doc=json.loads(gzip.decompress(REPORT.read_bytes()));r=doc['result'];p=doc['plan']
ss=[s for s in r['setups'] if s['tf']=='H2' and s['side']=='SELL' and s['status']=='ELIGIBLE' and s['clock']['available_at'].startswith('2026-06-11')]
assert {s['stop_ticks'] for s in ss}=={133923}
early=min((s for s in ss if s['model']=='confirmation_standing_extreme'),key=lambda s:(s['clock']['available_at'],s['id']))
engulf=min((s for s in ss if s['model']=='engulf_av_retest'),key=lambda s:(s['clock']['available_at'],s['id']))
assert engulf['clock']['available_at']=='2026-06-11T15:00:00+00:00' and engulf['entry_ticks']==133613
assert next(z for z in r['selection']['rejected'] if z['setup_id']==engulf['id'])['reason']=='EXPOSURE_CAP'
m=json.loads(Path(p['manifest_path']).read_text());feed=load_feed(p['input_path'],m,p['as_of'],p['history_start']);allbars=aggregate(feed['bars'],'H2',feed['instrument'],p['as_of'],calendar=m.get('calendar',m['calendar_id']))['bars'];tick=float(feed['instrument'].tick_size)
lo=utc('2026-06-10T19:00:00Z');hi=utc('2026-06-11T19:00:00Z');bars=[b for b in allbars if lo<=b.start<hi]
protection=next(b for b in bars if b.id=='bar_d555141c13d14934b69465c4');assert protection.high_ticks==133918
ce=next(b for b in bars if b.start==utc('2026-06-11T13:00:00Z'));prev=next(b for b in bars if b.start==utc('2026-06-11T11:00:00Z'));assert _engulfs(prev,ce,'SELL')
navy='#15334b';red='#c7363e';purple='#874fa2';blue='#2468b4';orange='#ad6400';green='#11846c'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12})
fig,ax=plt.subplots(figsize=(16,8.4),dpi=160,facecolor='white');ax.set_facecolor('#fafcfe');w=1.30/24
for b in bars:
 x=md.date2num(b.start+timedelta(hours=1));o,h,l,c=[getattr(b,k+'_ticks')*tick for k in ('open','high','low','close')];color=green if c>=o else '#334155'
 ax.vlines(x,l,h,color=color,lw=1.5,zorder=3);ax.add_patch(Rectangle((x-w/2,min(o,c)),w,max(abs(c-o),.000025),facecolor=color,edgecolor=color,zorder=4))
start=md.date2num(lo)-.8/24;right=md.date2num(hi)+.25/24;end=right+6.9/24;ax.set_xlim(start,end);ax.set_ylim(1.3319,1.3412)
ax.axvspan(md.date2num(utc('2026-06-11T05:00:00Z')),md.date2num(utc('2026-06-11T07:00:00Z')),color=blue,alpha=.08)
ax.axvspan(md.date2num(ce.start),md.date2num(ce.end),color='#ffcf67',alpha=.28)
ax.axvspan(md.date2num(ce.end),md.date2num(hi),color=orange,alpha=.035)
ax.hlines(1.33925,start,right,color=purple,ls='--',lw=1.5,zorder=2)
ax.hlines(1.33923,start,right,color=red,lw=1.4,zorder=2)
ax.text(right+.3/24,1.33965,'BISHOP STOP  1.33925\nBOT STOP        1.33923\nDifference: 0.2 pip',fontsize=12,color=navy,fontweight='bold',va='center',bbox={'boxstyle':'round,pad=.5','fc':'white','ec':'#cbd5e1'})
ax.annotate('Protective high 1.33918\nBot adds 0.00005 buffer',xy=(md.date2num(protection.start+timedelta(hours=1)),1.33918),xytext=(md.date2num(lo)+.8/24,1.34085),arrowprops={'arrowstyle':'->','color':red,'lw':1.4},color=red,fontsize=11,va='top')
ax.hlines(early['entry_ticks']*tick,md.date2num(utc(early['clock']['available_at'])),right,color=blue,ls='--',lw=1.5)
ax.text(right+.3/24,1.33836,'07:00 BOT CANDIDATE\nStanding-extreme entry 1.33836',fontsize=10.5,color=blue,va='center')
ax.annotate('Earlier 05:00–07:00 candle\nBot labels standing-extreme,\nnot engulfing',xy=(md.date2num(utc('2026-06-11T06:00:00Z')),1.33774),xytext=(md.date2num(lo)+.5/24,1.33365),arrowprops={'arrowstyle':'->','color':blue,'lw':1.3},fontsize=10.5,color=blue)
ax.hlines(engulf['entry_ticks']*tick,md.date2num(ce.end),right,color=orange,ls='--',lw=1.7)
ax.text(right+.3/24,1.33613,'15:00 BOT ENGULF PLAN\nProposed entry 1.33613\nHeld: exposure cap',color=orange,fontsize=11,va='center',fontweight='bold')
ax.annotate('Bot H2 engulfing confirmation\n13:00–15:00 UTC',xy=(md.date2num(ce.start+timedelta(hours=1)),ce.open_ticks*tick),xytext=(md.date2num(ce.start)-2.4/24,1.3407),arrowprops={'arrowstyle':'->','color':orange,'lw':1.4},color=orange,fontsize=11,va='top')
ax.xaxis.set_major_locator(md.HourLocator(byhour=[19,23,3,7,11,15],tz=timezone.utc));ax.xaxis.set_major_formatter(md.DateFormatter('%d Jun\n%H:%M UTC',tz=timezone.utc));ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.5f'));ax.grid(axis='y',color='#e2e8f0',lw=.8);ax.set_ylabel('GBPUSD bid price');ax.set_title('BOT — actual IC Markets H2 candles | recorded candidates, not a matched source entry',loc='left',color=navy,fontweight='bold',fontsize=15,pad=16)
for z in ('top','right'):ax.spines[z].set_visible(False)
fig.text(.08,.025,'The stop levels nearly coincide. The confirmations and entries are not established as the same trade.\nThe later engulfing plan was not placed (exposure cap). Purple is a FOREXcom reference; source and IC candle identity is unverified.',fontsize=10,color='#425466');fig.subplots_adjust(left=.08,right=.98,bottom=.16,top=.91);fig.savefig(OUT/'bot_h2_actual_candles.png',facecolor='white');plt.close(fig)
fig=plt.figure(figsize=(16,18.5),dpi=160,facecolor='white');g=fig.add_gridspec(2,1,height_ratios=[.98,1.02],hspace=.12);a=fig.add_subplot(g[0]);a.imshow(mi.imread(OUT/'bishop_original_1350s.png'));a.axis('off');a.set_title('BISHOP — original video at 22:30 | GBPUSD H2, FOREXcom\nDrawn sell entry 1.33793 • stop 1.33925 • risk 13.2 pips',loc='left',pad=15,fontweight='bold',fontsize=15,color=navy);a=fig.add_subplot(g[1]);a.imshow(mi.imread(OUT/'bot_h2_actual_candles.png'));a.axis('off');fig.suptitle('Second example: GBPUSD H2 sell',fontsize=22,fontweight='bold',color=navy,x=.065,ha='left',y=.98);fig.subplots_adjust(left=.055,right=.985,top=.90,bottom=.025);fig.savefig(OUT/'comparison.png',facecolor='white');plt.close(fig)
(OUT/'evidence.json').write_text(json.dumps({'source_pts_seconds':1350,'source_video_sha256':'ee73e7118df31d1f30524a204ffe5393bbfc05b87197f935fe01bd4687d45004','source_entry':1.33793,'source_stop':1.33925,'source_target':1.33308,'bot_stop':1.33923,'difference_pips':.2,'bot_engulf_setup_id':engulf['id'],'bot_engulf_available_at':engulf['clock']['available_at'],'bot_engulf_entry':1.33613,'bot_engulf_order_status':'HELD_EXPOSURE_CAP','earlier_bot_candidate_model':early['model'],'earlier_bot_entry':early['entry_ticks']*tick,'source_trade_identity':'NOT_ESTABLISHED','frozen_report_sha256':hashlib.sha256(REPORT.read_bytes()).hexdigest()},indent=2)+'\n')
print((OUT/'comparison.png').resolve())

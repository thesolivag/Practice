"""Render exact broken-A reference and later limit fill from frozen CI output."""
from pathlib import Path
import gzip,json
from datetime import timedelta,timezone
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as md
from matplotlib.patches import Rectangle
from bishop.v2.feed import load_feed
from bishop.v2.aggregation import aggregate
from bishop.v2.types import utc
OUT=Path(__file__).parent
z=json.load(gzip.open('reports/implementation_review/primary_video_40586614121/video-t3-gbpcad-buy.json.gz'));r=z['result'];p=z['plan']
o=min((o for o in r['orders'] if o['tf']=='H2' and o['model']=='confirmation_bo' and o['clock']['available_at'].startswith('2026-06-09')),key=lambda o:(o['clock']['available_at'],o['id']))
s=next(s for s in r['setups'] if s['id']==o['setup_id']);d=r['diagnostics']['structures']['H2'];level=next(l for l in d['levels'] if l['id']==s['level_id']);e=next(e for e in d['events'] if e['id']==s['details']['breakout_event_id']);obs=next(x for x in r['observations'] if x['id']==o['id'])
assert level['kind']=='A' and level['side']=='SELL' and o['entry_ticks']==level['price_ticks']==e['price_ticks']==186179
assert level['details']['turn_id']==e['reference_id'] and o['kind']=='LIMIT'
assert o['clock']['available_at']=='2026-06-09T05:00:00+00:00' and obs['fill_window']['start']=='2026-06-09T06:05:00+00:00'
m=json.load(open(p['manifest_path']));f=load_feed(p['input_path'],m,p['as_of'],p['history_start']);allbs=aggregate(f['bars'],'H2',f['instrument'],p['as_of'],calendar=m['calendar_id'])['bars'];tick=float(f['instrument'].tick_size)
lo=utc('2026-06-08T15:00:00Z');hi=utc('2026-06-09T09:00:00Z');bs=[b for b in allbs if lo<=b.start<hi]
fig,ax=plt.subplots(figsize=(17,9),dpi=160);left=md.date2num(lo);right=md.date2num(hi)
for b in bs:
 x=md.date2num(b.start+timedelta(hours=1));op,h,l,c=[getattr(b,k+'_ticks')*tick for k in ('open','high','low','close')];col='#13856e' if c>=op else '#3c4b60'
 ax.vlines(x,l,h,color=col,lw=1.5);ax.add_patch(Rectangle((x-.65/24,min(op,c)),1.3/24,max(abs(c-op),.00001),color=col))
ax.set_xlim(left-.04,right+7/24);ax.set_ylim(1.8579,1.8663)
for price,color,style,text,offset in [(1.86179,'#2369b0','-','CORRECTED BUY LIMIT  1.86179\nExact broken A, now support',-.00015),(1.86183,'#864e9e','--','BISHOP DRAWN ENTRY  1.86183',.00065),(1.86271,'#7c8796',':','OLD WRONG ENTRY  1.86271',.00035),(1.85847,'#c7353d','--','BREAKOUT STOP  1.85847\nOwner confirmed logical',0),(1.86041,'#864e9e',':','BISHOP STOP  1.86041',-.0001)]:
 ax.hlines(price,left,right,color=color,ls=style,lw=1.8);ax.annotate(text,xy=(right,price),xytext=(right+.35/24,price+offset),color=color,fontsize=11,fontweight='bold',va='center',arrowprops={'arrowstyle':'-','color':color})
ce=next(b for b in bs if b.end==utc(o['clock']['available_at']));ax.axvspan(md.date2num(ce.start),md.date2num(ce.end),color='#ffcf67',alpha=.28)
ax.annotate('Breakout CLOSE confirms\nA changes from SELL to BUY\nOrder waits at the A-level',xy=(md.date2num(ce.end),1.86179),xytext=(left+.01,1.86595),va='top',fontsize=12,color='#17344d',arrowprops={'arrowstyle':'->','color':'#17344d'})
mid=utc(obs['fill_window']['start'])+timedelta(minutes=2,seconds=30);ax.plot(md.date2num(mid),1.86179,'o',color='#2369b0',ms=7,zorder=6)
ax.annotate('LATER RETEST FILL\n06:05–06:10 UTC',xy=(md.date2num(mid),1.86179),xytext=(md.date2num(ce.end)-.2/24,1.85955),fontsize=12,color='#2369b0',arrowprops={'arrowstyle':'->','color':'#2369b0'})
ax.xaxis.set_major_locator(md.HourLocator(interval=2,tz=timezone.utc));ax.xaxis.set_major_formatter(md.DateFormatter('%d Jun\n%H:%M UTC',tz=timezone.utc));ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.5f'));ax.grid(axis='y',alpha=.2);ax.set_ylabel('GBPCAD bid price');ax.set_title('Breakout entry corrected: wait for the broken A-level retest',fontsize=19,fontweight='bold',loc='left',pad=22)
fig.text(.07,.025,'Actual IC Markets H2 candles; fill established by frozen M5 replay. Source drawing is a FOREXcom price reference.\nEntry gap is now 0.4 pip; exact source trade equivalence is unverified. Owner confirmed the deeper breakout stop as logical; Bishop used a different protection reference in this case.',fontsize=11);fig.subplots_adjust(left=.07,right=.98,top=.89,bottom=.17);fig.savefig(OUT/'comparison.png');plt.close(fig)
(OUT/'evidence.json').write_text(json.dumps({'run':40586614121,'setup':s,'order':o,'observation':obs,'broken_A':level,'breakout_event':e,'source_entry':1.86183,'source_stop':1.86041,'source_pts':420,'entry_difference_pips':.4,'stop_difference_pips':19.4,'teacher_acceptance':'NOT_ESTABLISHED','owner_stop_review':{'status':'LOGICAL_BREAKOUT_STOP_CONFIRMED','numeric_gap_is_engine_defect':False,'source_engulf_stop_rationale':'OWNER_INTERPRETATION_FOR_THIS_TRADE','universal_engulf_stop_rule':False}},indent=2)+'\n')

"""Plot actual candles against the saved engine reading; never infer missing targets."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from bishop.v2.feed import load_feed
from bishop.v2.aggregation import aggregate
from bishop.v2.types import utc
from bishop.bias_snapshot import snapshot


def render(acquisition,engine_path,out):
    a=json.loads(Path(acquisition).read_text());engine=json.loads(Path(engine_path).read_text())
    manifest=json.loads(Path(a['manifest']).read_text())
    feed=load_feed(a['path'],manifest,engine['as_of'])
    if feed['hashes']['sha256']!=engine['input']['sha256']:
        raise ValueError('Chart candles must match the engine input hash')
    if manifest['symbol']!=engine['instrument']['symbol'] or utc(a['as_of'])!=utc(engine['as_of']):
        raise ValueError('Chart instrument and assessment clock must match')
    tick=float(feed['instrument'].tick_size)
    confirmed=engine.get('story_context_evaluated') is True
    readings={row['tf']:row for row in snapshot(engine)['rows']}
    fig,axes=plt.subplots(3,1,figsize=(13,13),dpi=150)
    fig.patch.set_facecolor('#f4f7fb');evidence=[]
    for ax,tf,count in zip(axes,('W','D','H4'),(26,55,55)):
        bars=aggregate(feed['bars'],tf,feed['instrument'],engine['as_of'],calendar=manifest.get('calendar',manifest['calendar_id']))['bars'][-count:]
        ctx=engine.get('structural_context',{}).get(tf,{})
        row=readings.get(tf,{}) if confirmed else ctx
        side=row.get('side');state=row.get('state','UNAVAILABLE')
        selected_stories=[story for story in engine.get('stories',[]) if story['origin_tf']==tf]
        reaction_ids={story['origin_id'] for story in selected_stories}
        reaction_ids.update(event['reference_id'] for event in row.get('waiting_external_break',[]) if event.get('reference_id'))
        reactions=[event for event in engine.get('story_reactions',[]) if event['id'] in reaction_ids]
        color='#087e70' if side=='BUY' else '#bd4654' if side=='SELL' else '#62748a'
        ax.set_facecolor('white');ax.grid(axis='y',color='#e6ebf2',lw=.7)
        for i,b in enumerate(bars):
            op,hi,lo,cl=(v*tick for v in (b.open_ticks,b.high_ticks,b.low_ticks,b.close_ticks))
            c='#119487' if cl>=op else '#cd6571'
            ax.vlines(i,lo,hi,color=c,lw=1)
            ax.add_patch(Rectangle((i-.29,min(op,cl)),.58,max(abs(cl-op),tick),facecolor=c,edgecolor=c))
        events=reactions if confirmed else ctx.get('recent_breaks',[])
        references={e['price_ticks'] for e in events if e.get('price_ticks') is not None}
        for price in sorted(references):
            ax.axhline(price*tick,color=color,ls='--',lw=1.2)
            ax.text(1.005,price*tick,f"{'Rejection level' if confirmed else 'Break reference'} {price*tick:.5f}",transform=ax.get_yaxis_transform(),color=color,va='center',fontsize=8)
        event_bars={ident for e in events for ident in e.get('bar_ids',[])}
        for i,b in enumerate(bars):
            if b.id in event_bars:
                ax.scatter(i,b.close_ticks*tick,s=65,facecolors='none',edgecolors='#d08a00',linewidths=2,zorder=5)
        roots=[] if confirmed else [r for r in ctx.get('active_root_ranges',[]) if r.get('side')==side]
        frozen={(story['details'].get('frozen_external_reference_ticks'),story['confirmation_tf']) for story in selected_stories}
        frozen.update((event.get('price_ticks'),event.get('details',{}).get('confirmation_tf','lower TF')) for event in engine.get('story_events',[]) if event['kind']=='BIAS_REFERENCE_FROZEN' and event.get('details',{}).get('reaction_id') in reaction_ids)
        for price,reference_tf in sorted((price,frame) for price,frame in frozen if price is not None):
            ax.axhline(price*tick,color='#8a6aaf',ls='-.',lw=1)
            ax.text(1.005,price*tick,f'{reference_tf} frozen A/V {price*tick:.5f}',transform=ax.get_yaxis_transform(),fontsize=8,color='#8a6aaf',va='center')
        # Only a uniquely identified same-direction origin can be shown.
        origin=roots[0]['origin_ticks'] if len(roots)==1 else None
        if origin is not None and bars and min(b.low_ticks for b in bars)<=origin<=max(b.high_ticks for b in bars):
            ax.axhline(origin*tick,color='#8a6aaf',ls=':',lw=1)
            ax.text(1.005,origin*tick,f'Range origin {origin*tick:.5f}',transform=ax.get_yaxis_transform(),fontsize=8,color='#8a6aaf',va='center')
        elif origin is not None:
            ax.text(.01,.035,f'Protected range origin {origin*tick:.5f} is outside this view',transform=ax.transAxes,fontsize=8,color='#8a6aaf')
        title={'BUY':'BUY / bullish','SELL':'SELL / bearish'}.get(side,state.replace('_',' '))
        ax.set_title(f'{tf}  |  {title}',loc='left',color=color,fontsize=14,fontweight='bold',pad=10)
        when=max((story['clock']['available_at'] for story in selected_stories),default=None) if confirmed else ctx.get('available_at')
        kind=('Rejection + external confirmation' if selected_stories else 'Waiting for confirmed bias') if confirmed else (' / '.join(sorted({e['kind'] for e in events})) or 'No confirmed structural break')
        ax.text(.01,.97,f'{kind}'+(f" · known {when[:16].replace('T',' ')} UTC" if when else ''),transform=ax.transAxes,va='top',fontsize=8,color='#526174',bbox={'facecolor':'white','edgecolor':'none','alpha':.9})
        if bars:
            ticks=sorted({round(i*(len(bars)-1)/5) for i in range(6)})
            ax.set_xticks(ticks,[bars[i].start.strftime('%d %b\n%H:%M') for i in ticks],fontsize=8)
            ax.set_xlim(-1,len(bars))
        ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.5f'))
        ax.tick_params(axis='y',labelsize=8)
        for spine in ax.spines.values():spine.set_color('#dce3ed')
        evidence.append({'tf':tf,'state':state,'side':side,'reference_ticks':sorted(references),'range_origin_ticks':origin,'events':events,'confirmed_stories':selected_stories,'basis':row.get('basis','SAME_TIMEFRAME_STRUCTURE'),'current_segment':ctx.get('current_segment'), 'bars':[{'id':b.id,'start':b.start.isoformat(),'open_ticks':b.open_ticks,'high_ticks':b.high_ticks,'low_ticks':b.low_ticks,'close_ticks':b.close_ticks} for b in bars]})
    pair=manifest['symbol'];stamp=utc(engine['as_of']).strftime('%d %b %Y, %H:%M UTC')
    fig.suptitle(f'{pair} — {"confirmed bias" if confirmed else "structural direction"} on actual IC Markets candles\nAssessment: {stamp}',x=.07,ha='left',fontsize=17,fontweight='bold',color='#182b43')
    fig.text(.07,.025,('Confirmed bias: rejection level + frozen lower-timeframe A/V break. Orange circles: rejection candles.\nPurple: frozen confirmation reference. No direction is forced when the evidence conflicts.\nLiquidity targets are not selected by this bias-only scan.' if confirmed else 'Orange circles: engine break candles. Dashed lines: the exact references used.\nThese are separate timeframe readings, not an entry signal or verified mentor match.\nRange origin is not a trade stop. Liquidity targets are not selected by this bias-only scan.'),fontsize=9,color='#526174')
    fig.subplots_adjust(left=.07,right=.81,top=.91,bottom=.105,hspace=.39)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    fig.savefig(out/f'{pair}-bias.png');plt.close(fig)
    record={'instrument':pair,'as_of':engine['as_of'],'source':'ICMARKETS','input_sha256':feed['hashes']['sha256'],'engine_run_id':engine['run_id'],'historical_coverage':engine['coverage']['base'],'timeframes':evidence,'liquidity_target':'NOT_SELECTED_BIAS_ONLY','teacher_acceptance':'NOT_ESTABLISHED'}
    (out/f'{pair}-bias-evidence.json').write_text(json.dumps(record,indent=2)+'\n')
    return str(out/f'{pair}-bias.png')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--acquisition',required=True);p.add_argument('--engine',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();print(render(args.acquisition,args.engine,args.out))

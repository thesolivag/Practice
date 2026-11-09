/* Frozen research review. No order placement or live-account requests. */
window.BishopReview = (() => {
  const names={standalone:'Original Bishop · nearby',kk_aligned:'Kevin-aligned · nearby',kk_aligned_RR:'Kevin-aligned · 1R / 2R / 3R',recognition_RR:'Recognition flow · 1R / 2R / 3R'};
  const tfs=['H1','H2','H3','H4','D','W'];
  let api,root,offset=0,selected=null,clock=0,panels=[],generation=0,catalogVersion=0,ready=false;
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const stamp=x=>new Date(x*1000).toISOString().replace('T',' ').replace('.000Z',' UTC');
  const epoch=x=>Math.floor(Date.parse(x)/1000);
  const price=x=>Number(x).toFixed(Math.max(0,Math.round(-Math.log10(selected.tick_size))));
  const select=(label,items)=>{const wrap=el('label',label+' '),s=el('select');items.forEach(([v,n])=>s.add(new Option(n,v)));wrap.append(s);return [wrap,s];};
  function button(label,fn){const b=el('button',label);b.type='button';b.onclick=()=>Promise.resolve().then(fn).catch(error);return b;}
  function error(e){root.querySelector('.review-status').textContent=e.message;}
  async function open(fn){api=fn;if(ready)return;ready=true;root=document.getElementById('review-root');
    root.append(el('p','Browse frozen research setups. Drag to move through history; pinch or scroll to zoom. All times are UTC.','muted'));
    const filters=el('div',undefined,'review-controls');root.append(filters);
    for(const [id,label] of [['pair','Market'],['strategy','Strategy'],['confirmation','Confirmation']]){const [w,s]=select(label,[['','All']]);s.id='review-'+id;s.onchange=()=>{offset=0;catalog().catch(error);};filters.append(w);}
    root.append(el('p','','review-status'));const list=el('select');list.id='review-setups';list.size=5;list.setAttribute('aria-label','Saved setups');list.onchange=()=>choose(list.value).catch(error);root.append(list);
    const paging=el('div',undefined,'review-controls');paging.append(button('Previous setups',()=>{offset=Math.max(0,offset-40);return catalog();}),button('More setups',()=>{if(offset+40<Number(list.dataset.total))offset+=40;return catalog();}));root.append(paging,el('div',undefined,'review-detail'));
    try { await catalog(); } catch(e) { ready=false;root.replaceChildren();throw e; }
  }
  async function catalog(){const version=++catalogVersion;const q=new URLSearchParams({offset:String(offset)});for(const k of ['pair','strategy','confirmation'])q.set(k,document.getElementById('review-'+k).value);const d=await api('/api/research-review?'+q);if(version!==catalogVersion)return;
    for(const [key,values] of [['pair',d.pairs],['strategy',d.strategies],['confirmation',d.confirmations]]){const s=document.getElementById('review-'+key);if(s.options.length===1)values.forEach(v=>s.add(new Option(names[v]||v,v)));}
    root.querySelector('.review-status').textContent=`${d.total} setups · ${d.notice}`;
    const list=document.getElementById('review-setups');list.replaceChildren();list.dataset.total=d.total;
    d.entries.forEach(e=>list.add(new Option(`${e.highlight?'★ ':''}${e.pair} ${e.side} · ${e.confirmation} ${e.tf} · ${e.decision.slice(0,16).replace('T',' ')} · ${names[e.strategy]||e.strategy}`,e.id)));
    if(d.entries.length){list.value=d.entries[0].id;await choose(list.value);}else{generation++;panels.forEach(p=>p.chart.remove());panels=[];selected=null;root.querySelector('.review-detail').textContent='No setups match these filters.';}
  }
  async function choose(id){const version=++generation;const e=await api('/api/research-review/'+encodeURIComponent(id));if(version!==generation)return;selected=e;clock=epoch(e.decision);panels.forEach(p=>p.chart.remove());panels=[];const detail=root.querySelector('.review-detail');detail.replaceChildren();
    detail.append(el('h3',`${e.pair} ${e.side} · ${e.confirmation} · ${names[e.strategy]||e.strategy}`),el('p',`${e.kind} entry ${price(e.entry)} · SL ${price(e.stop)} · ${e.targets.map(t=>t.label+' '+price(t.price)).join(' · ')}`));
    detail.append(el('p',e.flow?'★ Audited bot sequence. These markings are the model’s saved/reconstructed evidence, not Bishop’s original drawings.':'H4 sequence was not retained for this setup. Entry, stop and target values are recorded; no liquidity candle has been guessed.','muted'));
    if(e.bias)detail.append(el('p',`Reconstructed bias: ${e.bias.timeframe} ${e.bias.side} · confirmed ${e.bias.confirmed_at}`));
    const controls=el('div',undefined,'review-controls');controls.append(button('Reset to decision',()=>advance(epoch(e.decision),true)),button('+1 hour',()=>advance(clock+3600)),button('+4 hours',()=>advance(clock+14400)),button('+1 day',()=>advance(clock+86400)),button('+7 days',()=>advance(clock+604800)));
    const reveal=button('Reveal corrected outcomes',async()=>{const r=await api('/api/research-review/'+encodeURIComponent(e.id)+'?reveal=true');if(version!==generation)return;outcome.textContent=r.targets.map(t=>`${t.label}: ${t.result.outcome} · ${t.result.gross_R||'unresolved'} gross R · observed ${t.result.observed_at||'not recorded'} · fill window ${t.result.fill_start||'unknown'} — ${t.result.fill_end||'unknown'}`).join('\n');reveal.disabled=true;});controls.append(reveal);detail.append(controls,el('p','','review-clock'));const outcome=el('p','Outcomes hidden. Revealing results does not move the chart clock.','review-outcomes');detail.append(outcome);
    detail.append(el('p','Lines show the setup levels known at the decision time. Price bars stop at the review clock; incomplete candles are omitted. H1 history cannot show the exact ordering of events within one minute.','muted'));
    const grid=el('div',undefined,'review-charts');detail.append(grid);panel(grid,'H4 context','H4',version);panel(grid,'Entry view',e.tf,version);
    if(e.flow){const legend=el('ol',undefined,'review-legend');e.flow.timeline.forEach(t=>legend.append(el('li',t.stage.replaceAll('_',' ')+' · '+t.at.replace('T',' ').replace('+00:00',' UTC'))));legend.append(el('li','ENTRY PLAN · '+e.decision.replace('T',' ')));detail.append(legend);const evidence=el('details'),summary=el('summary','Recorded sequence and evidence');evidence.append(summary);const pre=el('pre',JSON.stringify(e.flow,null,2));evidence.append(pre);detail.append(evidence);}
    if(e.stop_proof){const proof=el('details'),s=el('summary','Logical stop evidence');proof.append(s,el('pre',JSON.stringify(e.stop_proof,null,2)));detail.append(proof);}
    await advance(clock,true);
  }
  function panel(parent,title,tf,version){const box=el('div',undefined,'review-panel');box.append(el('h4',title));const controls=el('div',undefined,'review-controls');const [wrap,s]=select('Timeframe',tfs.map(t=>[t,t==='D'?'Daily':t==='W'?'Weekly':t]));s.value=tf;controls.append(wrap);box.append(controls);const quote=el('div','Move the crosshair over a candle for OHLC.','review-quote');box.append(quote);const canvas=el('div',undefined,'review-canvas');box.append(canvas);parent.append(box);
    const chart=LightweightCharts.createChart(canvas,{autoSize:true,height:380,layout:{background:{color:'#101923'},textColor:'#d6e2ef'},grid:{vertLines:{color:'#202d3b'},horzLines:{color:'#202d3b'}},timeScale:{timeVisible:true,secondsVisible:false,rightOffset:8},localization:{timeFormatter:stamp},handleScroll:true,handleScale:true});
    const series=chart.addSeries(LightweightCharts.CandlestickSeries,{upColor:'#32bd9b',downColor:'#ee7183',wickUpColor:'#32bd9b',wickDownColor:'#ee7183',borderVisible:false,priceFormat:{type:'price',precision:Math.max(0,Math.round(-Math.log10(selected.tick_size))),minMove:selected.tick_size}});
    const p={context:title==='H4 context',chart,series,select:s,bars:[],lines:[],markers:null,version,busy:false,more:true};panels.push(p);
    controls.append(button('Load earlier candles',()=>load(p,true)),button('Fit candles',()=>chart.timeScale().fitContent()));s.onchange=()=>load(p,false).catch(error);
    chart.subscribeCrosshairMove(param=>{const b=param.seriesData.get(series);if(b)quote.textContent=`${stamp(b.time)} · O ${b.open} H ${b.high} L ${b.low} C ${b.close}`;});
    const full=button('Expand chart',()=>{box.classList.toggle('review-expanded');full.textContent=box.classList.contains('review-expanded')?'Close expanded view':'Expand chart';});controls.append(full);
  }
  async function advance(next,reset=false){if(!selected)return;clock=Math.min(next,epoch(selected.cutoff));root.querySelector('.review-clock').textContent=`Review clock: ${stamp(clock)}${clock===epoch(selected.decision)?' · decision time':''}`;if(reset){root.querySelector('.review-outcomes').textContent='Outcomes hidden. Revealing results does not move the chart clock.';const buttons=root.querySelectorAll('.review-detail > .review-controls button');buttons[buttons.length-1].disabled=false;}await Promise.all(panels.map(p=>load(p,false)));}
  async function load(p,older){if(p.version!==generation)return;const request=(p.request||0)+1;p.request=request;const key=selected.id,tf=p.select.value;const q=new URLSearchParams({tf,as_of:String(clock),limit:'300'});if(older&&p.bars.length)q.set('before',p.bars[0].time);const d=await api(`/api/research-review/${encodeURIComponent(key)}/candles?${q}`);if(p.version!==generation||p.request!==request)return;
    const range=p.chart.timeScale().getVisibleLogicalRange();const count=d.candles.length;p.bars=older?[...d.candles,...p.bars]:d.candles;p.more=d.has_more;p.series.setData(p.bars);decorate(p);
    if(older&&range)p.chart.timeScale().setVisibleLogicalRange({from:range.from+count,to:range.to+count});else p.chart.timeScale().setVisibleLogicalRange({from:Math.max(0,p.bars.length-85),to:p.bars.length+5});
    const b=p.select.closest('.review-controls').querySelector('button');b.disabled=!d.has_more;b.textContent=d.has_more?'Load earlier candles':'Start of saved history';
  }
  function decorate(p){p.lines.forEach(l=>p.series.removePriceLine(l));p.lines=[];const e=selected;const line=(price,title,color)=>{if(Number.isFinite(price))p.lines.push(p.series.createPriceLine({price,title,color,lineWidth:1,lineStyle:2,axisLabelVisible:true}));};if(!p.context||!e.flow){line(e.entry,'Entry','#73baff');line(e.stop,'SL','#ff7085');e.targets.forEach(t=>line(t.price,t.label,'#42d6ae'));}
    const f=e.flow;let events=[{at:e.decision,stage:'ENTRY PLAN'}];if(f){if(p.context){line(f.break.level_ticks*e.tick_size,'H4 break level','#cdb0ff');line(f.pool.price_ticks*e.tick_size,'Single-candle liquidity','#ffc46b');line(f.level.price_ticks*e.tick_size,'Reaction key level','#fff099');}events=[...f.timeline,...events];}
    const markers=[];for(const [index,event] of events.entries()){const at=epoch(event.at);if(at>clock)continue;const b=p.bars.findLast(b=>b.time<at);if(!b||at>b.end+7*86400)continue;markers.push({time:b.time,position:'aboveBar',color:'#ffc46b',shape:'circle',text:String(index+1)});}
    markers.sort((a,b)=>a.time-b.time);const grouped=[];for(const m of markers){const last=grouped[grouped.length-1];if(last&&last.time===m.time)last.text+=','+m.text;else grouped.push(m);}if(p.markers)p.markers.setMarkers(grouped);else p.markers=LightweightCharts.createSeriesMarkers(p.series,grouped);
  }
  return {open};
})();

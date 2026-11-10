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
    root.append(button('My setup reports',savedReports),el('div',undefined,'review-saved-reports'));
    root.append(el('p','','review-status'));const list=el('select');list.id='review-setups';list.size=5;list.setAttribute('aria-label','Saved setups');list.onchange=()=>choose(list.value).catch(error);root.append(list);
    const paging=el('div',undefined,'review-controls');paging.append(button('Previous setups',()=>{offset=Math.max(0,offset-40);return catalog();}),button('More setups',()=>{if(offset+40<Number(list.dataset.total))offset+=40;return catalog();}));root.append(paging,el('div',undefined,'review-detail'));
    try { await catalog(); } catch(e) { ready=false;root.replaceChildren();throw e; }
  }
  async function catalog(){const version=++catalogVersion;const q=new URLSearchParams({offset:String(offset)});for(const k of ['pair','strategy','confirmation'])q.set(k,document.getElementById('review-'+k).value);const d=await api('/api/research-review?'+q);if(version!==catalogVersion)return;
    for(const [key,values] of [['pair',d.pairs],['strategy',d.strategies],['confirmation',d.confirmations]]){const s=document.getElementById('review-'+key);if(s.options.length===1)values.forEach(v=>s.add(new Option(names[v]||v,v)));}
    root.querySelector('.review-status').textContent=`${d.total} setups · ${d.notice}`;
    const list=document.getElementById('review-setups');list.replaceChildren();list.dataset.total=d.total;
    d.entries.forEach(e=>list.add(new Option(`${e.highlight?'★ ':''}${e.pair} ${e.side} · ${e.confirmation}${e.entry_reference?.kind?' ('+e.entry_reference.kind+' entry)':''} ${e.tf} · ${e.decision.slice(0,16).replace('T',' ')} · ${names[e.strategy]||e.strategy}`,e.id)));
    if(d.entries.length){list.value=d.entries[0].id;await choose(list.value);}else{generation++;panels.forEach(p=>p.chart.remove());panels=[];selected=null;root.querySelector('.review-detail').textContent='No setups match these filters.';}
  }
  async function reportForm(parent,e,version){
    const box=el('details',undefined,'review-report'),title=el('summary','Report / review this setup');box.append(title);
    box.append(el('p','Mark what looks right or wrong. Your report is saved to your account and does not change the trade result.'));
    const fields=el('div',undefined,'review-report-fields'),inputs={};
    for(const [key,label] of [['whole_setup','Whole setup'],['bias','Bias / direction'],['h4_break','H4 breakout'],['liquidity','Single-candle liquidity'],['key_level_reaction','Key level / rejection'],['confirmation','Confirmation'],['entry','Entry'],['stop_loss','Stop loss'],['target','Target']]){
      const [w,s]=select(label,[['not_reviewed','Not reviewed'],['correct','Correct'],['wrong','Wrong'],['unsure','Unsure']]);s.name=key;inputs[key]=s;fields.append(w);
    }
    box.append(fields);
    const noteLabel=el('label','What looks right or wrong?'),notes=el('textarea');notes.name='report_notes';notes.rows=4;notes.maxLength=4000;noteLabel.append(notes);
    const expectedLabel=el('label','What should the model have done instead? (Optional)'),expected=el('textarea');expected.name='report_expected';expected.rows=3;expected.maxLength=4000;expectedLabel.append(expected);
    box.append(noteLabel,expectedLabel);
    const status=el('p','Loading your saved report…','review-report-status');status.setAttribute('role','status');
    const save=button('Save setup report',async()=>{
      save.disabled=true;status.textContent='Saving…';
      try {const body={assessments:Object.fromEntries(Object.entries(inputs).map(([k,s])=>[k,s.value])),notes:notes.value,expected:expected.value,review_clock:clock,context_tf:panels[0].select.value,entry_tf:panels[1].select.value,outcomes_revealed:!!e.revealedTargets};
        const r=await api('/api/research-reports/'+encodeURIComponent(e.id),{method:'PUT',body:JSON.stringify(body)});status.textContent='Saved to your account · '+stamp(r.updated_at);title.textContent='Review saved — edit report';
      } catch(err){status.textContent='Not saved: '+err.message;}finally{save.disabled=false;}
    });save.disabled=true;box.append(save,status);parent.insertBefore(box,parent.querySelector('.review-controls'));
    try {const saved=await api('/api/research-reports/'+encodeURIComponent(e.id));if(version!==generation)return;
      if(saved){for(const [k,s] of Object.entries(inputs))s.value=saved.report.assessments[k]||'not_reviewed';notes.value=saved.report.notes||'';expected.value=saved.report.expected||'';status.textContent='Saved report · '+stamp(saved.updated_at);title.textContent='Review saved — edit report';box.append(button('Restore saved chart view',async()=>{panels[0].select.value=saved.report.context_tf;panels[1].select.value=saved.report.entry_tf;await advance(saved.report.review_clock,true);}));}
      else status.textContent='No report saved for this setup yet.';
      save.disabled=false;
    } catch(err){status.textContent='Could not load your report: '+err.message+' Reopen this setup to retry.';}
  }
  async function savedReports(){
    const area=root.querySelector('.review-saved-reports');area.replaceChildren(el('p','Loading your reports…'));
    const d=await api('/api/research-reports');area.replaceChildren();
    if(!d.reports.length){area.append(el('p','No saved reports yet. Open a setup and choose Report / review this setup.'));return;}
    const [wrap,s]=select('Your saved reports',d.reports.map(r=>[r.setup_id,`${r.report.setup.pair} · ${r.report.setup.confirmation} · ${r.report.setup.decision.slice(0,16)} · ${names[r.report.setup.strategy]||r.report.setup.strategy}`]));
    area.append(wrap,button('Open reported setup',()=>choose(s.value)),button('Export my reports',async()=>{
      const latest=await api('/api/research-reports');
      const url=URL.createObjectURL(new Blob([JSON.stringify(latest,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download='my-setup-reports.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }),el('p',`${d.reports.length} saved reports. Export the file when you want to share the feedback for investigation.`));
  }

  async function choose(id){const version=++generation;const e=await api('/api/research-review/'+encodeURIComponent(id));if(version!==generation)return;selected=e;clock=epoch(e.decision);panels.forEach(p=>p.chart.remove());panels=[];const detail=root.querySelector('.review-detail');detail.replaceChildren();
    detail.append(el('h3',`${e.pair} ${e.side} · ${e.confirmation} · ${names[e.strategy]||e.strategy}`),el('p',`${e.kind} entry ${price(e.entry)} · SL ${price(e.stop)} · ${e.targets.map(t=>t.label+' '+price(t.price)).join(' · ')}`));
    if(e.entry_reference?.kind){const ref=e.entry_reference;detail.append(el('p',`Entry reference: ${ref.kind==='OC'?'engulfed open-close (OC)':'A/V retest'} · ${price(e.entry)}`));
      detail.append(el('p',ref.pattern_link==='OC_CROSS_WITHOUT_SAVED_ADJACENT_ENGULF_PAIR'?'This OC-cross route has no saved adjacent engulf-pair proof. It is not automatically the two-candle OC junction you described.':'Reference alternatives below are matched to the same recorded confirmation and context.','muted'));
      const refs=el('ul');(ref.alternatives||[]).forEach(a=>refs.append(el('li',`${a.kind==='OC'?'Open-close':'A/V'} level: ${price(a.price)}${Math.abs(a.price-e.entry)<e.tick_size/2?' · this entry':''}`)));detail.append(refs);
      if(new Set((ref.alternatives||[]).map(a=>a.kind)).size<2)detail.append(el('p','A second eligible reference was not retained in this matched archive group. This does not establish that it was ineligible.','muted'));
    }
    detail.append(el('p',e.flow?'★ Audited bot sequence. These markings are the model’s saved/reconstructed evidence, not Bishop’s original drawings.':'H4 sequence was not retained for this setup. Entry, stop and target values are recorded; no liquidity candle has been guessed.','muted'));
    if(e.bias)detail.append(el('p',`Reconstructed bias: ${e.bias.timeframe} ${e.bias.side} · confirmed ${e.bias.confirmed_at}`));
    const controls=el('div',undefined,'review-controls');controls.append(button('Reset to decision',()=>advance(epoch(e.decision),true)),button('+1 hour',()=>advance(clock+3600)),button('+4 hours',()=>advance(clock+14400)),button('+1 day',()=>advance(clock+86400)),button('+7 days',()=>advance(clock+604800)));
    const reveal=button('Reveal corrected outcomes',async()=>{const r=await api('/api/research-review/'+encodeURIComponent(e.id)+'?reveal=true');if(version!==generation)return;outcome.textContent=r.targets.map(t=>`${t.label}: ${t.result.outcome==='CENSORED'?'UNKNOWN / unresolved':t.result.outcome} · ${t.result.gross_R||'unresolved'} gross R · observed ${t.result.observed_at||'not recorded'} · fill window ${t.result.fill_start||'unknown'} — ${t.result.fill_end||'unknown'}`).join('\n');e.revealedTargets=r.targets;panels.forEach(decorate);reveal.disabled=true;});controls.append(reveal);detail.append(controls,el('p','','review-clock'));const outcome=el('p','Outcomes hidden. Revealing results does not move the chart clock.','review-outcomes');detail.append(outcome);
    detail.append(el('p','Lines show the setup levels known at the decision time. Price bars stop at the review clock; incomplete candles are omitted. After revealing outcomes, advance the clock to see observed fill/exit markers. Their times are observation bounds, not exact execution ticks. H1 history cannot show the exact ordering within one minute.','muted'));
    const grid=el('div',undefined,'review-charts');detail.append(grid);panel(grid,'H4 context','H4',version);panel(grid,'Entry view',e.tf,version);
    if(e.flow){const legend=el('ol',undefined,'review-legend');e.flow.timeline.forEach(t=>legend.append(el('li',t.stage.replaceAll('_',' ')+' · '+t.at.replace('T',' ').replace('+00:00',' UTC'))));legend.append(el('li','ENTRY PLAN · '+e.decision.replace('T',' ')));detail.append(legend);const evidence=el('details'),summary=el('summary','Recorded sequence and evidence');evidence.append(summary);const pre=el('pre',JSON.stringify(e.flow,null,2));evidence.append(pre);detail.append(evidence);}
    if(e.stop_proof){const proof=el('details'),s=el('summary','Logical stop evidence');proof.append(s,el('pre',JSON.stringify(e.stop_proof,null,2)));detail.append(proof);}
    await advance(clock,true);
    if(version===generation)await reportForm(detail,e,version);
  }
  function panel(parent,title,tf,version){const box=el('div',undefined,'review-panel');box.append(el('h4',title));const controls=el('div',undefined,'review-controls');const [wrap,s]=select('Timeframe',tfs.map(t=>[t,t==='D'?'Daily':t==='W'?'Weekly':t]));s.value=tf;controls.append(wrap);box.append(controls);const quote=el('div','Move the crosshair over a candle for OHLC.','review-quote');box.append(quote);const canvas=el('div',undefined,'review-canvas');box.append(canvas);parent.append(box);
    const chart=LightweightCharts.createChart(canvas,{autoSize:true,height:380,layout:{background:{color:'#101923'},textColor:'#d6e2ef'},grid:{vertLines:{color:'#202d3b'},horzLines:{color:'#202d3b'}},timeScale:{timeVisible:true,secondsVisible:false,rightOffset:8},localization:{timeFormatter:stamp},handleScroll:true,handleScale:true});
    const series=chart.addSeries(LightweightCharts.CandlestickSeries,{upColor:'#32bd9b',downColor:'#ee7183',wickUpColor:'#32bd9b',wickDownColor:'#ee7183',borderVisible:false,priceFormat:{type:'price',precision:Math.max(0,Math.round(-Math.log10(selected.tick_size))),minMove:selected.tick_size}});
    const p={context:title==='H4 context',chart,series,select:s,bars:[],lines:[],markers:null,version,busy:false,more:true};panels.push(p);
    controls.append(button('Load earlier candles',()=>load(p,true)),button('Fit candles',()=>chart.timeScale().fitContent()));s.onchange=()=>load(p,false).catch(error);
    chart.subscribeCrosshairMove(param=>{const b=param.seriesData.get(series);if(b)quote.textContent=`${stamp(b.time)} · O ${price(b.open)} H ${price(b.high)} L ${price(b.low)} C ${price(b.close)}`;});
    const full=button('Expand chart',()=>{box.classList.toggle('review-expanded');full.textContent=box.classList.contains('review-expanded')?'Close expanded view':'Expand chart';});controls.append(full);
  }
  async function advance(next,reset=false){if(!selected)return;clock=Math.min(next,epoch(selected.cutoff));root.querySelector('.review-clock').textContent=`Review clock: ${stamp(clock)}${clock===epoch(selected.decision)?' · decision time':''}`;if(reset){delete selected.revealedTargets;root.querySelector('.review-outcomes').textContent='Outcomes hidden. Revealing results does not move the chart clock.';const buttons=root.querySelectorAll('.review-detail > .review-controls button');buttons[buttons.length-1].disabled=false;}await Promise.all(panels.map(p=>load(p,false)));}
  async function load(p,older){if(p.version!==generation)return;const request=(p.request||0)+1;p.request=request;const key=selected.id,tf=p.select.value;const q=new URLSearchParams({tf,as_of:String(clock),limit:'300'});if(older&&p.bars.length)q.set('before',p.bars[0].time);const d=await api(`/api/research-review/${encodeURIComponent(key)}/candles?${q}`);if(p.version!==generation||p.request!==request)return;
    const range=p.chart.timeScale().getVisibleLogicalRange();const count=d.candles.length;p.bars=older?[...d.candles,...p.bars]:d.candles;p.more=d.has_more;p.series.setData(p.bars);decorate(p);
    if(older&&range)p.chart.timeScale().setVisibleLogicalRange({from:range.from+count,to:range.to+count});else p.chart.timeScale().setVisibleLogicalRange({from:Math.max(0,p.bars.length-85),to:p.bars.length+5});
    const b=p.select.closest('.review-controls').querySelector('button');b.disabled=!d.has_more;b.textContent=d.has_more?'Load earlier candles':'Start of saved history';
  }
  function decorate(p){p.lines.forEach(l=>p.series.removePriceLine(l));p.lines=[];const e=selected;const line=(price,title,color)=>{if(Number.isFinite(price))p.lines.push(p.series.createPriceLine({price,title,color,lineWidth:1,lineStyle:2,axisLabelVisible:true}));};if(!p.context||!e.flow){line(e.entry,e.entry_reference?.kind?'Entry '+e.entry_reference.kind:'Entry','#73baff');line(e.stop,'SL','#ff7085');e.targets.forEach(t=>line(t.price,t.label,'#42d6ae'));}
    if(!p.context)for(const a of e.entry_reference?.alternatives||[]){if(Math.abs(a.price-e.entry)>=e.tick_size/2)line(a.price,a.kind+' alternative','#cdb0ff');}
    const f=e.flow;let events=[{at:e.decision,stage:'ENTRY PLAN'}];if(f){if(p.context){line(f.break.level_ticks*e.tick_size,'H4 break level','#cdb0ff');line(f.pool.price_ticks*e.tick_size,'Single-candle liquidity','#ffc46b');line(f.level.price_ticks*e.tick_size,'Reaction key level','#fff099');}events=[...f.timeline,...events];}
    const markers=[];for(const [index,event] of events.entries()){const at=epoch(event.at);if(at>clock)continue;const b=p.bars.findLast(b=>b.time<at);if(!b||at>b.end+7*86400)continue;markers.push({time:b.time,position:'aboveBar',color:'#ffc46b',shape:'circle',text:String(index+1)});}
    for(const t of e.revealedTargets||[]){for(const [date,label] of [[t.result.fill_end,'Recorded fill bound '+t.label],[['WIN','LOSS','BREAK_EVEN'].includes(t.result.outcome)?t.result.observed_at:null,'Exit observed '+t.label]]){if(!date)continue;const at=epoch(date);if(!Number.isFinite(at)||at>clock)continue;const b=p.bars.findLast(b=>b.time<at);if(b&&at<=b.end+7*86400)markers.push({time:b.time,position:'belowBar',color:'#73baff',shape:'arrowUp',text:label});}}
    markers.sort((a,b)=>a.time-b.time);const grouped=[];for(const m of markers){const last=grouped[grouped.length-1];if(last&&last.time===m.time&&last.position===m.position)last.text+=','+m.text;else grouped.push(m);}if(p.markers)p.markers.setMarkers(grouped);else p.markers=LightweightCharts.createSeriesMarkers(p.series,grouped);
  }
  return {open};
})();

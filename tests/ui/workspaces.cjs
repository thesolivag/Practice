// Run with node tests/ui/workspaces.cjs; uses Playwright + system Chromium.
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
const root=path.resolve(__dirname,'../../webapp/static');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:390,height:844},hasTouch:true,timezoneId:'UTC'});
 let paired=false,watch=null,journal=[],settings={pairs:'EURUSD,DVR75'},step=0;
 let releaseAlertSchema,alertSchemaRequests=0;const alertSchemaGate=new Promise(resolve=>releaseAlertSchema=resolve);
 let unavailableStep=false,holdStep=false,releaseStep,markStepStarted;const heldStep=new Promise(resolve=>releaseStep=resolve),stepStarted=new Promise(resolve=>markStepStarted=resolve);
 const errors=[],watchBodies=[],openBodies=[],timeframeBodies=[],historyBodies=[],cursors=new Map();page.on('pageerror',e=>errors.push(e.message));
 const schemas={groups:['Markets'],settings:[{name:'pairs',type:'pairs',default:'EURUSD',group:'Markets',choices:['EURUSD','DVR75'],labels:{DVR75:'Deriv · Volatility 75 Index (DVR75)'},groups:{EURUSD:'IC Markets · Forex · majors',DVR75:'Deriv · Synthetic indices'},help:'Choose watched markets'}]};
 const prices=[{value:'close_above',label:'Close above',description:'Completed candle closes above your level.'},{value:'crossing',label:'Sampled crossing',description:'Sampled quote crossing.'}];
 const models=[{value:'breakout',label:'Breakout'},{value:'engulfing',label:'Engulfing'},{value:'fourth_man',label:'4th man'}];
 const conditions={timeframes:['H1','H2','H4'],price_conditions:prices,confirmation_models:models,confirmation_timeframes:['M5','M15','M30','H1','H2','H3','H4'],conditions:[...prices,...models],lower_timeframes:{H2:'H1',H4:'H2'},max_confirmation_timeframes:6};
 async function exitChart(){if(await page.locator('#replay-panel.chart-full').count())await page.locator('#replay-close').click();}
 async function showTools(){await page.locator('#chart-tools-panel').evaluate(el=>el.open=true);}
 async function tool(kind){await showTools();await page.locator('#chart-tool').selectOption(kind);}
 async function chartClick(position){await page.locator('#chart-tools-panel').evaluate(el=>el.open=false);await page.locator('#replay-chart-stage').click({position});}
 async function toolButton(id){await showTools();await page.locator(id).click();}
 const anchor=Date.parse('2026-10-20T08:00:00Z')/1000,durations={H1:3600,H2:7200,H3:10800,H4:14400,D:86400,W:604800};
 // Deterministic synthetic broker-like fixtures, not downloaded/live market evidence.
 // Forex has weekend gaps; Deriv remains continuous. Every bar has a true close boundary.
 function barsBefore(ctx, before=ctx.clock, count=160){
  const duration=durations[ctx.timeframe], bars=[];
  let time=Math.floor(before/duration)*duration-duration;
  while(bars.length<count){
   const day=new Date(time*1000).getUTCDay();
   if(ctx.pair.startsWith('DV')||duration>=604800||![0,6].includes(day)){
    const n=time/3600,base=1.1+Math.sin(n/9)*.002+Math.cos(n/31)*.001;
    const open=Number(base.toFixed(5)),close=Number((base+Math.sin(n)*.00055).toFixed(5));
    bars.push({time,end:time+duration,open,high:Number((Math.max(open,close)+.00035).toFixed(5)),low:Number((Math.min(open,close)-.0003).toFixed(5)),close});
   }
   time-=duration;
  }
  return bars.reverse();
 }
 function replay(ctx){
  const cursor=`cursor-${cursors.size}`;cursors.set(cursor,ctx);const duration=durations[ctx.timeframe];
  const bars=barsBefore(ctx);
  // Deliberately inject a future bar: the UI must never reveal its extreme OHLC.
  bars.push({time:ctx.clock,end:ctx.clock+duration,open:90,high:99,low:80,close:95});
  return {available:true,...ctx,cursor,bars,finished:false,feed:'Synthetic test fixture',
   markers:ctx.mode==='alert'?[{time:ctx.anchor,price:1.1,label:'Key level',kind:'level'}]:[],event:ctx.mode==='alert'?{time:ctx.anchor,pair:ctx.pair,label:'Alert'}:null};
 }
 await page.route('**/*',async r=>{
  const req=r.request(),u=new URL(req.url()),body=req.postData()?JSON.parse(req.postData()):null;
  if(u.hostname==='telegram.org')return r.fulfill({body:'window.Telegram={WebApp:{initData:"",ready(){},expand(){}}}',contentType:'application/javascript'});
  const reply=(json,status=200)=>r.fulfill({status,json});
  if(u.pathname==='/api/auth/session')return paired?reply({user:{id:42},csrf:'csrf-value',auth_method:'browser'}):reply({detail:'not connected'},403);
  if(u.pathname==='/api/auth/redeem'){assert.equal(body.client,'browser');assert.equal(body.code,'test-code');paired=true;return reply({user:{id:42},csrf:'csrf-value'});}
  if(u.pathname.startsWith('/api/')&&req.method()!=='GET')assert.equal(req.headers()['x-csrf-token'],'csrf-value');
  if(u.pathname==='/api/settings/schema')return reply(schemas);
  if(u.pathname==='/api/settings'){if(body)settings=body;return reply(settings);}
  if(u.pathname==='/api/alerts/schema'){alertSchemaRequests++;await alertSchemaGate;return reply(conditions);}
  if(/^\/api\/alerts\/1\/(pause|resume)$/.test(u.pathname)){watch.status=u.pathname.endsWith('/pause')?'PAUSED':'ACTIVE';return reply({ok:true,id:1});}
  if(u.pathname==='/api/alerts'){
   if(body){await new Promise(resolve=>setTimeout(resolve,300));watchBodies.push(body);watch={id:1,...body,status:'ACTIVE',expires_at:1900000000,event_time:anchor,error:watchBodies.length===3?'Provider temporarily unavailable':null};return reply(watch);}
   return reply(watch?[watch]:[]);
  }
  if(u.pathname==='/api/replay/sources')return reply([{kind:'bias',id:5,pair:'EURUSD',anchor,label:'EURUSD confirmed bias'},{kind:'watch_event',id:9,watch_id:1,pair:'DVR75',anchor,label:'DVR75 recorded watch event'}]);
  if(u.pathname==='/api/journal'){
   if(body){assert.equal(body.source_kind,'manual');assert.equal(body.source_id,null);journal=[{id:7,...body}];return reply(journal[0]);}
   return reply(journal);
  }
  if(u.pathname==='/api/journal/7'&&req.method()==='PUT'){assert.equal(body.source_kind,undefined);assert.equal(body.source_id,undefined);assert.equal(body.pair,undefined);journal[0]={...journal[0],...body};return reply(journal[0]);}
  if(u.pathname==='/api/replay/open'){
   openBodies.push(body);const isPrice=body.mode==='price',start=isPrice?Date.parse(body.start)/1000:anchor;
   return reply(replay({mode:isPrice?'price':'alert',pair:isPrice?body.pair:'EURUSD',anchor:start,clock:start,timeframe:body.timeframe}));
  }
  if(u.pathname==='/api/replay/step'){step++;if(unavailableStep)return reply({available:false,message:'History temporarily busy'});const ctx=cursors.get(body.cursor);assert(ctx);if(holdStep){markStepStarted();await heldStep;}return reply(replay({...ctx,clock:ctx.clock+durations[ctx.timeframe]}));}
  if(u.pathname==='/api/replay/timeframe'){timeframeBodies.push(body);const ctx=cursors.get(body.cursor);assert(ctx);return reply(replay({...ctx,timeframe:body.timeframe}));}
  if(u.pathname==='/api/replay/history'){
   historyBodies.push(body);const ctx=cursors.get(body.cursor);assert(ctx);
   const bars=barsBefore(ctx,body.before,120);
   return reply({available:true,bars,before:bars[0].time,has_more:false,status:'ready',message:'Earlier fixture history loaded.',clock:ctx.clock,timeframe:ctx.timeframe,feed:'Synthetic test fixture'});
  }
  if(u.pathname.startsWith('/api/'))return reply([]);
  if(u.pathname==='/static/replay_chart.js')return r.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'replay_chart.js'),'utf8')+';window.ReplayViewport=class extends window.ReplayViewport { constructor(...args){super(...args);window.testReplayViewport=this;} };'});
  return r.fulfill({path:path.join(root,u.pathname.startsWith('/static/')?u.pathname.slice(8):'index.html')});
 });
 await page.goto('http://slk.test/');await page.locator('#login-panel').waitFor({state:'visible'});
 await page.locator('#browser-login-code').fill('test-code');await page.locator('#browser-login-form button').click();await page.locator('#tabs').waitFor({state:'visible'});
 await page.locator('[data-tab=alerts]').click();await page.locator('#watch-pair').selectOption('DVR75');await page.locator('#watch-tf').selectOption('H2');
 // Delayed schema response and re-entry must preserve the user's H2 selection.
 await page.locator('[data-tab=bias]').click();await page.locator('[data-tab=alerts]').click();releaseAlertSchema();
 await page.waitForFunction(()=>document.querySelector('#watch-condition').options.length>0);assert.equal(alertSchemaRequests,1);assert.equal(await page.locator('#watch-tf').inputValue(),'H2');
 assert.equal(await page.locator('#watch-confirmation-controls').isVisible(),false);
 await page.locator('#watch-level').fill('123.45');await page.locator('#watch-note').fill('<img src=x onerror=alert(1)>');await page.locator('#watch-form button').click();
 assert.equal(await page.locator('#watch-form button').getAttribute('aria-busy'),'true');
 assert.equal(await page.locator('#watch-form button').isDisabled(),true);
 await page.locator('#watch-form').evaluate(form => form.dispatchEvent(new SubmitEvent('submit',{bubbles:true,cancelable:true,submitter:form.querySelector('button')})));
 await page.getByText('Price alert saved.',{exact:false}).waitFor();
 await page.waitForFunction(()=>!document.querySelector('#watch-form button').disabled);
 assert.equal(await page.locator('#watch-form button').getAttribute('aria-busy'),null);
 assert.equal(watchBodies.length,1);assert.equal(watchBodies[0].kind,'price');assert.equal(watchBodies[0].timeframe,'H2');assert.equal(watchBodies[0].level,123.45);
 for(const key of ['models','timeframes','scope','repeat','engulfing'])assert.equal(watchBodies[0][key],undefined);
 assert.equal(await page.locator('#watch-list img').count(),0);
 const originalExpiry=watch.expires_at;
 await page.getByRole('button',{name:'Pause',exact:true}).click();
 await page.getByRole('button',{name:'Resume',exact:true}).waitFor();assert.equal(watch.status,'PAUSED');
 assert.equal(watch.expires_at,originalExpiry);
 await page.getByRole('button',{name:'Resume',exact:true}).click();
 await page.getByRole('button',{name:'Pause',exact:true}).waitFor();assert.equal(watch.status,'ACTIVE');
 await page.locator('#watch-expiry').selectOption('168');
 await page.locator('#watch-kind').selectOption('confirmation');assert.equal(await page.locator('#watch-price-controls').isVisible(),false);assert.equal(await page.locator('#watch-level-row').isVisible(),false);
 assert.equal(await page.locator('#watch-expiry').inputValue(),'24');
 await page.locator('#watch-any-model').uncheck();await page.locator('#watch-any-model').check();
 for(const tf of ['M5','M15','M30','H2','H3'])await page.locator(`#watch-timeframes input[value=${tf}]`).check();
 await page.locator('#watch-timeframes input[value=H4]').click();
 assert.equal(await page.locator('#watch-timeframes input:checked').count(),6);assert.equal(await page.locator('#watch-timeframes input[value=H4]').isChecked(),false);
 for(const tf of ['M5','M15','M30','H3'])await page.locator(`#watch-timeframes input[value=${tf}]`).uncheck();
 await page.locator('#watch-repeat').selectOption('each');await page.locator('#watch-form button').click();
 await page.getByText('Confirmation alert saved.',{exact:false}).waitFor();assert.equal(watchBodies[1].expires_hours,24);assert.deepEqual(watchBodies[1].models,['breakout','engulfing','fourth_man']);assert.deepEqual(watchBodies[1].timeframes,['H1','H2']);
 assert.equal(watchBodies[1].scope,'anywhere');assert.equal(watchBodies[1].repeat,'each');for(const key of ['level','condition','timeframe'])assert.equal(watchBodies[1][key],undefined);
 await page.locator('#watch-scope').selectOption('level');assert.equal(await page.locator('#watch-level').getAttribute('required'),'');
 await page.locator('#watch-form button').click();assert.equal(watchBodies.length,2); // scoped confirmation cannot save without a level
 await page.locator('#watch-any-model').uncheck();await page.locator('#watch-models input[value=fourth_man]').check();await page.locator('#watch-level').fill('124.5');await page.locator('#watch-engulfing').check();
 await page.locator('#watch-form button').click();await page.getByText('Provider temporarily unavailable',{exact:true}).waitFor();assert.deepEqual(watchBodies[2].models,['fourth_man']);assert.equal(watchBodies[2].level,124.5);assert.equal(watchBodies[2].engulfing,true);
 await page.locator('#watch-kind').selectOption('price');assert.equal(await page.locator('#watch-level').inputValue(),'');await page.locator('#watch-level').fill('125');await page.locator('#watch-form button').click();
 await page.waitForFunction(()=>document.querySelector('#watch-feedback').textContent.startsWith('Price alert saved'));
 assert.equal(watchBodies[3].kind,'price');assert.equal(watchBodies[3].engulfing,undefined);
 await page.locator('#watch-pair').selectOption('EURUSD');assert.equal(await page.locator('#watch-level').inputValue(),'');assert.equal(await page.locator('#watch-note').inputValue(),'');
 await page.locator('[data-tab=journal]').click();await page.locator('#journal-source').selectOption('manual:');await page.locator('#journal-pair').selectOption('EURUSD');
 await page.locator('#journal-entry').fill('1.1');await page.locator('#journal-stop').fill('1.0');await page.locator('#journal-target').fill('1.3');await page.locator('#journal-notes').fill('<script>bad()</script>');
 await page.locator('#journal-form button[type=submit]').click();await page.getByText('Journal note saved.',{exact:false}).waitFor();assert.equal(await page.locator('#journal-list script').count(),0);
 await page.locator('[data-edit-journal="7"]').click();await page.locator('#journal-notes').fill('Updated note');await page.locator('#journal-form button[type=submit]').click();await page.getByText('Updated note',{exact:true}).waitFor();
 await page.locator('[data-tab=replay]').click();await page.locator('#replay-source').selectOption('bias:5');await page.locator('#replay-form button').click();await page.locator('#replay-panel').waitFor({state:'visible'});
 assert.deepEqual(openBodies[0],{kind:'bias',id:5,timeframe:'H1'});assert.equal(step,0);assert((await page.locator('#replay-markers').textContent()).includes('Key level'));
 await page.locator('#replay-next').click();await page.waitForFunction(()=>document.querySelector('#replay-caption').textContent.includes('09:00'));assert.equal(step,1);
 await exitChart();await page.locator('#replay-timeframe').selectOption('H4');await page.waitForFunction(()=>document.querySelector('#replay-caption').textContent.includes('H4'));
 assert.equal(cursors.get(timeframeBodies[0].cursor).clock,anchor+3600);assert((await page.locator('#replay-caption').textContent()).includes('09:00'));
 await page.locator('#replay-reset').click();await page.waitForFunction(()=>document.querySelector('#replay-caption').textContent.includes('08:00'));assert.deepEqual(openBodies[1],{kind:'bias',id:5,timeframe:'H4'});
 await exitChart();await page.locator('#replay-mode').selectOption('price');assert.equal(await page.locator('#replay-panel').isVisible(),false);assert.equal(await page.locator('#replay-alert-controls').isVisible(),false);
 await exitChart();await page.locator('#replay-pair').selectOption('DVR75');await exitChart();await page.locator('#replay-start').fill('2026-10-19T05:00');await exitChart();await page.locator('#replay-timeframe').selectOption('H2');await page.locator('#replay-form button').click();await page.locator('#replay-panel').waitFor({state:'visible'});
 assert.deepEqual(openBodies[2],{mode:'price',pair:'DVR75',start:'2026-10-19T05:00:00.000Z',timeframe:'H2'});assert.equal(await page.locator('#replay-markers').textContent(),'');
 await page.locator('#replay-next').click();await page.waitForFunction(()=>document.querySelector('#replay-caption').textContent.includes('07:00'));
 await exitChart();await page.locator('#replay-timeframe').selectOption('D');await page.waitForFunction(()=>document.querySelector('#replay-caption').textContent.includes(' · D · '));assert.equal(cursors.get(timeframeBodies[1].cursor).clock,Date.parse('2026-10-19T07:00:00Z')/1000);
 await page.locator('#replay-reset').click();await page.waitForFunction(()=>document.querySelector('#replay-caption').textContent.includes('05:00'));assert.equal(openBodies[3].timeframe,'D');assert.equal(openBodies[3].start,'2026-10-19T05:00:00.000Z');
 await exitChart();await page.locator('#replay-start').fill('2026-10-18T05:00');await page.locator('#replay-start').dispatchEvent('change');assert.equal(await page.locator('#replay-panel').isVisible(),false);
 await page.locator('#replay-form button').click();await page.locator('#replay-panel').waitFor({state:'visible'});
 holdStep=true;await page.locator('#replay-next').click();await stepStarted;
 await exitChart();await page.locator('#replay-mode').selectOption('alert');assert.equal(await page.locator('#replay-panel').isVisible(),false);
 const oldResponse=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/replay/step');releaseStep();await oldResponse;
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 assert.equal(await page.locator('#replay-panel').isVisible(),false);assert.equal(await page.locator('#replay-caption').textContent(),'');
 await exitChart();await page.locator('[data-tab=alerts]').click();await page.locator('[data-replay-watch="1"]').click();await page.locator('#replay-panel').waitFor({state:'visible'});
 assert.equal(openBodies[openBodies.length-1].kind,'watch_event');assert.equal(openBodies[openBodies.length-1].id,9);assert.equal(await page.locator('#replay-mode').inputValue(),'alert');
 assert.equal(await page.locator('#replay-panel').evaluate(el=>el.classList.contains('chart-full')),true);
 await page.waitForFunction(()=>window.testReplayViewport?.bars.length>100);
 const stage=await page.locator('#replay-chart-stage').boundingBox();assert(stage.height>420,`Mobile chart too small: ${stage.height}`);
 assert(await page.evaluate(()=>window.testReplayViewport.bars.every(b=>b.high<2)), 'Future extreme candle leaked into chart');
 const visibleRange=()=>page.evaluate(()=>window.testReplayViewport.chart.timeScale().getVisibleLogicalRange());
 const initialRange=await visibleRange();
 await page.mouse.move(stage.x+stage.width*.45,stage.y+stage.height*.45);await page.mouse.down();await page.mouse.move(stage.x+stage.width*.8,stage.y+stage.height*.45,{steps:12});await page.mouse.up();
 const pannedRange=await visibleRange();assert(Math.abs(pannedRange.from-initialRange.from)>5,'Dragging must pan candles');
 await page.mouse.move(stage.x+stage.width*.5,stage.y+stage.height*.4);await page.mouse.wheel(0,-240);
 await page.waitForTimeout(150);const zoomedRange=await visibleRange();assert(zoomedRange.to-zoomedRange.from<pannedRange.to-pannedRange.from,'Wheel must zoom candles');
 const inspect=await page.evaluate(()=>{const v=window.testReplayViewport,r=v.chart.timeScale().getVisibleLogicalRange(),b=v.bars[Math.floor((r.from+r.to)/2)];return {x:v.chart.timeScale().timeToCoordinate(b.time),y:v.series.priceToCoordinate(b.close),bar:b};});
 await page.mouse.move(stage.x+inspect.x,stage.y+inspect.y);await page.waitForTimeout(50);
 assert((await page.locator('#replay-bar').textContent()).includes(`C ${inspect.bar.close}`),'Crosshair must inspect hovered OHLC');
 await page.screenshot({path:'/tmp/replay-viewport-mobile.png'});
 const beforeHistory=await page.evaluate(()=>window.testReplayViewport.bars[0].time),historyClock=await page.locator('#replay-caption').textContent();
 for(let i=0;i<7&&!historyBodies.length;i++){
  await page.mouse.move(stage.x+40,stage.y+stage.height*.4);await page.mouse.down();await page.mouse.move(stage.x+stage.width-90,stage.y+stage.height*.4,{steps:10});await page.mouse.up();await page.waitForTimeout(60);
 }
 assert.equal(historyBodies.length,1,'Panning left must request one bounded history page');
 await page.waitForFunction(before=>window.testReplayViewport.bars[0].time<before,beforeHistory);
 assert.equal(await page.locator('#replay-caption').textContent(),historyClock,'History loading must preserve replay clock');
 assert(await page.locator('#replay-chart-status').isVisible());
 await page.evaluate(()=>window.testReplayViewport.head());

 await page.locator('#chart-tools-panel summary').first().click();

 await tool('line');await chartClick({x:100,y:100});
 await tool('long');await chartClick({x:100,y:100});await chartClick({x:100,y:150});assert((await page.locator('#chart-help').textContent()).includes('drawing added'));
 await page.screenshot({path:'/tmp/replay-mobile.png'});
 await toolButton('#chart-undo');await toolButton('#chart-in');await toolButton('#chart-out');
 // Drawings use chart coordinates, survive zoom, and support editing/moving/deleting with undo.
 for(const kind of ['rectangle','trend']) {
   await tool(kind);
   await chartClick({x:85,y:90});await chartClick({x:220,y:175});
 }
 await tool('text');await page.locator('#chart-editor').evaluate(el=>el.open=true);await page.locator('#drawing-text').fill('<img src=x> Zone note');
 await chartClick({x:110,y:120});
 assert.equal(await page.locator('#drawing-select option').count(),5);assert.equal(await page.locator('#chart-editor img').count(),0);
 await showTools();await page.locator('#drawing-text').fill('Retest zone');await page.locator('#drawing-price').fill('1.10125');await page.locator('#drawing-edit button').click();
 assert((await page.locator('#drawing-select option:checked').textContent()).includes('Retest zone'));
 assert.equal(await page.locator('#drawing-price').inputValue(),'1.10125');
 const beforeTime=await page.locator('#drawing-time').inputValue();await toolButton('#chart-in');assert.equal(await page.locator('#drawing-time').inputValue(),beforeTime);
 await toolButton('#drawing-move');await chartClick({x:180,y:160});
 assert.equal(await page.locator('#chart-help').textContent(),'Drawing moved.');assert.notEqual(await page.locator('#drawing-price').inputValue(),'1.10125');
 await toolButton('#drawing-delete');assert.equal(await page.locator('#drawing-select option').count(),4);
 await toolButton('#chart-undo');assert.equal(await page.locator('#drawing-select option').count(),5);
 await showTools();await page.locator('#drawing-select').selectOption('1');await page.locator('#drawing-second').fill('1.10175');await page.locator('#drawing-edit button').click();assert.equal(await page.locator('#chart-help').textContent(),'Drawing updated.');
 // Drag a drawing with real pointer events, then undo/redo it.
 await tool('cursor');await showTools();await page.locator('#drawing-select').selectOption('0');
 const linePrice=Number(await page.locator('#drawing-price').inputValue());
 const lineY=await page.evaluate(p=>window.testReplayViewport.series.priceToCoordinate(p),linePrice);
 const lineX=await page.evaluate(()=>window.testReplayViewport.transform().w/2);
 await page.locator('#chart-tools-panel').evaluate(el=>el.open=false);
 const dragStage=await page.locator('#replay-chart-stage').boundingBox();
 await page.mouse.move(dragStage.x+lineX,dragStage.y+lineY);await page.mouse.down();await page.mouse.move(dragStage.x+lineX,dragStage.y+lineY+35,{steps:8});await page.mouse.up();
 const movedLine=Number(await page.locator('#drawing-price').inputValue());assert.notEqual(movedLine,linePrice,'Pointer drag must move horizontal line');
 await toolButton('#chart-undo');await page.locator('#drawing-select').selectOption('0');assert.equal(Number(await page.locator('#drawing-price').inputValue()),linePrice);
 await toolButton('#chart-redo');await page.locator('#drawing-select').selectOption('0');assert.equal(Number(await page.locator('#drawing-price').inputValue()),movedLine);
 await page.locator('#chart-tools-panel').evaluate(el=>el.open=false);
 await page.screenshot({path:'/tmp/replay-drawings-mobile.png'});
 unavailableStep=true;const unchanged=await page.locator('#replay-caption').textContent();await page.locator('#replay-next').click();
 await page.getByText('History temporarily busy',{exact:true}).waitFor();assert(await page.locator('#replay-panel').isVisible());assert.equal(await page.locator('#replay-caption').textContent(),unchanged);unavailableStep=false;

 await exitChart();settings.display_tz='Africa/Lagos';await page.locator('[data-tab=settings]').click();await page.locator('[data-tab=replay]').click();
 await page.locator('#replay-mode').selectOption('price');await page.locator('#replay-pair').selectOption('EURUSD');await page.locator('#replay-start').fill('2026-10-19T09:00');await page.locator('#replay-form button').click();await page.locator('#replay-panel').waitFor({state:'visible'});
 assert.equal(await page.locator('#drawing-select option').count(),1);
 assert.equal(openBodies.at(-1).start,'2026-10-19T08:00:00.000Z');assert((await page.locator('#replay-caption').textContent()).includes('Africa/Lagos'));
 assert((await page.locator('#replay-caption').textContent()).includes('09:00'));
 // Native touch panning on a phone-sized viewport.
 await page.locator('#chart-tools-panel').evaluate(el=>el.open=false);
 const touchStage=await page.locator('#replay-chart-stage').boundingBox(),beforeTouch=await visibleRange();
 const cdp=await page.context().newCDPSession(page),tx=touchStage.x+80,ty=touchStage.y+touchStage.height*.55;
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:tx,y:ty}]});
 for(let i=1;i<=8;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:tx+i*14,y:ty}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 const afterTouch=await visibleRange();assert(Math.abs(afterTouch.from-beforeTouch.from)>5,'Touch drag must pan candles');
 await cdp.detach();await page.evaluate(()=>window.testReplayViewport.head());
 // Same chart remains useful on desktop and axes/crosshair use account timezone.
 const beforeResize=await visibleRange();
 await page.setViewportSize({width:1440,height:900});await page.waitForTimeout(100);
 assert((await page.locator('#replay-chart-stage').boundingBox()).height>650);
 const afterResize=await visibleRange();assert(Math.abs((afterResize.to-afterResize.from)-(beforeResize.to-beforeResize.from))<2,'Resize must preserve visible candle range');
 assert((await page.evaluate(()=>window.testReplayViewport.options.tick(Date.parse('2026-10-19T08:00:00Z')/1000))).includes('09:00'));
 await page.screenshot({path:'/tmp/replay-viewport-desktop.png'});
 assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>localStorage.length),0);await browser.close();
 console.log('Separate price/confirmation payloads, Any models, scope, recurring watches, journals and both replay modes/timeframes/reset passed');
})().catch(e=>{console.error(e);process.exit(1)});

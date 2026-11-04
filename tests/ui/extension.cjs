const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path');
const {chromium}=require('playwright');
const dir=path.resolve(__dirname,'../../extension');
(async()=>{
 let listener,storage={},requests=[],accessLevel;
 const chrome={runtime:{id:'slk-test',onMessage:{addListener:f=>listener=f}},storage:{local:{setAccessLevel:async v=>{accessLevel=v.accessLevel},get:async keys=>typeof keys==='string'?{[keys]:storage[keys]}:{...storage},set:async v=>Object.assign(storage,v),remove:async keys=>keys.forEach(k=>delete storage[k])}}};
 const fetch=async(url,opts)=>{requests.push({url,opts});return {ok:true,status:200,json:async()=>url.endsWith('/redeem')?{token:'private-token',expires_at:Date.now()/1000+3600}:{settings:[]}}};
 vm.runInNewContext(fs.readFileSync(path.join(dir,'background.js'),'utf8'),{chrome,fetch,Date,console});
 const message=(body,sender={id:'slk-test'})=>new Promise(resolve=>listener(body,sender,resolve));
 assert.equal(accessLevel,'TRUSTED_CONTEXTS');
 assert.equal((await message({action:'pair',code:'one-time-code'})).ok,true);
 assert.equal(requests[0].opts.headers.Authorization,undefined);
 assert.equal(storage.slkToken,'private-token');
 assert.equal((await message({action:'schema'})).ok,true);
 assert.equal(requests[1].opts.headers.Authorization,'Bearer private-token');
 assert.equal(requests[1].opts.credentials,'omit');
 assert.equal((await message({action:'pair',code:'bad'},{id:'slk-test',tab:{id:1}})).ok,false);
 assert.equal((await message({action:'schema'},{id:'other-extension'})).ok,false);
 assert.equal((await message({action:'arbitrary',url:'https://elsewhere.test'})).ok,false);
 assert.equal((await message({action:'cancelAlert',id:'../../logout'})).ok,false);
 assert.equal((await message({action:'quote',pair:'../../secret'})).ok,false);
 assert.equal((await message({action:'cancelAlert',id:7})).ok,true);
 assert(requests.at(-1).url.endsWith('/api/alerts/7/cancel'));
 assert.equal((await message({action:'logout'})).ok,true);assert.equal(storage.slkToken,undefined);
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage();let saved=null;
 const hoverPill=async()=>{const rect=await page.locator('#slk-chart-alerts-host').locator('#pill').boundingBox();assert(rect);await page.mouse.move(rect.x+rect.width/2,rect.y+rect.height/2);};
 await page.route('**/*',r=>r.fulfill({contentType:'text/html',body:'<title>Unmatched chart</title><body>Chart</body>'}));
 await page.goto('https://www.tradingview.com/chart/test/');
 await page.evaluate(()=>{
  const attach=Element.prototype.attachShadow;Element.prototype.attachShadow=function(init){return attach.call(this,{...init,mode:'open'})};
  window.chrome={runtime:{sendMessage:async message=>{
   if(message.action==='status')return {ok:true,data:{connected:true}};
   if(message.action==='schema')return {ok:true,data:{settings:[{name:'pairs',choices:['EURUSD','GBPJPY','DVR75','DVR25','BTCUSD'],groups:{BTCUSD:'IC Markets · Cryptocurrencies'},labels:{DVR75:'Deriv · Volatility 75 Index (DVR75)',DVR25:'Deriv · Volatility 25 Index (DVR25)'}}]}};
   if(message.action==='alertsSchema'){const prices=[{value:'close_above',label:'Close above',description:'Completed close'}],models=[{value:'breakout',label:'Breakout'},{value:'engulfing',label:'Engulfing'},{value:'fourth_man',label:'4th man'}];return {ok:true,data:{timeframes:['M15','H1','H2'],conditions:[...prices,...models],price_conditions:prices,confirmation_models:models,confirmation_timeframes:['M15','H1','H2'],lower_timeframes:{H2:'H1'}}};}
   if(message.action==='quote')return {ok:true,data:{price:1.2345,timestamp:Math.floor(Date.now()/1000),fresh:true}};
   if(message.action==='listAlerts')return {ok:true,data:window.stopped ? [] : [{id:7,pair:'EURUSD',condition:'close_above',timeframe:'H1',level:1.2,status:'ACTIVE',expires_at:Date.now()/1000+3600}]};
   if(message.action==='cancelAlert'){window.stopped=message.id;return {ok:true,data:{ok:true}};}
   if(message.action==='createAlert'){window.savedAlert=message.body;window.savedAlerts=[...(window.savedAlerts||[]),message.body];return {ok:true,data:{id:1}};}
  }}};
 });
 await page.addScriptTag({path:path.join(dir,'content.js')});
 await hoverPill();
 await page.locator('#slk-chart-alerts-host').locator('#form').waitFor({state:'visible'});
 const host=page.locator('#slk-chart-alerts-host');
 assert.equal(await host.locator('#pair').inputValue(),'');
 await host.locator('[data-market=crypto]').click();
 assert.deepEqual(await host.locator('#pair option').evaluateAll(nodes=>nodes.map(n=>n.value)),['','BTCUSD']);
 await host.locator('[data-market=deriv]').click();
 assert.deepEqual(await host.locator('#pair option').evaluateAll(nodes=>nodes.map(n=>n.value)),['','DVR75','DVR25']);
 await host.locator('[data-market=regular]').click();
 await host.locator('#pair').selectOption('EURUSD');
 await host.locator('#quote').getByText('Broker sample',{exact:false}).waitFor();
 assert.equal(await host.locator('#level').inputValue(),'1.2345'); // Automatic, no Use price click.
 await host.locator('#level').fill('1.456');
 await host.locator('#refresh-quote').click();await host.locator('#quote').getByText('Broker sample',{exact:false}).waitFor();
 assert.equal(await host.locator('#level').inputValue(),'1.456');
 await host.locator('#level').fill('');
 await host.locator('#refresh-quote').click();await host.locator('#quote').getByText('Broker sample',{exact:false}).waitFor();
 assert.equal(await host.locator('#level').inputValue(),''); // Deliberately cleared stays empty.
 await host.locator('#use-price').click();assert.equal(await host.locator('#level').inputValue(),'1.2345');
 await host.locator('[aria-label="Stop alert 7"]').click();
 await page.waitForFunction(()=>window.stopped===7);
 await host.locator('#alerts-status').getByText('0 active',{exact:false}).waitFor();
 await host.locator('[data-market=all]').click();

 await host.locator('#pair').selectOption('DVR75');await host.locator('#timeframe').selectOption('H2');await host.locator('#level').fill('123');
 await host.locator('#save').click();await host.locator('#feedback').getByText('Price alert saved.',{exact:false}).waitFor();
 saved=await page.evaluate(()=>window.savedAlert);assert.equal(saved.pair,'DVR75');assert.equal(saved.timeframe,'H2');assert.equal(saved.kind,'price');assert.equal(saved.models,undefined);assert.equal(saved.engulfing,undefined);
 await host.locator('#kind').selectOption('confirmation');assert.equal(await host.locator('#price-controls').isVisible(),false);assert.equal(await host.locator('#level-row').isVisible(),false);
 await host.locator('#timeframes input[value=H2]').check();await host.locator('#repeat').selectOption('each');await host.locator('#save').click();
 await host.locator('#feedback').getByText('Confirmation alert saved.',{exact:false}).waitFor();saved=await page.evaluate(()=>window.savedAlert);
 assert.deepEqual(saved.models,['breakout','engulfing','fourth_man']);assert.deepEqual(saved.timeframes,['H1','H2']);assert.equal(saved.scope,'anywhere');assert.equal(saved.repeat,'each');assert.equal(saved.level,undefined);assert.equal(saved.condition,undefined);assert.equal(saved.timeframe,undefined);
 await host.locator('#scope').selectOption('level');await host.locator('#save').click();assert.equal(await page.evaluate(()=>window.savedAlerts.length),2);
 await host.locator('#any-model').uncheck();await host.locator('#models input[value=fourth_man]').check();await host.locator('#level').fill('125');await host.locator('#engulfing').check();await host.locator('#save').click();
 await page.waitForFunction(()=>window.savedAlerts.length===3);saved=await page.evaluate(()=>window.savedAlert);assert.deepEqual(saved.models,['fourth_man']);assert.equal(saved.scope,'level');assert.equal(saved.level,125);assert.equal(saved.engulfing,true);
 await host.locator('#kind').selectOption('price');assert.equal(await host.locator('#level').inputValue(),'');
 await page.evaluate(()=>{
  const button=document.createElement('button');button.dataset.name='header-toolbar-symbol-search';button.textContent='EURUSD';document.body.append(button);
  history.replaceState({},'', '?symbol=FOREXCOM:EURUSD');document.title='EURUSD chart';
 });
 await host.locator('#follow').click();
 await page.waitForFunction(()=>document.querySelector('#slk-chart-alerts-host').shadowRoot.querySelector('#pair').value==='EURUSD');
 await host.locator('#level').fill('1.1');
 await page.evaluate(()=>document.querySelector('[data-name="header-toolbar-symbol-search"]').textContent='GBPJPY');
 await page.waitForFunction(()=>document.querySelector('#slk-chart-alerts-host').shadowRoot.querySelector('#pair').value==='GBPJPY');
 await page.waitForFunction(()=>document.querySelector('#slk-chart-alerts-host').shadowRoot.querySelector('#level').value==='1.2345');
 // Active chart DOM wins over an unchanged EURUSD page title and URL.
 await host.locator('#pair').selectOption('DVR75');
 await page.evaluate(()=>document.querySelector('[data-name="header-toolbar-symbol-search"]').textContent='EURUSD');
 await page.waitForTimeout(350);assert.equal(await host.locator('#pair').inputValue(),'DVR75');
 await host.locator('#follow').click();assert.equal(await host.locator('#pair').inputValue(),'EURUSD');
 await host.locator('#close').click();await hoverPill();await host.locator('#panel').waitFor({state:'visible'});
 const handle=await host.locator('#handle').boundingBox();
 await page.mouse.move(handle.x+20,handle.y+5);await page.mouse.down();await page.mouse.move(-100,-100);await page.mouse.up();
 const rect=await host.boundingBox();assert(rect.x>=0&&rect.y>=0);
 // Deriv's visible underlying symbol can change without a useful document title.
 await page.goto('https://charts.deriv.com/deriv');
 await page.evaluate(()=>{
  const attach=Element.prototype.attachShadow;Element.prototype.attachShadow=function(init){return attach.call(this,{...init,mode:'open'})};
  document.title='Deriv charts';const symbol=document.createElement('button');symbol.dataset.testid='chart-symbol';symbol.textContent='R_75';document.body.append(symbol);
  window.chrome={runtime:{sendMessage:async message=>{
   if(message.action==='status')return {ok:true,data:{connected:true}};
   if(message.action==='schema')return {ok:true,data:{settings:[{name:'pairs',choices:['EURUSD','DVR75','DVR25'],labels:{DVR75:'Deriv · Volatility 75 Index (DVR75)',DVR25:'Deriv · Volatility 25 Index (DVR25)'}}]}};
   if(message.action==='alertsSchema')return {ok:true,data:{timeframes:['M5','H1'],price_conditions:[{value:'close_above',label:'Close above'}],confirmation_models:[{value:'fourth_man',label:'4th man'}],confirmation_timeframes:['H1'],conditions:[],lower_timeframes:{H1:'M30'}}};
  }}};
 });
 await page.addScriptTag({path:path.join(dir,'content.js')});
 await hoverPill();await host.locator('#form').waitFor({state:'visible'});
 assert.equal(await host.locator('#pair').inputValue(),'DVR75');
 await page.evaluate(()=>document.querySelector('[data-testid="chart-symbol"]').textContent='Volatility 25 Index');
 await page.waitForFunction(()=>document.querySelector('#slk-chart-alerts-host').shadowRoot.querySelector('#pair').value==='DVR25');
 await browser.close();console.log('Extension separate Price/Confirmation flows, Any/scoped/recurring models, credentials, hover dock, drag bounds and chart follow passed');
})().catch(e=>{console.error(e);process.exit(1)});

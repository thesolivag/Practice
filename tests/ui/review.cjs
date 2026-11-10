const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../webapp/static'),decision=Date.parse('2026-02-18T10:00:00Z')/1000;
 let savedReport=null;
 const entry={id:'sample',pair:'EURUSD',strategy:'recognition_RR',confirmation:'breakout',tf:'H1',side:'BUY',decision:'2026-02-18T10:00:00Z',cutoff:'2026-02-20T10:00:00Z',tick_size:0.00001,entry:1.1,stop:1.099,kind:'LIMIT',targets:[{label:'1R',price:1.101}],flow:null,highlight:false,entry_reference:{kind:'AV',junction_audit:{status:'ENGINE_ELIGIBLE_OC'},pattern_link:'ADJACENT_ENGULF_PAIR',alternatives:[{kind:'AV',price:1.1},{kind:'OC',price:1.1005,audit_only:true}]}};
 await page.route('**/*',async route=>{const u=new URL(route.request().url()),reply=json=>route.fulfill({json});requests.push(u.href);
  if(u.hostname==='telegram.org')return route.fulfill({body:'window.Telegram={WebApp:{initData:"",ready(){},expand(){}}}',contentType:'application/javascript'});
  if(u.pathname==='/api/auth/session')return reply({user:{id:42},csrf:'test',auth_method:'browser'});
  if(u.pathname==='/api/settings')return reply({auto_trade:'confirm',kill_switch:'on',pairs:'EURUSD'});
  if(u.pathname==='/api/settings/schema')return reply({groups:[],settings:[]});
  if(u.pathname==='/api/research-reports/sample'){if(route.request().method()==='PUT'){savedReport={setup_id:'sample',report:{...route.request().postDataJSON(),setup:entry},updated_at:decision};return reply({saved:true,updated_at:decision});}return reply(savedReport);}
  if(u.pathname==='/api/research-reports')return reply({reports:savedReport?[savedReport]:[]});
  if(u.pathname==='/api/research-review')return reply({entries:[entry],pairs:['EURUSD'],strategies:['recognition_RR'],confirmations:['breakout'],total:1,notice:'Frozen test archive'});
  if(u.pathname==='/api/research-review/sample')return reply(u.searchParams.has('reveal')?{...entry,targets:[{...entry.targets[0],result:{outcome:'WIN',gross_R:'1',observed_at:'2026-02-18T12:00:00Z'}}]}:entry);
  if(u.pathname.endsWith('/candles')){const end=Number(u.searchParams.get('before')||u.searchParams.get('as_of'));return reply({candles:Array.from({length:100},(_,i)=>({time:end-(100-i)*3600,end:end-(99-i)*3600,available_at:end-(99-i)*3600,open:1.1,high:1.102,low:1.098,close:1.101})),has_more:!u.searchParams.has('before')});}
  if(u.pathname.startsWith('/api/'))return reply([]);
  return route.fulfill({path:path.join(root,u.pathname.startsWith('/static/')?u.pathname.slice(8):'index.html')});
 });
 await page.goto('http://slk.test/');await page.locator('[data-tab=review]').click();await page.locator('.review-panel canvas').first().waitFor();
 assert.equal(await page.locator('.review-panel').count(),2);
 assert((await page.locator('.review-detail').textContent()).includes('A/V retest'));
 assert((await page.locator('.review-detail').textContent()).includes('Open-close level: 1.10050'));
 assert((await page.locator('.review-detail').textContent()).includes('engine-qualified in prefix audit; not an admitted-order claim'));
 assert((await page.locator('.review-detail').textContent()).includes('Immediate two-candle OC junction'));
 assert((await page.locator('#review-setups').textContent()).includes('(AV entry)'));
 assert((await page.locator('.review-outcomes').textContent()).includes('hidden'));
 for(const tf of ['D','W','H2','H3','H4']){await page.locator('.review-panel select').first().selectOption(tf);await page.waitForResponse(r=>r.url().includes('/candles?tf='+tf));}
 await page.locator('.review-panel').first().getByRole('button',{name:'Load earlier candles'}).click();await page.getByRole('button',{name:'Start of saved history'}).waitFor();assert(requests.some(u=>u.includes('before=')));
 await page.getByRole('button',{name:'+1 hour',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.review-clock').textContent.includes('11:00'));
 await page.getByRole('button',{name:'Reveal corrected outcomes'}).click();await page.waitForFunction(()=>document.querySelector('.review-outcomes').textContent.includes('WIN'));
 await page.getByRole('button',{name:'Reset to decision'}).click();assert((await page.locator('.review-outcomes').textContent()).includes('hidden'));
 await page.locator('.review-panel').first().getByRole('button',{name:'Expand chart'}).click();assert.equal(await page.locator('.review-expanded').count(),1);await page.getByRole('button',{name:'Close expanded view'}).click();
 await page.locator('.review-report summary').click();
 await page.locator('[name=bias]').selectOption('wrong');await page.locator('[name=entry]').selectOption('correct');
 await page.locator('[name=report_notes]').fill('Bias was not confirmed <script>test</script>');await page.locator('[name=report_expected]').fill('Wait for the daily close');
 await page.getByRole('button',{name:'Save setup report'}).click();await page.waitForFunction(()=>document.querySelector('.review-report-status').textContent.includes('Saved to your account'));
 assert.equal(savedReport.report.assessments.bias,'wrong');assert.equal(savedReport.report.assessments.entry,'correct');assert.equal(savedReport.report.review_clock,decision);assert.equal(savedReport.report.outcomes_revealed,false);
 await page.getByRole('button',{name:'My setup reports',exact:true}).click();await page.getByRole('button',{name:'Open reported setup'}).click();await page.locator('.review-report summary').click();
 assert.equal(await page.locator('[name=report_notes]').inputValue(),'Bias was not confirmed <script>test</script>');assert.equal(await page.locator('[name=bias]').inputValue(),'wrong');
 await page.getByRole('button',{name:'Restore saved chart view'}).click();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Export my reports'}).click();assert.equal((await download).suggestedFilename(),'my-setup-reports.json');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);await browser.close();console.log('Research review: dual charts, timeframe controls, pagination, clock, hidden outcomes and mobile layout passed');
})().catch(e=>{console.error(e);process.exit(1)});

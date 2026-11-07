const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:390,height:844}});
 const root=path.resolve(__dirname,'../../webapp/static');
 const entries=[{id:1,strategy:'kk',strategy_label:'KK · Paper',pair:'EURUSD',tf:'H4',side:'BUY',model:'continuation',entry:1.1,stop:1.09,tp1:1.12,tp2:1.14,status:'PENDING'},
 {id:'bishop:one',strategy:'bishop',strategy_label:'Bishop · Paper',pair:'EURUSD',tf:'H1',side:'BUY',model:'confirmation_bo',entry:1.1,stop:1.09,tp1:null,tp2:1.13,target_sources:[{timeframe:'H4',kind:'KL'}],story_target:1.2,story_target_timeframe:'W',status:'PENDING',cost_note:'Zero-cost paper estimate',note:'Bishop confirmation profile · H4/H3/H2/H1'},
 {id:'bishop:two',strategy:'bishop',strategy_label:'Bishop · Paper',pair:'GBPUSD',tf:'H2',side:'SELL',model:'confirmation_engulfed_oc',entry:1.3,stop:1.31,tp1:null,tp2:1.27,status:'UNKNOWN',cost_note:'Zero-cost paper estimate',note:'Ambiguous H1 candle'}];
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());const reply=json=>route.fulfill({json});
  if(url.hostname==='telegram.org')return route.fulfill({body:'window.Telegram={WebApp:{initData:"",ready(){},expand(){}}}',contentType:'application/javascript'});
  if(url.pathname==='/api/auth/session')return reply({user:{id:42},csrf:'test',auth_method:'browser'});
  if(url.pathname==='/api/settings')return reply({auto_trade:'confirm',kill_switch:'off',pairs:'EURUSD,GBPUSD'});
  if(url.pathname==='/api/settings/schema')return reply({groups:[],settings:[]});
  if(url.pathname==='/api/bishop/recognition')return reply({available:true,markets:[{pair:'EURUSD',checked_at:1,study:{tick_size:'0.00001',flows:[{id:'flow',pair:'EURUSD',tf:'H1',side:'BUY',status:'WAIT_REACTION',bias:{id:42},break:{level_ticks:110000,close_ticks:110020},pool:{price_ticks:110010},level:{price_ticks:110000},timeline:[{stage:'LIQUIDITY_TAKEN',at:'2026-11-06T12:00:00Z'}],plans:[]}],rejected_breaks:[]}}],note:'Recognition study only. No orders.'});
  if(url.pathname==='/api/bishop/rr-study')return reply({available:true,summary:{cohort:1,stop_unresolved:0,paired_closed:1,note:'Zero-cost study',variants:{'1':{wins:1,losses:0,open:0,unknown:0,total_r:1,paired_total_r:1,closed_drawdown_r:0},'2':{wins:0,losses:1,open:0,unknown:0,total_r:-1,paired_total_r:-1,closed_drawdown_r:1},'3':{wins:0,losses:1,open:0,unknown:0,total_r:-1,paired_total_r:-1,closed_drawdown_r:1}}},entries:[]});
  if(url.pathname==='/api/entries')return reply(entries.filter(e=>!url.searchParams.get('strategy')||e.strategy===url.searchParams.get('strategy')));
  if(url.pathname==='/api/entries/summary')return reply({closed:0,wins:0,losses:0,total_r:0,open:1,by_model:{},bishop:{closed:0,wins:0,losses:0,total_r:0,open:1,unknown:1,cost_note:'Zero-cost paper estimates',scope:'Most recent 500 Bishop signals'}});
  if(url.pathname==='/api/bishop/status')return reply({note:'Paper only · H4/H3/H2/H1 · Zero-cost estimates',markets:[{pair:'EURUSD',note:'COMPUTED_UNVALIDATED'},{pair:'US30',note:'Calendar unavailable'}]});
  if(url.pathname.startsWith('/api/'))return reply([]);
  return route.fulfill({path:path.join(root,url.pathname.startsWith('/static/')?url.pathname.slice(8):'index.html')});
 });
 await page.goto('http://slk.test/');await page.locator('[data-tab=entries]').click();
 await page.locator('#entries-list .card').first().waitFor();
 assert.equal(await page.locator('#entries-list .card').count(),3);
 assert.equal(await page.locator('#entries-list .approve').count(),1); // KK only
 assert.equal(await page.locator('#entries-list .card').filter({hasText:'Bishop · Paper'}).locator('.approve').count(),0);
 assert((await page.locator('#entries-summary').textContent()).includes('1 Unknown'));
 assert((await page.locator('#entries-summary').textContent()).includes('Bishop study · 1R / 2R / 3R'));
 assert((await page.locator('#entries-summary').textContent()).includes('Paired R'));
 assert((await page.locator('#entries-summary').textContent()).includes('Bishop recognition study'));
 assert((await page.locator('#entries-summary').textContent()).includes('LIQUIDITY TAKEN'));
 assert.equal(await page.locator('#entries-summary .approve').count(),0);
 await page.locator('#f-estrategy').selectOption('bishop');
 await page.waitForFunction(()=>document.querySelectorAll('#entries-list .card').length===2);
 assert.equal(await page.locator('#entries-list .approve').count(),0);
 assert((await page.locator('#entries-list').textContent()).includes('Ambiguous H1 candle'));
 assert((await page.locator('#entries-list').textContent()).includes('Trade target'));
 assert((await page.locator('#entries-list').textContent()).includes('Legacy: web bias alignment not verified'));
 assert(!(await page.locator('#entries-list').textContent()).includes('TP1'));
 assert((await page.locator('#entries-list').textContent()).includes('Target context'));
 assert((await page.locator('#entries-list').textContent()).includes('Larger story objective'));
 assert((await page.locator('#entries-list').textContent()).includes('1.2'));
 await page.screenshot({path:'/tmp/bishop-entries.png',fullPage:true});
 assert.deepEqual(errors,[]);
 await browser.close();console.log('Bishop/KK source labels, filtering, separate paper summaries, Unknown and no Bishop approval passed');
})().catch(e=>{console.error(e);process.exit(1)});

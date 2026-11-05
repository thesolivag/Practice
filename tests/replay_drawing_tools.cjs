// Run with node tests/replay_drawing_tools.cjs. Exercises production drawing handlers.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../webapp/static/app.js'),'utf8');
const nodes=new Map();function $(id){if(!nodes.has(id))nodes.set(id,{value:'',classList:{remove(){},toggle(){}},addEventListener(){},replaceChildren(){},getContext(){return {measureText(){return {width:50}}}}});return nodes.get(id);}
const ctx={$,Option:function(){},console,setTimeout,window:{addEventListener(){}},document:{addEventListener(){}},chartDrawings:[],chartRedo:[],chartHistory:[],chartSelected:-1,chartPending:null,chartMoving:false,selectReplayStart:false,replayState:{},replayViewport:{interactions(){}},stopReplay(){},redrawChart(){},paintReplayDrawings(){},localReplayInput(){return ''},replayInstant(){return new Date()},chartTransform:{padding:0,w:500,h:500,price:y=>500-y,time:x=>1000+x,x:t=>t-1000,y:p=>500-p}};
vm.createContext(ctx);vm.runInContext(src.slice(src.indexOf('  const drawingNames ='),src.indexOf("  $('#chart-in')")),ctx);
vm.runInContext('drawingPoint=event=>({px:event.clientX,py:event.clientY});',ctx);
function tap(x,y){ctx.placeReplayDrawing({clientX:x,clientY:y});}
function tool(kind){$('#chart-tool').value=kind;ctx.chartPending=null;}
$('#chart-ratio').value='2';$('#drawing-text').value='My note';
for(const kind of ['line','vertical','text','trend','rectangle','fib','long','short']){
 const n=ctx.chartDrawings.length;tool(kind);tap(100,200);
 if(['trend','rectangle','fib','long','short'].includes(kind)){assert.equal(ctx.chartDrawings.length,n);tap(200,kind==='short'?100:300);}
 assert.equal(ctx.chartDrawings.length,n+1,kind);assert.equal(ctx.chartDrawings[n].kind,kind);assert.equal($('#chart-tool').value,'cursor');
}
const long=ctx.chartDrawings.find(d=>d.kind==='long');assert.equal(long.entry,300);assert.equal(long.stop,200);assert.equal(long.target,500);
const short=ctx.chartDrawings.find(d=>d.kind==='short');assert.equal(short.target,100);
tool('long');const n=ctx.chartDrawings.length;tap(100,200);tap(200,100);assert.equal(ctx.chartDrawings.length,n,'wrong-side stop rejected');
tool('vertical');tap(600,200);assert.equal(ctx.chartDrawings.length,n,'outside plot rejected');
const fib=ctx.chartDrawings.find(d=>d.kind==='fib');assert.equal(ctx.drawingHandles(fib).length,2);assert.equal(ctx.hitDrawing(150,250),ctx.chartDrawings.indexOf(fib));
console.log('PASS: eight tools, two-point placement, long/short targets, invalid stop, plot bounds, Fibonacci handles and hit testing');

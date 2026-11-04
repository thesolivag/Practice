/* SLK replay viewport. Lightweight Charts 5.0.8; see vendor LICENSE and NOTICE. */
(() => {
  class ReplayViewport {
    constructor(host, overlay, options) {
      this.overlay=overlay; this.options=options; this.bars=[]; this.key=null;
      const css=getComputedStyle(document.documentElement), color=k=>css.getPropertyValue(k).trim();
      this.chart=LightweightCharts.createChart(host,{autoSize:true,layout:{background:{color:color('--bg')||'#fff'},textColor:color('--text')||'#222',attributionLogo:true},grid:{vertLines:{color:'#8293a718'},horzLines:{color:'#8293a718'}},rightPriceScale:{borderVisible:false,minimumWidth:65},timeScale:{timeVisible:true,secondsVisible:false,lockVisibleTimeRangeOnResize:true,rightOffset:5,borderVisible:false,tickMarkFormatter:(t,type)=>options.tick(t,type)},crosshair:{mode:LightweightCharts.CrosshairMode.Normal},localization:{timeFormatter:t=>options.format(t)},handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true}});
      this.series=this.chart.addSeries(LightweightCharts.CandlestickSeries,{upColor:'#20a06b',downColor:'#de5656',wickUpColor:'#20a06b',wickDownColor:'#de5656',borderVisible:false,priceFormat:{type:'price',precision:5,minMove:.00001}});
      this.chart.timeScale().subscribeVisibleLogicalRangeChange(range=>{this.schedule();if(range&&range.from<12)options.older?.();});
      this.chart.subscribeCrosshairMove(param=>{const b=param.seriesData.get(this.series); if(b&&param.time)options.inspect({...b,time:param.time});else if(this.bars.length)options.inspect(this.bars[this.bars.length-1]);});
      this.chart.subscribeClick(param=>{if(param.time)options.select?.(Number(param.time));});
      this.resize=new ResizeObserver(()=>this.schedule());this.resize.observe(host);
    }
    schedule(){if(this.frame)return;this.frame=requestAnimationFrame(()=>{this.frame=null;this.options.draw();});}
    set(bars,key){
      const changed=key!==this.key, old=this.bars, range=this.chart.timeScale().getVisibleLogicalRange();
      const following=!range||range.to>=old.length-2, oldFirst=old[0]?.time;
      this.bars=bars;this.key=key;
      this.series.setData(bars.map(b=>({time:b.time,open:b.open,high:b.high,low:b.low,close:b.close})));
      if(changed){this.chart.timeScale().setVisibleLogicalRange({from:Math.max(-1,bars.length-100),to:bars.length+4});}
      else if(range){const shift=oldFirst===undefined?0:Math.max(0,bars.findIndex(b=>b.time===oldFirst));this.chart.timeScale().setVisibleLogicalRange(following&&bars.length>old.length&&shift===0?{from:range.from+bars.length-old.length,to:range.to+bars.length-old.length}:{from:range.from+shift,to:range.to+shift});}
      this.schedule();
    }
    transform(){
      const scale=this.chart.timeScale(), bars=this.bars, canvas=this.overlay;
      canvas.width=Math.max(1,Math.round(canvas.clientWidth));canvas.height=Math.max(1,Math.round(canvas.clientHeight));
      const logicalTime=logical=>{if(!bars.length||logical===null)return NaN;const i=Math.floor(logical),j=Math.max(0,Math.min(bars.length-2,i));if(bars.length===1)return bars[0].time;return bars[j].time+(logical-j)*(bars[j+1].time-bars[j].time);};
      const x=time=>{const direct=scale.timeToCoordinate(time);if(direct!==null)return direct;if(!bars.length)return NaN;if(bars.length===1)return scale.logicalToCoordinate(0);let index=bars.findIndex(b=>b.time>=time);index=index<0?bars.length-1:Math.max(1,index);const first=bars[index-1],second=bars[index];return scale.logicalToCoordinate(index-1+(time-first.time)/(second.time-first.time));};
      return {x,y:p=>this.series.priceToCoordinate(p),price:y=>this.series.coordinateToPrice(y),time:x=>logicalTime(scale.coordinateToLogical(x)),w:canvas.width-this.chart.priceScale('right').width(),h:canvas.height-scale.height(),padding:0};
    }
    zoom(factor){const s=this.chart.timeScale(),r=s.getVisibleLogicalRange();if(r){const half=(r.to-r.from)*factor/2,m=(r.from+r.to)/2;s.setVisibleLogicalRange({from:m-half,to:m+half});}}
    pan(direction){const s=this.chart.timeScale(),r=s.getVisibleLogicalRange();if(r){const delta=(r.to-r.from)*direction/3;s.setVisibleLogicalRange({from:r.from+delta,to:r.to+delta});}}
    head(){this.chart.timeScale().scrollToRealTime();}
    fit(){this.chart.timeScale().fitContent();}
    interactions(enabled){this.chart.applyOptions({handleScroll:enabled?{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false}:false,handleScale:enabled});}
    clear(){this.series.setData([]);this.bars=[];this.key=null;this.schedule();}
  }
  window.ReplayViewport=ReplayViewport;
})();

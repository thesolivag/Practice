"""Explain the archived NZDJPY reference clock; no outcome or future candles."""
import json
from pathlib import Path
from dataclasses import asdict
import pandas as pd
from fzasm.data import df_to_candles,resample_ohlc
from fzasm.native_daily import candles_from_native_daily
from fzasm.full_model import FullASMEngine
from fzasm.types import TimeFrame


def main():
    now=pd.Timestamp('2026-11-11T03:00:00Z')
    d=pd.read_csv('evidence/nzdjpy-reference/NZDJPY_M1.csv',index_col=0,parse_dates=True)
    d=d[d.index+pd.Timedelta(minutes=1)<=now]
    native=pd.read_csv('evidence/close-validation/NZDJPY_native_D1.csv',index_col=0,parse_dates=True)
    daily,audit=candles_from_native_daily(native,now)
    if audit['missing_weekday_gaps']:raise ValueError('Unverified native daily gap')
    series={tf:df_to_candles(resample_ohlc(d,rule),TimeFrame(tf)) for tf,rule in
            {'M5':'5min','M10':'10min','M15':'15min','H1':'1h','H2':'2h','H4':'4h'}.items()}
    series['D1']=daily
    engine=FullASMEngine(extra_pairs={'NZDJPY'})
    plan=engine.scan_asset('NZDJPY',series,now)
    report=dict(clock=str(now),signal=plan is not None,plan=asdict(plan) if plan else None,
                review=engine.last_review,diagnostics=dict(engine.diagnostics),
                native_gap_count=len(audit['missing_weekday_gaps']),
                limitation='Single decision-clock check; short intraday archive; not replay or proof of profitability')
    Path('reports/FZ_ASM_FULL_REFERENCE_CHECK.json').write_text(json.dumps(report,indent=2,default=str))
    if plan is None:
        print(json.dumps(report,indent=2,default=str));return
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig,axes=plt.subplots(3,1,figsize=(12,12))
    views=[daily[-16:],series['H1'][-14:],series['M5'][-36:]]
    for ax,bars,title in zip(axes,views,['Native daily context — bearish maps agree','H1 sweep and pre-existing context level','M5 entry plan — pending after03:00UTC']):
        for i,c in enumerate(bars):
            color='#119b83' if c.close>=c.open else '#d94d67'
            ax.vlines(i,c.low,c.high,color=color)
            ax.add_patch(Rectangle((i-.32,min(c.open,c.close)),.64,max(abs(c.open-c.close),.0005),color=color))
        stride=max(1,len(bars)//9)
        ax.set_xticks(range(0,len(bars),stride),[c.timestamp.strftime('%d %H:%M') for c in bars[::stride]],fontsize=8)
        ax.set_title(title,loc='left');ax.grid(alpha=.15)
        ax.set_ylabel('NZDJPY');ax.set_xlabel('UTC candle open')
    axes[0].axhline(plan.take_profit_2,color='#159e85',linestyle='--',label=f'Frozen structural target {plan.take_profit_2:.3f}')
    axes[0].axhline(plan.daily_map.origin_level,color='#b58228',linestyle=':',label=f'Map origin {plan.daily_map.origin_level:.3f}')
    ev=plan.entry_evidence
    axes[1].axhspan(ev['poi_bottom'],ev['poi_top'],alpha=.15,color='#b58228',label='Selected pre-existing H4/H2 level')
    axes[1].axhline(plan.h1_sweep.swept_candle.high,color='#b58228',linestyle=':',label='Previous H1 high swept')
    axes[1].axhline(plan.h1_sweep.swept_candle.low,color='#888888',linestyle=':',label='Previous H1 low standing')
    axes[2].axhline(plan.entry_price,color='#327dd1',linestyle='--',label=f'Limit entry {plan.entry_price:.3f}')
    axes[2].axhline(plan.stop_loss,color='#d94d67',linestyle='--',label=f'SL {plan.stop_loss:.3f} (sweep +3pips)')
    if 'structure_boundary' in ev:
        axes[2].axhline(ev['structure_boundary'],color='#b58228',linestyle=':',label=f'Close-based CHoCH boundary {ev["structure_boundary"]:.3f}')
    for ax in axes:ax.legend(loc='best',fontsize=8)
    fig.suptitle('ASM full-context research v1 — NZDJPY,11 Nov2026,03:00UTC\nActual archived candles; no future candles or assumed fills',fontsize=13)
    fig.tight_layout(rect=(0,.025,1,.95))
    fig.text(.02,.01,'Research interpretation: rules require chart validation. This is a plan, not an executed or profitable trade.',fontsize=10)
    out=Path('evidence/repair-review');out.mkdir(parents=True,exist_ok=True)
    fig.savefig(out/'NZDJPY-full-context.png',dpi=140)
    print(json.dumps(dict(entry=plan.entry_price,stop=plan.stop_loss,target=plan.take_profit_2,route=plan.entry_model.value,rr=plan.risk_reward),indent=2))

if __name__=='__main__':main()

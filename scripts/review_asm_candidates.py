"""Read-only review of frozen outcome artifacts; no price replay or rule fitting."""
import json
from pathlib import Path
import pandas as pd
root=Path('/workspace/fzasm-review/evidence/candidate-review')
configs=[('GBPUSD','h1_av_m5','1R','aligned_map'),('NZDJPY','h1_av','3R','htf_touch'),('AUDJPY','swing_ob','ASIAN_EXTREME','aligned_map')]
summary=[];monthly=[];checks=[]
for pair,policy,target,feature in configs:
    df=pd.read_csv(root/pair/'annotated_outcomes.csv')
    base=df[(df.entry_policy==policy)&(df.target==target)&df.context_valid.eq(True)]
    assert not base.signal_id.duplicated().any()
    selected=base[base[feature].eq(True)].copy()
    selected.to_csv(root/pair/'selected_trades.csv',index=False)
    for _,r in selected.iterrows():
        at=pd.Timestamp(r.timestamp); maps=json.loads(r.map_evidence);levels=json.loads(r.level_evidence)
        assert all(pd.Timestamp(m['known_at'])<=at for m in maps)
        if feature=='htf_touch':
            assert r.sweep_match_count==1 and levels
            assert all(pd.Timestamp(l['known_at'])<=pd.Timestamp(r.sweep_at) for l in levels)
        e=json.loads(r.entry_evidence)
        assert abs(abs(float(e['sweep_extreme'])-r.stop_price)-float(e['study_stop_buffer_price']))<1e-7
        if r.status=='CLOSED':
            assert pd.Timestamp(r.fill_bar_open)>=at
            assert pd.Timestamp(r.exit_time)>=pd.Timestamp(r.fill_bar_open)
            if target in ('1R','3R'):assert abs(abs(r.target_price-r.entry_price)/abs(r.entry_price-r.stop_price)-int(target[0]))<1e-6
    checks.append(dict(pair=pair,selected_signals=len(selected),timestamp_stop_target_checks='PASS'))
    for phase in ('discovery','validation'):
        for present in (True,False):
            g=base[(base.phase==phase)&base[feature].eq(present)].copy()
            c=g[(g.status=='CLOSED')&g.result_r.notna()].copy()
            if phase=='discovery':c=c[pd.to_datetime(c.exit_time,utc=True)<pd.Timestamp('2026-07-01T00:00Z')]
            c['net']=c.result_r-.08
            top=c.net.sort_values(ascending=False)
            equity=c.groupby('exit_time').net.sum().sort_index().cumsum()
            dd=float((equity.cummax().clip(lower=0)-equity).max()) if len(equity) else None
            summary.append(dict(pair=pair,phase=phase,feature_present=present,signals=len(g),resolved=len(c),unknown=int((g.status=='UNKNOWN').sum()),unfilled=int((g.status=='UNFILLED').sum()),wins=int((c.net>0).sum()),net_r=c.net.sum(),mean_net_r=c.net.mean(),best_trade=top.iloc[0] if len(top) else None,without_best=c.net.sum()-top.head(1).sum(),without_best3=c.net.sum()-top.head(3).sum(),drawdown_r=dd,net_at_016_cost=(c.result_r-.16).sum(),net_at_025_cost=(c.result_r-.25).sum()))
            if present:
                for month,mg in g.groupby(g.timestamp.str[:7]):
                    mc=c[c.timestamp.str[:7]==month]
                    monthly.append(dict(pair=pair,phase=phase,month=month,signals=len(mg),resolved=len(mc),unknown=int((mg.status=='UNKNOWN').sum()),unfilled=int((mg.status=='UNFILLED').sum()),wins=int((mc.net>0).sum()),net_r=mc.net.sum(),best_trade=mc.net.max() if len(mc) else None))
                c.sort_values('net',ascending=False).to_csv(root/pair/(phase+'_resolved_ranked.csv'),index=False)
(root/'checks.json').write_text(json.dumps(checks,indent=2))
pd.DataFrame(summary).to_csv(root/'robustness.csv',index=False)
pd.DataFrame(monthly).to_csv(root/'monthly.csv',index=False)
print(pd.DataFrame(summary).query("phase=='validation' and feature_present").to_string(index=False))
print(pd.DataFrame(monthly).query("phase=='validation'").to_string(index=False))
print(checks)

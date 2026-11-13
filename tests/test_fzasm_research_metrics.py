import pandas as pd
from fzasm.research_metrics import metrics

def test_cost_drawdown_streak_and_unknown_accounting():
 rows=pd.DataFrame([dict(status=s,result_r=r,entry_price=1.1,stop_price=1.099,exit_time=str(i),signal_id=str(i)) for i,(s,r) in enumerate([('CLOSED',2),('CLOSED',-1),('CLOSED',-1),('CLOSED',4),('UNKNOWN',None),('UNFILLED',None)])])
 m=metrics(rows,1,.0001)
 assert abs(m['result_r']-3.6)<1e-8
 assert abs(m['resolved_exit_drawdown_r']-2.2)<1e-8
 assert m['max_resolved_losing_streak']==2
 assert m['unknown']==1 and m['unfilled']==1 and m['resolved']==4

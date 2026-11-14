import json, math, hashlib, csv, pathlib, datetime, random, statistics
ROOT=pathlib.Path(__file__).parent
VARIANTS=['reversal_0.005','reversal_0.01','continuation_0.005','continuation_0.01','trend_100','trend_200']
def rows():
 b=(ROOT/'data/spy.json').read_bytes()
 assert hashlib.sha256(b).hexdigest()=='e4e49bb5d439b63dd201b6f2285221fa9abf2ff3783920edf89e9a8ee1f9f10e'
 r=json.loads(b)['chart']['result'][0]; q=r['indicators']['quote'][0]
 # Do not calculate final-period statistics or inspect final bars in this batch.
 out=[]
 for i,t in enumerate(r['timestamp']):
  d=datetime.datetime.fromtimestamp(t,datetime.timezone.utc).date().isoformat()
  if d>='2022-01-01': continue
  a={k:q[k][i] for k in ['open','high','low','close','volume']};a['date']=d
  assert all(a[k] is not None and a[k]>0 for k in ['open','high','low','close','volume'])
  assert a['low']<=min(a['open'],a['close'])<=max(a['open'],a['close'])<=a['high']
  out.append(a)
 assert len({a['date'] for a in out})==len(out)
 assert [a['date'] for a in out]==sorted(a['date'] for a in out)
 import exchange_calendars as xc
 expected={d.date().isoformat() for d in xc.get_calendar('XNYS',start='2010-01-01',end='2021-12-31').sessions}
 assert {a['date'] for a in out}==expected, 'Missing or unexpected exchange sessions'
 assert not r.get('events',{}).get('splits'), 'Split handling must be audited first'
 return out

def signal(a,i,v):
 kind,p=v.split('_');p=float(p)
 if i<2:return False
 if kind=='trend':
  n=int(p)
  return i>=n and a[i-1]['close']>sum(x['close'] for x in a[i-n:i])/n
 change=a[i-1]['close']/a[i-2]['close']-1
 return change<=-p if kind=='reversal' else change>=p

def metrics(ds,rs,trades):
 eq=peak=1.;dd=0.;streak=maxstreak=0;monthly={};annual={}
 for d,r,t in zip(ds,rs,trades):
  eq*=1+r;peak=max(peak,eq);dd=max(dd,1-eq/peak)
  monthly[d[:7]]=monthly.get(d[:7],1)*(1+r)
  annual[d[:4]]=annual.get(d[:4],1)*(1+r)
  if t:streak=streak+1 if r<0 else 0;maxstreak=max(maxstreak,streak)
 active=[r for r,t in zip(rs,trades) if t];top=sorted(active,reverse=True)[:5]
 m=[x-1 for x in monthly.values()];rng=random.Random(20261114);boot=[]
 for _ in range(5000):
  sample=[]
  while len(sample)<len(m):
   j=rng.randrange(len(m));sample.extend(m[(j+k)%len(m)] for k in range(3))
  boot.append(statistics.mean(sample[:len(m)]))
 boot.sort();sd=statistics.stdev(rs)
 return dict(total_return=eq-1,cagr=eq**(252/len(rs))-1,sharpe=statistics.mean(rs)/sd*math.sqrt(252) if sd else 0,max_drawdown=dd,trades=sum(trades),expectancy=statistics.mean(active) if active else 0,max_losing_streak=maxstreak,session_exposure=sum(trades)/len(rs),approx_clock_exposure=sum(trades)*6.5/(len(rs)*24*365.25/252),positive_years=sum(v>1 for v in annual.values()),annual={k:v-1 for k,v in annual.items()},monthly={k:v-1 for k,v in monthly.items()},top5_net_sum=sum(top),net_sum=sum(active),net_sum_without_top5=sum(active)-sum(top),top5_share_of_net_sum=sum(top)/sum(active) if sum(active) else None,monthly_mean_ci95=[boot[124],boot[4874]])
def passes(m,stress):
 return m['trades']>=100 and m['sharpe']>=.7 and m['max_drawdown']<=.2 and m['positive_years']>=3 and m['net_sum_without_top5']>0 and stress['total_return']>0 and m['monthly_mean_ci95'][0]>0

def run():
 a=rows();results={};ledger=[]
 selected=None
 for part,lo,hi in [('development','2010','2018'),('validation','2018','2022')]:
  if part=='validation':
   selected=max(VARIANTS,key=lambda v:results[v]['development']['net']['sharpe'])
  for v in VARIANTS:
   results.setdefault(v,{})
   ix=[i for i,x in enumerate(a) if lo<=x['date']<hi];ds=[a[i]['date'] for i in ix];ts=[signal(a,i,v) for i in ix];gr=[a[i]['close']/a[i]['open']-1 if t else 0 for i,t in zip(ix,ts)]
   # Exact adverse price adjustments, commission charged on each side.
   def net(cost):
    friction=cost*.75/2;commission=cost*.25/2
    return [((1+g)*(1-friction)*(1-commission)/((1+friction)*(1+commission))-1) if t else 0 for g,t in zip(gr,ts)]
   nr=net(.0004);sr=net(.0008)
   res={k:metrics(ds,r,ts) for k,r in [('gross',gr),('net',nr),('stress',sr)]};res['passes']=passes(res['net'],res['stress']);results[v][part]=res
   ledger.extend(dict(variant=v,partition=part,date=d,trade=int(t),gross=g,net=n,stress=s) for d,t,g,n,s in zip(ds,ts,gr,nr,sr))
 # Selection depends exclusively on development.
 assert selected is not None
 family=selected.split('_')[0];eligible=all(results[v]['validation']['passes'] for v in VARIANTS if v.startswith(family+'_'))
 out={'data_rows_development_validation':len(a),'selected_from_development':selected,'selected_family_validation_pass':eligible,'final_test':'NOT RUN — requires validation gates and independent audit','results':results}
 (ROOT/'results').mkdir(exist_ok=True)
 (ROOT/'results/summary.json').write_text(json.dumps(out,indent=2))
 with (ROOT/'results/daily.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=ledger[0]);w.writeheader();w.writerows(ledger)
 print(json.dumps({k:v for k,v in out.items() if k!='results'}))
 for v in VARIANTS:
  for p in ['development','validation']:
   m=results[v][p]['net'];print(v,p,{k:m[k] for k in ['total_return','sharpe','trades','max_drawdown']},'pass',results[v][p]['passes'])
if __name__=='__main__':run()

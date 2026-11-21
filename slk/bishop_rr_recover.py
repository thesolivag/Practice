"""Owner-only verified M1 recovery of frozen mini-app study outcomes."""
import json,os,time,hashlib
from pathlib import Path
from copy import deepcopy
from collections import Counter
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from decimal import Decimal
from bishop.v2.types import Instrument,Bar,utc,jsonable
from bishop.v2.simulation import simulate,Costs
from slk.bishop_paper import thaw_order,history_hash
from slk.bishop_unknown_jobs import MinuteLoader,censor_event
from slk.bishop_rr import summary

TERMINAL={'WIN','LOSS','BREAK_EVEN','EXPIRED','CANCELLED','REPLACED','CENSORED'}

def recover(study,bars,minute_loader):
    original=deepcopy(study);new=deepcopy(study);audits=[]
    inst=Instrument(**study['instrument']);end=utc(study['history_to'])
    if study.get('status')=='UNKNOWN':return new,[{'reason':'STUDY_HISTORY_QUARANTINE_REQUIRES_SEPARATE_REVIEW'}]
    if history_hash(bars,thaw_order(study['source_order']),end)!=study.get('history_hash'):
        return new,[{'reason':'ORIGINAL_H1_HISTORY_HASH_MISMATCH'}]
    for rr,v in study.get('variants',{}).items():
        if v['observation']['outcome']!='CENSORED':continue
        o=thaw_order(v['order']);actions=[{**a,'order_id':o.id} for a in study.get('source_actions',[])]
        costs=Costs(**study['costs'])
        baseline=simulate((o,),bars,inst,costs,end,actions,calendar=study['calendar'])
        if jsonable(baseline['observations'][0])!=v['observation']:
            audits.append({'rr':rr,'reason':'ORIGINAL_OBSERVATION_NOT_REPRODUCED'});continue
        event=censor_event(baseline);freeze=event.available_at if event else end
        fine=[];failed=None
        try:
            for b in bars:
                if b.end>o.available_at and b.available_at<=end:fine.extend(minute_loader(b))
        except Exception as exc:
            known={'MISSING_OR_DUPLICATE_MINUTES','M1_H1_PRICE_MISMATCH','BROKER_H1_PRICE_MISMATCH','BROKER_FETCH_UNAVAILABLE','JOB_TIME_BUDGET','OFF_GRID_MINUTE'}
            failed=str(exc) if str(exc) in known else 'MINUTE_EVIDENCE_UNAVAILABLE'
        if failed:audits.append({'rr':rr,'reason':failed});continue
        result=simulate((o,),fine,inst,costs,end,actions,calendar=study['calendar'])
        obs=jsonable(result['observations'][0]);fill=obs.get('fill_window')
        reason=obs.get('censor_reason')
        if obs['outcome'] not in ('WIN','LOSS','BREAK_EVEN'):
            audits.append({'rr':rr,'reason':reason or 'NOT_PROVEN_CLOSED','first_censor':jsonable(censor_event(result))});continue
        if not fill or utc(fill['end'])>freeze:
            audits.append({'rr':rr,'reason':'PENDING_MANAGEMENT_AFTER_ORIGINAL_CENSOR_UNAVAILABLE'});continue
        events=jsonable(result['events'])
        new['variants'][rr]={**v,'observation':obs,
            'filled_at':next((e['clock']['available_at'] for e in events if e['kind']=='ORDER_FILLED'),None),
            'closed_at':next((e['clock']['available_at'] for e in reversed(events) if e['kind'].startswith('POSITION_')),None),
            'm1_recovery':{'original_observation':v['observation'],'events':events,'original_censor':jsonable(event)}}
        audits.append({'rr':rr,'reason':'RESOLVED','outcome':obs['outcome'],'gross_r':obs['net_r']})
    assert all(new[k]==original[k] for k in ('source_order','stop_proof','instrument','costs','calendar','version'))
    assert all(v['order']==original['variants'][rr]['order'] for rr,v in new['variants'].items())
    if new!=original:
        new['status']='COMPLETE' if all(v['observation']['outcome'] in TERMINAL for v in new['variants'].values()) else 'TRACKING'
        new['m1_recovery_run']=os.environ.get('GITHUB_RUN_ID','local-test')
    return new,audits


def fetch_h1(study):
    from slk import db,jobs
    from slk.bishop_year_jobs import research_feed_lock
    from ctrader.client import CTraderClient
    from ctrader import tokens
    inst=Instrument(**study['instrument'])
    if not inst.source_id.startswith('ctrader:'):raise ValueError('UNSUPPORTED_PRIMARY_PROVIDER')
    start=utc(study['source_order']['clock']['available_at']);end=utc(study['history_to'])
    with research_feed_lock(db,wait=240):
        with jobs.feed_lock(db,wait=0,name='slk_personal_feed') as acquired:
            if not acquired:raise ValueError('BROKER_FETCH_UNAVAILABLE')
            with CTraderClient(env='demo',settings=tokens.default_settings(strict=True),timeout=15) as client:
                client.get_symbols([inst.symbol]);rows=client.trendbar_rows(inst.symbol,'H1',start,end)
    bars=[]
    for r in rows:
        at=datetime.fromtimestamp(int(r[0]),timezone.utc);close=at+timedelta(hours=1)
        if at<start or close>end:continue
        bars.append(Bar(inst.symbol,'H1',at,close,*(inst.to_ticks(Decimal(str(v))) for v in r[1:5]),close,inst.source_id,'0'))
    return tuple(sorted(bars,key=lambda b:b.start))


def commit(db,uid,old,new):
    if new==old:return 'UNCHANGED'
    conn=db.connect()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute('SELECT payload FROM bishop_rr_studies WHERE user_id=%s AND study_id=%s FOR UPDATE',(uid,old['id']))
            found=cur.fetchone()
            if not found or json.loads(found['payload'])!=old:
                conn.rollback();return 'CONCURRENT_CHANGE_NOT_APPLIED'
            cur.execute('UPDATE bishop_rr_studies SET payload=%s,updated_at=%s WHERE user_id=%s AND study_id=%s',
                (json.dumps(new),int(time.time()),uid,old['id']))
        conn.commit();return 'APPLIED'
    except Exception:
        conn.rollback();raise
    finally:conn.close()


def main():
    from slk import db
    if not os.environ.get('TELEGRAM_CHAT_ID'):raise RuntimeError('Owner identity secret required')
    uid=int(os.environ['TELEGRAM_CHAT_ID']);out=Path('reports/rr-recovery');out.mkdir(parents=True,exist_ok=True)
    try:raw=db.query('SELECT payload FROM bishop_rr_studies WHERE user_id=%s ORDER BY created_at',(uid,))
    except Exception:raise RuntimeError('Study query failed; credentials withheld') from None
    all_rows=[json.loads(r['payload']) for r in raw]
    selected=[s for s in all_rows if s.get('status')=='UNKNOWN' or any(v['observation']['outcome']=='CENSORED' for v in s.get('variants',{}).values())]
    (out/'before-summary.json').write_text(json.dumps(summary(all_rows),indent=2))
    (out/'original-studies.json').write_text(json.dumps(selected))
    deadline=time.monotonic()+45*60;loaders={};audits=[]
    for s in selected:
        result={'study_id':s['id'],'pair':s['pair']}
        try:
            if time.monotonic()>deadline:raise ValueError('JOB_TIME_BUDGET')
            bars=fetch_h1(s);inst=Instrument(**s['instrument'])
            if s['pair'] not in loaders:
                loaders[s['pair']]=MinuteLoader(s['pair'],replace(inst,venue='ctrader'),out/'minute-evidence'/s['pair'],deadline)
            new,detail=recover(s,bars,loaders[s['pair']]);result['variants']=detail
            result['write']=commit(db,uid,s,new)
            (out/(s['id']+'-evidence.json')).write_text(json.dumps({'h1':jsonable(bars),'before':s,'after':new,'audit':result},default=str))
        except Exception as exc:
            result['reason']=str(exc) if str(exc) in ('JOB_TIME_BUDGET','UNSUPPORTED_PRIMARY_PROVIDER','BROKER_FETCH_UNAVAILABLE') else 'RECOVERY_UNAVAILABLE'
        audits.append(result);(out/'audit.json').write_text(json.dumps(audits,indent=2))
        print(json.dumps({'processed':len(audits),'selected':len(selected),'write':result.get('write','NOT_APPLIED')}),flush=True)
    fresh=[json.loads(r['payload']) for r in db.query('SELECT payload FROM bishop_rr_studies WHERE user_id=%s',(uid,))]
    (out/'after-summary.json').write_text(json.dumps(summary(fresh),indent=2))
    reasons=Counter(v.get('reason') for a in audits for v in a.get('variants',[{'reason':a.get('reason')}]))
    (out/'REPORT.md').write_text('# Mini-app M1 recovery\n\nSelected studies:'+str(len(selected))+'\n\n'+json.dumps(dict(reasons),indent=2)+'\n\nOnly hash-matched, reproduced, proven closed outcomes applied with per-record compare-and-swap. Original observations and price evidence retained. Remaining unknowns are not assigned wins or losses.\n')

if __name__=='__main__':main()

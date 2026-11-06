"""Isolated paired 1R/2R/3R paper study. Never changes baseline or sends alerts."""
import json
from decimal import Decimal,ROUND_CEILING
from datetime import datetime,timezone
VERSION='confirmation_episode_rr_v1'
SCHEMA='''CREATE TABLE IF NOT EXISTS bishop_rr_studies (
 user_id BIGINT NOT NULL, study_id VARCHAR(64) NOT NULL, pair VARCHAR(16) NOT NULL,
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, payload MEDIUMTEXT NOT NULL,
 PRIMARY KEY(user_id,study_id), KEY ix_rr_user_pair(user_id,pair,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''


def logical_stop(setup, bars, instrument, buffer_units=Decimal('0.5')):
    """Declared research rule: current confirmation episode plus nearby protection.

    BO/nonadjacent OC episode starts at the currently selected KL reaction, not
    the older first liquidity take. Adjacent engulf keeps its own pattern pair.
    Standing-extreme protects its reference/sweep pair. Unmapped proof is held.
    """
    from bishop.v2.types import utc
    d=setup.get('details',{});model=setup['model'];at=utc(setup['clock']['available_at'])
    known=[b for b in bars if b.instrument==setup['instrument'] and b.tf==setup['tf'] and b.complete and b.available_at<=at]
    by_id={b.id:b for b in known}
    ids=list(d.get('confirmation_protection_bar_ids') or d.get('study_pattern_bar_ids') or ())
    if model=='confirmation_standing_extreme':
        current=[b for b in known if b.end==at]
        ids=[d.get('reference_bar_id')]+[b.id for b in current]
    allowed={'confirmation_bo','confirmation_sweep_bos','confirmation_engulfed_oc','oc_break_retest','engulf_av_retest','engulf_irl_retest','confirmation_standing_extreme'}
    if model not in allowed or not ids or any(i not in by_id for i in ids):
        return {'status':'UNRESOLVED','reason':'Current confirmation candle evidence unavailable','version':VERSION}
    anchors=[by_id[i] for i in ids];segments={b.segment_id for b in anchors}
    if len(segments)!=1:return {'status':'UNRESOLVED','reason':'Confirmation crosses a data gap','version':VERSION}
    first=min(b.start for b in anchors);last=max(b.end for b in anchors)
    episode=[b for b in known if b.start>=first and b.end<=last]
    from bishop.v2.aggregation import expected_slots
    expected=set(expected_slots(first,last,'H1',instrument.calendar_id))
    covered={t for b in episode for t in expected_slots(b.start,b.end,'H1',instrument.calendar_id)}
    if expected-covered:
        return {'status':'UNRESOLVED','reason':'Missing candles within confirmation episode','version':VERSION}
    if any(b.segment_id not in segments for b in episode):
        return {'status':'UNRESOLVED','reason':'Confirmation crosses a data gap','version':VERSION}
    sign=1 if setup['side']=='BUY' else -1;entry=setup['entry_ticks']
    objects=[(b.id,b.low_ticks if sign==1 else b.high_ticks,'current_pattern_wick') for b in episode]
    # Keep already-qualified nearby objects; never remove them to improve R:R.
    objects += [tuple(o) for o in d.get('protected_objects',[]) if o[2]=='nearby_structure_or_liquidity_OUR_CHOICE']
    if any(o[2]=='active_range_protected_wick' for o in d.get('protected_objects',[])):
        return {'status':'UNRESOLVED','reason':'Linked range protection needs current-pattern mapping','version':VERSION}
    objects=[o for o in objects if sign*(entry-o[1])>0]
    if not objects:return {'status':'UNRESOLVED','reason':'No protective price behind entry','version':VERSION}
    boundary=(min if sign==1 else max)(o[1] for o in objects)
    pad=max(1,int(instrument.unit_ticks(buffer_units).to_integral_value(rounding=ROUND_CEILING)))
    return {'status':'READY','version':VERSION,'stop_ticks':boundary-sign*pad,'boundary_ticks':boundary,
            'buffer_ticks':pad,'buffer_units':str(buffer_units),'bar_ids':[b.id for b in episode],
            'protected_objects':objects,'rule':'Current confirmation episode + nearby protection; study hypothesis, not teacher-certified'}


def make_study(row, bars, now):
    from bishop.v2.types import Instrument,stable_id
    inst=Instrument(**row['instrument']);s=row['setup'];proof=logical_stop(s,bars,inst)
    o=row['order'];ident=stable_id('rr_study',o['id'],VERSION)
    return {'id':ident,'version':VERSION,'source_order_id':o['id'],'pair':o['instrument'],'tf':o['tf'],
            'side':o['side'],'model':o['model'],'created_at':o['clock']['available_at'],
            'enrolled_at':now,'source_order':o,'source_baseline_observation':row['observation'],
            'instrument':row['instrument'],'calendar':row['calendar'],'costs':row['costs'],
            'web_bias':row.get('web_bias'),'stop_proof':proof,'variants':{},'status':proof['status']}


def evaluate(study, feed, now, source=None):
    from bishop.v2.types import Order,Clock,Instrument,jsonable,utc
    from bishop.v2.simulation import simulate,Costs
    from slk.bishop_paper import history_hash
    study=dict(study)
    if source:study['source_baseline_observation']=source['observation']
    if study['stop_proof']['status']!='READY' or study.get('status')=='COMPLETE':return study
    o=study['source_order'];inst=Instrument(**study['instrument']);at=utc(now)
    if inst!=feed['instrument']:return {**study,'status':'UNKNOWN','reason':'Source metadata changed'}
    base=Order(**{**o,'clock':Clock(**o['clock'])})
    if study.get('history_hash') and history_hash(feed['bars'],base,utc(study['history_to']))!=study['history_hash']:
        return {**study,'status':'UNKNOWN','reason':'Previously observed candles changed'}
    if not feed['bars'] or base.available_at<feed['bars'][0].start:
        return {**study,'status':'UNKNOWN','reason':'Active history unavailable'}
    if study.get('status')=='UNKNOWN':return study
    entry=o['entry_ticks'];stop=study['stop_proof']['stop_ticks'];risk=abs(entry-stop);sign=1 if o['side']=='BUY' else -1
    variants={}
    actions=source.get('actions',[]) if source else study.get('source_actions',[])
    for rr in (1,2,3):
        key=str(rr);prior=study.get('variants',{}).get(key)
        if prior and prior['observation']['outcome'] in ('WIN','LOSS','BREAK_EVEN','EXPIRED','CANCELLED','REPLACED','CENSORED'):
            variants[key]=prior;continue
        order=Order(**{**o,'id':study['id']+'_r'+key,'stop_ticks':stop,'target_ticks':entry+sign*risk*rr,'clock':Clock(**o['clock'])})
        mapped=[{**a,'order_id':order.id} for a in actions]
        result=simulate((order,),feed['bars'],inst,Costs(**study['costs']),at,mapped,calendar=study['calendar'])
        obs=jsonable(result['observations'][0]);events=jsonable(result['events'])
        variants[key]={'order':jsonable(order),'observation':obs,
            'filled_at':next((e['clock']['available_at'] for e in events if e['kind']=='ORDER_FILLED'),None),
            'closed_at':next((e['clock']['available_at'] for e in reversed(events) if e['kind'].startswith('POSITION_') and obs['outcome'] in ('WIN','LOSS','BREAK_EVEN')),None)}
    complete=all(v['observation']['outcome'] in ('WIN','LOSS','BREAK_EVEN','EXPIRED','CANCELLED','REPLACED','CENSORED') for v in variants.values())
    return {**study,'variants':variants,'status':'COMPLETE' if complete else 'TRACKING','source_actions':actions,'history_to':now,
            'history_hash':history_hash(feed['bars'],base,at)}


def compute(rows, existing, feed, now, since, enabled=True):
    from bishop.v2.aggregation import aggregate
    from bishop.v2.types import utc
    sources={r['order']['id']:r for r in rows};studies={r['id']:r for r in existing};frames={}
    if enabled:
        for row in rows:
            if utc(row['order']['clock']['available_at'])<utc(since):continue
            if any(s['source_order_id']==row['order']['id'] for s in studies.values()):continue
            tf=row['order']['tf']
            if tf not in frames:frames[tf]=aggregate(feed['bars'],tf,feed['instrument'],now,calendar=feed['manifest']['calendar'])['bars']
            s=make_study(row,frames[tf],now);studies[s['id']]=s
    return [evaluate(s,feed,now,sources.get(s['source_order_id'])) for s in studies.values()]


class Repository:
    def __init__(self,db):self.db=db
    def apply_schema(self):self.db.execute(SCHEMA)
    def rows(self,uid,pair):
        recent=self.db.query('SELECT payload FROM bishop_rr_studies WHERE user_id=%s AND pair=%s ORDER BY created_at DESC LIMIT 500',(int(uid),pair))
        active=self.db.query("SELECT payload FROM bishop_rr_studies WHERE user_id=%s AND pair=%s AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.status')) IN ('READY','TRACKING')",(int(uid),pair))
        rows=[json.loads(r['payload']) for r in (*recent,*active)]
        return list({r['id']:r for r in rows}.values())
    def persist(self,uid,rows,stamp):
        conn=self.db.connect()
        try:
            conn.begin()
            with conn.cursor() as cur:
                for r in rows:
                    cur.execute('SELECT payload,updated_at FROM bishop_rr_studies WHERE user_id=%s AND study_id=%s FOR UPDATE',(int(uid),r['id']))
                    found=cur.fetchone()
                    if found:
                        if int(found['updated_at'])>stamp:continue
                        old=json.loads(found['payload'])
                        if any(old.get(k)!=r.get(k) for k in ('source_order','stop_proof','version','instrument','costs','calendar')):
                            raise ValueError('Frozen study geometry/evidence cannot change')
                        if any(v['order']!=r.get('variants',{}).get(k,{}).get('order') for k,v in old.get('variants',{}).items()):
                            raise ValueError('Frozen study variant cannot change')
                    created=int(datetime.fromisoformat(r['created_at']).timestamp())
                    cur.execute('INSERT INTO bishop_rr_studies(user_id,study_id,pair,created_at,updated_at,payload) VALUES(%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload),updated_at=VALUES(updated_at)',
                        (int(uid),r['id'],r['pair'],created,stamp,json.dumps(r)))
            conn.commit()
        except Exception:conn.rollback();raise
        finally:conn.close()


def summary(rows):
    total=len(rows);eligible=[r for r in rows if r['stop_proof']['status']=='READY']
    result={'version':VERSION,'cohort':total,'stop_unresolved':total-len(eligible),'variants':{},
            'note':'Independent full exits on the same issued entries. Zero-cost paper estimates; study stop rule is experimental. Unknown is not a win/loss.'}
    paired=[s for s in eligible if s.get('status')!='UNKNOWN' and all(s.get('variants',{}).get(k,{}).get('observation',{}).get('outcome') in ('WIN','LOSS','BREAK_EVEN') for k in ('1','2','3'))]
    result['paired_closed']=len(paired)
    for rr in ('1','2','3'):
        values=[];wins=losses=unknown=pending=expired=0;closed=[]
        for s in eligible:
            v=s.get('variants',{}).get(rr,{});o=v.get('observation',{})
            outcome=o.get('outcome')
            if s.get('status')=='UNKNOWN' or outcome=='CENSORED':unknown+=1;continue
            if outcome in ('WIN','LOSS','BREAK_EVEN') and o.get('net_r') is not None:
                value=float(o['net_r']);values.append(value);wins+=outcome=='WIN';losses+=outcome=='LOSS';closed.append((v.get('closed_at') or '',s['id'],value))
            elif outcome in ('EXPIRED','CANCELLED','REPLACED'):expired+=1
            else:pending+=1
        equity=peak=drawdown=0.
        # Batch simultaneous closes to avoid arbitrary order-ID drawdown ordering.
        batches={}
        for when,_,v in closed:batches[when]=batches.get(when,0)+v
        for when in sorted(batches):equity+=batches[when];peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
        result['variants'][rr]={'closed':len(values),'wins':wins,'losses':losses,'unknown':unknown,'open':pending,'expired_or_cancelled':expired,
            'win_rate':round(100*wins/len(values),1) if values else None,'total_r':round(sum(values),3),'mean_r':round(sum(values)/len(values),3) if values else None,'closed_drawdown_r':round(drawdown,3),'paired_total_r':round(sum(float(s['variants'][rr]['observation']['net_r']) for s in paired),3)}
    return result



def report(db,uid):
    # Full-history statistics read only compact outcome fields, not large proofs.
    parts=[]
    for rr in ('1','2','3'):
        path='$.variants."'+rr+'"'
        parts.append("'"+rr+"',JSON_OBJECT('observation',JSON_OBJECT('outcome',JSON_EXTRACT(payload,'"+path+".observation.outcome'),'net_r',JSON_EXTRACT(payload,'"+path+".observation.net_r')),'closed_at',JSON_EXTRACT(payload,'"+path+".closed_at'))")
    sql="SELECT study_id,JSON_UNQUOTE(JSON_EXTRACT(payload,'$.status')) AS study_status,JSON_UNQUOTE(JSON_EXTRACT(payload,'$.stop_proof.status')) AS stop_status,JSON_OBJECT("+','.join(parts)+") AS compact FROM bishop_rr_studies WHERE user_id=%s"
    rows=db.query(sql,(int(uid),))
    compact=[{'id':r['study_id'],'status':r['study_status'],'stop_proof':{'status':r['stop_status']},'variants':json.loads(r['compact'])} for r in rows]
    latest=[json.loads(r['payload']) for r in db.query('SELECT payload FROM bishop_rr_studies WHERE user_id=%s ORDER BY created_at DESC LIMIT 50',(int(uid),))]
    return summary(compact),latest

def scan(budget=90,timeout=12):
    """Separate bounded job after baseline scan; study failure cannot undo baseline."""
    import time,subprocess,sys
    from slk import db,settings,tenancy
    from slk.bishop_paper import iso
    now=datetime.now(timezone.utc);stamp=int(now.timestamp());deadline=time.monotonic()+budget
    repo=Repository(db);repo.apply_schema();done=failed=deferred=0
    users=sorted({tenancy.owner_id(),*(int(r['user_id']) for r in db.query('SELECT user_id FROM app_users'))})
    cursor=int(db.get_setting('bishop_rr_user_cursor','0') or '0');users=[u for u in users if u>cursor]+[u for u in users if u<=cursor]
    for uid in users:
        if time.monotonic()+timeout+2>=deadline:break
        with tenancy.scope(uid):
            saved=db.get_settings();vals=settings.load(saved);since=int(saved.get('bishop_rr_v1_since') or stamp)
            if not saved.get('bishop_rr_v1_since') or not vals['bishop_rr_study']:
                since=stamp;db.set_setting('bishop_rr_v1_since',str(stamp))
            pair_cursor=saved.get('bishop_rr_pair_cursor','')
        pairs=sorted(vals['pairs'] or (settings.PAIRS if uid==tenancy.owner_id() else tenancy.STARTER['pairs'].split(',')))
        pairs=[p for p in pairs if p>pair_cursor]+[p for p in pairs if p<=pair_cursor]
        for pair in pairs:
            if time.monotonic()+timeout+2>=deadline:deferred+=1;break
            sources=[json.loads(r['payload']) for r in db.query('SELECT payload FROM bishop_app_entries WHERE user_id=%s AND pair=%s ORDER BY created_at DESC LIMIT 500',(uid,pair))]
            existing=repo.rows(uid,pair)
            missing={r['source_order_id'] for r in existing if r.get('status') in ('READY','TRACKING')}-{r['order']['id'] for r in sources}
            if missing:
                slots=','.join(['%s']*len(missing))
                sources.extend(json.loads(r['payload']) for r in db.query('SELECT payload FROM bishop_app_entries WHERE user_id=%s AND pair=%s AND signal_id IN ('+slots+')',(uid,pair,*sorted(missing))))
            if not sources and not existing:continue
            payload={'pair':pair,'now':now.isoformat(),'since':iso(since),'enabled':vals['bishop_rr_study'],'sources':sources,'existing':existing}
            try:
                child=subprocess.run([sys.executable,'-m','slk.bishop_rr','--compute'],input=json.dumps(payload),text=True,capture_output=True,timeout=timeout,check=True)
                result=json.loads(child.stdout)
                if 'error' in result:raise ValueError('Study worker unavailable')
                repo.persist(uid,result['studies'],stamp);done+=1
            except Exception:failed+=1
            with tenancy.scope(uid):db.set_setting('bishop_rr_pair_cursor',pair)
        db.set_setting('bishop_rr_user_cursor',str(uid))
    print(json.dumps({'study':VERSION,'markets_ok':done,'unavailable':failed,'deferred':deferred,'paper_only':True}))
    return 0


def main():
    import sys
    if '--compute' in sys.argv:
        try:
            from slk.bishop_paper import feed_from_store
            p=json.load(sys.stdin);feed=feed_from_store(p['pair'],p['now'])
            print(json.dumps({'studies':compute(p['sources'],p['existing'],feed,p['now'],p['since'],p['enabled'])}))
        except Exception as exc:print(json.dumps({'error':type(exc).__name__}))
        return 0
    from slk import db
    from slk.jobs import feed_lock
    with feed_lock(db,wait=0) as acquired:
        if not acquired:print('RR study deferred: shared feed busy');return 0
        try:return scan()
        except Exception as exc:print('RR study unavailable: '+type(exc).__name__);return 0


if __name__=='__main__':raise SystemExit(main())

"""Private reviewer assessments, separate from frozen trade results."""
import json,time
from fastapi import Body,Depends,HTTPException
from bishop_review import selected,epoch

ASPECTS={'whole_setup','bias','h4_break','liquidity','key_level_reaction','confirmation','entry','stop_loss','target'}
VERDICTS={'correct','wrong','unsure','not_reviewed'}

def validate(body,setup):
    allowed={'assessments','notes','expected','review_clock','context_tf','entry_tf','outcomes_revealed'}
    if set(body)-allowed:raise HTTPException(422,'Unknown report fields')
    assessments=body.get('assessments',{})
    if not isinstance(assessments,dict) or set(assessments)-ASPECTS or any(not isinstance(v,str) or v not in VERDICTS for v in assessments.values()):raise HTTPException(422,'Invalid assessment')
    for k in ('notes','expected'):
        if not isinstance(body.get(k,''),str) or len(body.get(k,''))>4000:raise HTTPException(422,'Notes and corrections must each be at most 4000 characters')
    if not any(v!='not_reviewed' for v in assessments.values()) and not body.get('notes','').strip() and not body.get('expected','').strip():raise HTTPException(422,'Add an assessment or a note before saving')
    clock=body.get('review_clock',epoch(setup['decision']))
    if type(clock) is not int or not epoch(setup['decision'])<=clock<=epoch(setup['cutoff']):raise HTTPException(422,'Invalid review clock')
    for k in ('context_tf','entry_tf'):
        if body.get(k,'H4') not in ('H1','H2','H3','H4','D','W'):raise HTTPException(422,'Invalid chart timeframe')
    if type(body.get('outcomes_revealed',False)) is not bool:raise HTTPException(422,'Invalid outcome visibility')
    return {'assessments':assessments,'notes':body.get('notes','').strip(),'expected':body.get('expected','').strip(),'review_clock':clock,'context_tf':body.get('context_tf','H4'),'entry_tf':body.get('entry_tf',setup['tf']),'outcomes_revealed':body.get('outcomes_revealed',False)}

def unpack(row):
    return {'setup_id':row['setup_id'],'report':json.loads(row['payload']),'created_at':row['created_at'],'updated_at':row['updated_at']}

def register_routes(app,require_user,db):
    @app.get('/api/research-reports')
    def reports(user=Depends(require_user)):
        return {'reports':[unpack(r) for r in db.query('SELECT setup_id,payload,created_at,updated_at FROM research_setup_reports WHERE user_id=%s ORDER BY updated_at DESC,setup_id',(user['id'],))]}
    @app.get('/api/research-reports/{key}')
    def read(key:str,user=Depends(require_user)):
        selected(key)
        rows=db.query('SELECT setup_id,payload,created_at,updated_at FROM research_setup_reports WHERE user_id=%s AND setup_id=%s',(user['id'],key))
        return unpack(rows[0]) if rows else None
    @app.put('/api/research-reports/{key}')
    def save(key:str,body:dict=Body(...),user=Depends(require_user)):
        e=selected(key);report=validate(body,e)
        report['setup']={k:e[k] for k in ('id','pair','strategy','confirmation','tf','side','decision','entry','stop')}
        report['setup']['targets']=[{'label':t['label'],'price':t['price'],'order_id':t['order_id']} for t in e['targets']]
        report['dataset']='42371042901; corrected 42499187752/42516446781'
        now=int(time.time())
        db.execute('INSERT INTO research_setup_reports (user_id,setup_id,payload,created_at,updated_at) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload),updated_at=VALUES(updated_at)',(user['id'],key,json.dumps(report,separators=(',',':')),now,now))
        return {'saved':True,'updated_at':now,'setup_id':key}

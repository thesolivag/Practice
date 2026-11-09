"""Authenticated, read-only review of frozen research orders and closed candles."""
import copy,gzip,json
from functools import lru_cache
from pathlib import Path
from typing import Literal
from fastapi import Depends,HTTPException,Query
from bishop.v2.aggregation import aggregate
from slk.bishop_year_replay import feed_file
from journal_replay import epoch

ROOT=Path(__file__).resolve().parents[1]/'data'/'bishop_review'
@lru_cache(maxsize=1)
def archive():
    if not (ROOT/'index.json.gz').exists():raise HTTPException(503,'Research archive is not installed')
    with gzip.open(ROOT/'index.json.gz','rt') as f:return json.load(f)
@lru_cache(maxsize=1)
def lookup():return {e['id']:e for e in archive()['entries']}
def selected(key):
    e=lookup().get(key)
    if e is None:raise HTTPException(404,'Setup not found')
    return e
@lru_cache(maxsize=4)
def candles(pair,tf):
    # Pair comes exclusively from the packaged index, never a user-supplied path.
    feed=feed_file(ROOT/(pair+'.json.gz')); tick=float(feed['instrument'].tick_size)
    bars=feed['bars'] if tf=='H1' else aggregate(feed['bars'],tf,feed['instrument'])['bars']
    return tuple({'time':epoch(b.start),'end':epoch(b.end),'available_at':epoch(b.available_at),'open':float(b.open_ticks)*tick,'high':float(b.high_ticks)*tick,'low':float(b.low_ticks)*tick,'close':float(b.close_ticks)*tick} for b in bars if b.complete)

def detail(e,reveal=False):
    out=copy.deepcopy(e)
    if not reveal:
        for t in out['targets']:t.pop('result',None)
    # Final flow state can contain later plans. Only retain facts known at this decision.
    flow=out.get('flow')
    if flow:
        flow['timeline']=[t for t in flow.get('timeline',[]) if epoch(t['at'])<=epoch(e['decision'])]
        flow.pop('plans',None);flow.pop('status',None)
    return out

def register_routes(app,require_user):
    @app.get('/api/research-review')
    def catalog(pair:str='',strategy:str='',confirmation:str='',offset:int=Query(0,ge=0),limit:int=Query(40,ge=1,le=100),user=Depends(require_user)):
        a=archive();allrows=a['entries']; rows=[e for e in allrows if (not pair or e['pair']==pair) and (not strategy or e['strategy']==strategy) and (not confirmation or e['confirmation']==confirmation)]
        keys=('id','pair','strategy','confirmation','tf','side','decision','highlight')
        return {'notice':a['notice'],'source_run':a['source_run'],'total':len(rows),'pairs':sorted({e['pair'] for e in allrows}),'strategies':sorted({e['strategy'] for e in allrows}),'confirmations':sorted({e['confirmation'] for e in allrows}),'entries':[{k:e[k] for k in keys} for e in rows[offset:offset+limit]]}
    @app.get('/api/research-review/{key}')
    def setup(key:str,reveal:bool=False,user=Depends(require_user)):return detail(selected(key),reveal)
    @app.get('/api/research-review/{key}/candles')
    def history(key:str,tf:Literal['H1','H2','H3','H4','D','W']='H4',as_of:int|None=None,before:int|None=None,limit:int=Query(300,ge=1,le=500),user=Depends(require_user)):
        e=selected(key);clock=epoch(e['decision']) if as_of is None else as_of
        if not epoch(e['decision'])<=clock<=epoch(e['cutoff']):raise HTTPException(422,'Review clock is outside the saved setup window')
        rows=[b for b in candles(e['pair'],tf) if b['available_at']<=clock and b['end']<=clock and (before is None or b['time']<before)]
        return {'candles':rows[-limit:],'has_more':len(rows)>limit,'as_of':clock,'tf':tf,'price_basis':'BID','note':'Closed candles only; gaps are not filled. New York 17:00 broker anchor, DST-aware. Outcomes use the corrected ledger; these charts contain H1 or higher candles, not minute execution evidence.'}

"""Bounded shared replay cache with compressed monthly H1 chunks.

The hourly publisher copies local candle history; webapp.replay_loader can fill
cache misses from the broker on demand under the same publication lock.
"""
import argparse
import calendar
import json
import math
import time
import zlib
from datetime import datetime, timezone

MAX_BYTES = 16 * 1024 * 1024
MAX_BARS = 512
RETENTION = 30 * 86400
MAX_PAYLOAD = 128 * 1024


def month_bounds(epoch):
    d = datetime.fromtimestamp(epoch, timezone.utc)
    lo = calendar.timegm((d.year,d.month,1,0,0,0))
    y,m = (d.year+1,1) if d.month==12 else (d.year,d.month+1)
    return f'{d.year}-{d.month:02}',lo,calendar.timegm((y,m,1,0,0,0))


def months(lo,hi):
    out=[]
    while lo<hi:
        name,start,end=month_bounds(lo)
        out.append((name,start,end))
        lo=end
    return out


def encode(rows):
    """Canonical finite, aligned, unique H1 OHLC, compressed below a strict bound."""
    if len(rows)>744:raise ValueError('Replay chunk exceeds one month')
    clean=[]
    for row in rows:
        t=int(row[0]);o,h,l,c=map(float,row[1:5])
        if t%3600 or len(row)!=5 or not all(math.isfinite(x) and x>0 for x in (o,h,l,c)) or l>min(o,c) or h<max(o,c):
            raise ValueError('Invalid replay candle')
        clean.append([t,o,h,l,c])
    if [r[0] for r in clean]!=sorted(set(r[0] for r in clean)):raise ValueError('Replay candles must be unique and sorted')
    payload=zlib.compress(json.dumps(clean,separators=(',',':'),allow_nan=False).encode())
    if len(payload)>MAX_PAYLOAD:raise ValueError('Replay chunk too large')
    return payload


def decode(payload):
    obj=zlib.decompressobj();raw=obj.decompress(bytes(payload),MAX_PAYLOAD+1)
    if len(raw)>MAX_PAYLOAD or obj.unconsumed_tail or not obj.eof:raise ValueError('Replay chunk corrupt or oversized')
    rows=json.loads(raw)
    encode(rows) # revalidate OHLC and alignment even for stored data
    return rows


def available(db,pair,lo,hi,now=None,required_until=None,metadata=False):
    """Return rows only when every requested month has been published far enough."""
    now=int(now or time.time());hi=min(int(hi),now//3600*3600)
    if hi-lo>MAX_BARS*3600:raise ValueError("Replay window too large")
    required_until=hi if required_until is None else int(required_until)
    out=[];covered=lo;providers=set()
    for name,start,end in months(lo,hi):
        rows=db.query('SELECT payload,covered_until,provider FROM replay_candles WHERE pair=%s AND month=%s',(pair,name))
        if not rows:
            if covered<required_until:return None
            break
        providers.add(rows[0].get('provider','unknown'))
        if len(providers)>1:return None
        covered=int(rows[0]['covered_until'])
        out.extend(r for r in decode(rows[0]['payload']) if lo<=r[0] and r[0]+3600<=min(hi,covered))
    if covered<required_until:return None
    out=sorted(out,key=lambda r:r[0])
    return {'rows':out,'provider':next(iter(providers),'unknown')} if metadata else out


def _publish_chunk(conn,pair,name,rows,covered,now,provider):
    payload=encode(rows)
    with conn.cursor() as c:
        c.execute('DELETE FROM replay_candles WHERE updated_at<%s',(now-RETENTION,))
        c.execute('SELECT COALESCE(SUM(bytes),0) AS n FROM replay_candles WHERE NOT (pair=%s AND month=%s)',(pair,name))
        total=int(c.fetchone()['n'])
        # LRU eviction under the publisher's global lock. No user duplicates.
        while total+len(payload)>MAX_BYTES:
            c.execute('SELECT pair,month,bytes FROM replay_candles WHERE NOT (pair=%s AND month=%s) ORDER BY updated_at LIMIT 1',(pair,name))
            old=c.fetchone()
            if not old:raise ValueError('Replay cache capacity reached')
            c.execute('DELETE FROM replay_candles WHERE pair=%s AND month=%s',(old['pair'],old['month']))
            total-=int(old['bytes'])
        c.execute('INSERT INTO replay_candles(pair,month,payload,bytes,covered_until,updated_at,provider) VALUES(%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload),bytes=VALUES(bytes),covered_until=VALUES(covered_until),updated_at=VALUES(updated_at),provider=VALUES(provider)',(pair,name,payload,len(payload),covered,now,provider))
    conn.commit()


def publish(db=None,root=None,now=None,max_jobs=20):
    """Process queued windows from local candle files only; bounded to 20 jobs/80s."""
    if db is None:
        from . import db
    from . import store
    now=int(now or time.time());start=time.monotonic();done=[]
    conn=db.connect()
    try:
        with conn.cursor() as c:
            c.execute("SELECT GET_LOCK('slk_replay_publish',0) AS ok")
            if not c.fetchone()['ok']:return {'busy':True,'processed':0}
        requests=db.query("SELECT * FROM replay_requests WHERE status='QUEUED' ORDER BY created_at LIMIT %s",(min(20,max_jobs),))
        memo={}
        for request in requests:
            if time.monotonic()-start>80:break
            pair=request['pair'];lo=int(request['lo']);hi=min(int(request['hi']),now//3600*3600)
            # Reject malformed/unbounded queued input as well as enforcing API bounds.
            if hi-lo>22*86400 or lo<0:
                status='UNAVAILABLE'
            else:
                if pair not in memo:
                    cached=store.Pair(pair,root);memo[pair]=(cached.frame(),cached.src)
                frame,provider=memo[pair]
                status='READY'
                for name,a,b in months(lo,hi):
                    epochs=frame.index.as_unit('s').asi8
                    cut=frame[(epochs>=a)&(epochs<min(b,now//3600*3600))]
                    if cut.empty or int(cut.index[0].timestamp())>max(a,lo)+3*86400 or int(cut.index[-1].timestamp())+3600<min(b,hi)-3*86400:
                        status='UNAVAILABLE';break
                    rows=[[int(t.timestamp()),float(r.open),float(r.high),float(r.low),float(r.close)] for t,r in cut.iterrows()]
                    _publish_chunk(conn,pair,name,rows,int(cut.index[-1].timestamp())+3600,now,provider)
            db.execute('UPDATE replay_requests SET status=%s,updated_at=%s WHERE id=%s AND status=%s',(status,now,request['id'],'QUEUED'))
            done.append(request['id'])
        db.execute('DELETE FROM replay_requests WHERE updated_at<%s',(now-RETENTION,))
        return {'processed':len(done)}
    finally:
        try:
            with conn.cursor() as c:c.execute("SELECT RELEASE_LOCK('slk_replay_publish')")
        finally:conn.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    if args.publish:print(json.dumps(publish()))


if __name__=='__main__':main()

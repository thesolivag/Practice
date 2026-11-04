"""Bounded read-only quote audit; no inferred fills, trading or token refresh.

Protocol references:
https://help.ctrader.com/open-api/symbol-data/#attain-historical-tick-data
https://github.com/spotware/openapi-proto-messages/blob/master/OpenApiMessages.proto
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path
from bishop.collect_teacher_data import HistoricalClient, safe_failure
from bishop.v2.types import utc, stable_id
from ctrader.framing import oa, model

PREVIOUS = Path('reports/implementation_review/usdcad_m1_40686940103/portfolio_evidence.json')
VALIDATION = Path('reports/implementation_review/usdcad_execution_refinement/input_validation.json')
OUT = Path('data/usdcad_tick_audit')


class QuoteAuditClient(HistoricalClient):
    def request(self, msg, *args, **kwargs):
        if isinstance(msg, oa.ProtoOAGetTickDataReq):
            # Retain the historical client's SELECT-only credential adapter and
            # refresh prohibition; bypass only its narrower message allowlist.
            from ctrader.client import CTraderClient
            return CTraderClient.request(self, msg, *args, **kwargs)
        return super().request(msg, *args, **kwargs)


def windows(previous, validation):
    ranges=[]
    for ob in previous['observations']:
        if ob.get('censor_reason')=='UNRESOLVED_INTRABAR_SEQUENCE':
            ranges.append((utc(ob['fill_window']['start'])-timedelta(minutes=2),
                           utc(ob['fill_window']['end'])+timedelta(minutes=2)))
    for stamp in validation['coverage']['missing']:
        t=utc(stamp)
        ranges.append((t-timedelta(minutes=2),t+timedelta(minutes=3)))
    merged=[]
    for lo,hi in sorted(ranges):
        if merged and lo<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],hi)
        else:merged.append([lo,hi])
    if not merged or len(merged)>100 or sum((hi-lo).total_seconds() for lo,hi in merged)>6*3600:
        raise ValueError('quote audit must remain bounded to six hours in at most100 windows')
    if any(lo<utc('2026-06-05T00:00Z') or hi>utc('2026-06-13T00:00Z') for lo,hi in merged):
        raise ValueError('quote audit outside frozen replay window')
    return [(int(lo.timestamp()*1000),int(hi.timestamp()*1000)) for lo,hi in merged]


def decode_page(items):
    """Decode per-page timestamp/price accumulators; preserve timestamp ties."""
    decoded=[];at=None;price=None
    for row in items:
        delta=int(row['timestamp'])
        if at is None:at=delta
        else:
            if delta>0:raise ValueError('unexpected positive newest-first tick delta')
            at+=delta
        price=int(row['tick']) if price is None else price+int(row['tick'])
        if at<0 or price<=0:raise ValueError('invalid decoded historical tick')
        decoded.append((at,price))
    return decoded


def collect_window(client, symbol_id, quote, lo, hi, pages, budget):
    """Inclusive protocol interval; split capped responses into disjoint halves.

    Do not paginate by dropping a boundary millisecond: it could contain more
    unseen quotes. If that millisecond alone is capped, retain UNRESOLVED.
    """
    if budget[0]<=0:raise RuntimeError('bounded quote request budget exhausted')
    budget[0]-=1
    res=client._hist_request(oa.ProtoOAGetTickDataReq(ctidTraderAccountId=client.account_id,
        symbolId=symbol_id,type=model.ProtoOAQuoteType.Value(quote),fromTimestamp=lo,toTimestamp=hi))
    raw=[dict(timestamp=int(t.timestamp),tick=int(t.tick)) for t in res.tickData]
    page=dict(quote=quote,from_ms=lo,to_ms=hi,has_more=bool(res.hasMore),protocol_ticks=raw)
    pages.append(page)
    decoded=decode_page(raw)
    if any(not lo<=at<=hi for at,_ in decoded):raise ValueError('tick timestamp outside requested interval')
    if not res.hasMore:
        return decoded,True
    if lo==hi:
        return [],False
    mid=(lo+hi)//2
    left,lc=collect_window(client,symbol_id,quote,lo,mid,pages,budget)
    right,rc=collect_window(client,symbol_id,quote,mid+1,hi,pages,budget)
    return left+right,lc and rc


def main():
    previous=json.loads(PREVIOUS.read_text());validation=json.loads(VALIDATION.read_text())
    bounds=windows(previous,validation)
    plan=dict(scope='QUOTE_EVIDENCE_ONLY_NOT_EXECUTION_OR_TEACHER_ACCEPTANCE',
        previous_run=40686940103,pair='USDCAD',windows_ms=bounds,
        inputs_sha256={str(p):sha256(p.read_bytes()).hexdigest() for p in (PREVIOUS,VALIDATION)},
        source_references=['https://help.ctrader.com/open-api/symbol-data/',
            'https://github.com/spotware/openapi-proto-messages/blob/master/OpenApiMessages.proto'])
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    client=None;records=[]
    try:
        client=QuoteAuditClient();client.connect();client.app_auth();client.account_auth()
        info=client.symbol('USDCAD')
        frozen=json.loads(Path('data/usdcad_execution_m1/execution_m1_d850134abd75da6381676020.csv.manifest.json').read_text())
        if info['name']!=frozen['broker_symbol'] or info['symbol_id']!=frozen['symbol_metadata']['symbol_id']:
            raise ValueError('quote symbol does not match frozen M1 input')
        if frozen['source_id']!=stable_id('source','ICMARKETS',client.env,info['symbol_id'],info['name'],'M1'):
            raise ValueError('quote environment does not match frozen input')
        response=client.request(oa.ProtoOASymbolByIdReq(ctidTraderAccountId=client.account_id,symbolId=[info['symbol_id']]))
        symbol=next(s for s in response.symbol if s.symbolId==info['symbol_id'])
        schedule=dict(observed_at=datetime.now(timezone.utc).isoformat(),status='CURRENT_SCHEDULE_NOT_VERIFIED_FOR_JUNE2026',
            timezone=symbol.scheduleTimeZone,intervals=[dict(start_second=i.startSecond,end_second=i.endSecond) for i in symbol.schedule],
            holiday_count=len(symbol.holiday))
        (OUT/'current_schedule.json').write_text(json.dumps(schedule,indent=2)+'\n')
        budget=[800]
        for lo,end in bounds:
            for quote in ('BID','ASK'):
                pages=[]
                try:
                    ticks,complete=collect_window(client,info['symbol_id'],quote,lo,end-1,pages,budget)
                except Exception:
                    raw=gzip.compress(json.dumps(dict(quote=quote,from_ms=lo,to_exclusive_ms=end,pages=pages)).encode(),mtime=0)
                    (OUT/(stable_id('failed_raw_ticks',quote,lo,end)+'.json.gz')).write_bytes(raw)
                    raise
                # Canonical sort preserves protocol same-ms groups; sequence
                # within a tied millisecond must not be inferred by consumers.
                ticks=sorted(ticks,key=lambda row:row[0])
                doc=dict(quote=quote,from_ms=lo,to_exclusive_ms=end,complete=complete,
                    source_environment=client.env,symbol_metadata=info,pages=pages,ticks=ticks,
                    price_units='INTEGER_1E_MINUS_5',same_ms_order='UNRESOLVED',
                    historical_receipt='Unknown; do not invent receipt timestamps')
                raw=gzip.compress(json.dumps(doc,separators=(',',':')).encode(),mtime=0)
                name=stable_id('ticks','USDCAD',quote,lo,end)+'.json.gz';(OUT/name).write_bytes(raw)
                records.append(dict(path=str(OUT/name),quote=quote,from_ms=lo,to_exclusive_ms=end,
                    complete=complete,rows=len(ticks),sha256=sha256(raw).hexdigest()))
        status=dict(status='RAW_QUOTE_AUDIT_COLLECTED',records=records,requests=800-budget[0])
    except Exception as exc:
        status=dict(status='FAILED',records=records,**safe_failure(exc))
    finally:
        if client is not None:client.close()
    (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps({k:v for k,v in status.items() if k!='records'}))
    return 0 if status['status']=='RAW_QUOTE_AUDIT_COLLECTED' else 1


if __name__=='__main__':raise SystemExit(main())

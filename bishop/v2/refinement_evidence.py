"""Frozen quote ordering and coarse price bounds, never synthetic execution bars.

Proof visibility is separate from occurrence. Callers must carry the publication
returned by ``prove_gap`` into every dependent event's availability.
"""
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
import gzip
import json
from pathlib import Path
from .aggregation import expected_slots, minutes
from .types import _freeze, jsonable, stable_id, utc


def _decode_page(page):
    rows=[];at=None;price=None
    for row in page['protocol_ticks']:
        delta=row['timestamp'];change=row['tick']
        if type(delta) is not int or type(change) is not int:
            raise ValueError('integer historical quote encoding required')
        if at is None:at=delta
        else:
            if delta>0:raise ValueError('unexpected historical timestamp delta')
            at+=delta
        price=change if price is None else price+change
        if price<=0 or not page['from_ms']<=at<=page['to_ms']:
            raise ValueError('historical quote outside requested bounds')
        rows.append((at,price))
    return rows


def _validated_document(raw, record, fine):
    if sha256(raw).hexdigest()!=record['sha256']:
        raise ValueError('quote evidence hash mismatch')
    doc=json.loads(gzip.decompress(raw))
    for key in ('quote','from_ms','to_exclusive_ms','complete'):
        if doc[key]!=record[key]:raise ValueError('quote evidence index mismatch')
    if doc['quote'] not in ('BID','ASK') or type(doc['complete']) is not bool:
        raise ValueError('invalid quote evidence kind/completeness')
    lo,hi=doc['from_ms'],doc['to_exclusive_ms']
    if type(lo) is not int or type(hi) is not int or not lo<hi or hi-lo>604800000:
        raise ValueError('invalid quote evidence bounds')
    inst=fine['instrument'];meta=fine.get('manifest',{})
    info=doc['symbol_metadata']
    if info.get('name')!=meta.get('broker_symbol',inst.symbol):
        raise ValueError('quote evidence broker symbol mismatch')
    if inst.venue=='ICMARKETS':
        symbol_id=meta.get('symbol_metadata',{}).get('symbol_id')
        if (symbol_id is None or info.get('symbol_id')!=symbol_id
                or meta.get('source_id')!=stable_id('source','ICMARKETS',doc['source_environment'],
                    symbol_id,meta['broker_symbol'],meta['base_tf'])):
            raise ValueError('quote evidence source environment mismatch')
    leaves=[];decoded=[]
    for page in doc['pages']:
        if (page['quote']!=doc['quote'] or not lo<=page['from_ms']<=page['to_ms']<hi
                or type(page['has_more']) is not bool):
            raise ValueError('invalid quote evidence page')
        rows=_decode_page(page)
        if not page['has_more']:
            leaves.append((page['from_ms'],page['to_ms']))
            decoded.extend(rows)
    cursor=lo;complete=True
    for start,end in sorted(leaves):
        if start!=cursor:complete=False
        cursor=end+1
    complete=complete and cursor==hi
    if complete!=doc['complete']:
        raise ValueError('quote evidence pagination completeness mismatch')
    decoded.sort(key=lambda row:row[0])
    if decoded!=[tuple(row) for row in doc['ticks']] or len(decoded)!=record['rows']:
        raise ValueError('quote evidence decoded rows mismatch')
    return doc,tuple(decoded)


@dataclass(frozen=True)
class RefinementEvidence:
    id: str
    _coarse: tuple
    _starts: tuple
    _ticks_by_bar: object
    _audit: object

    @property
    def audit(self):
        # Return a JSON-native copy; callers cannot mutate the proof object.
        return jsonable(self._audit)

    def resolve_limit_target(self, order, bar, costs):
        if (order.kind!='LIMIT' or order.instrument!=bar.instrument or not bar.complete
                or order.available_at>bar.start):
            return None
        saved=self._ticks_by_bar.get(bar.id)
        if not saved or saved[0]!=bar.available_at:return None
        rows=saved[1]
        spread=costs.spread_ticks
        groups=defaultdict(list)
        for at,price in rows:groups[at].append(price)
        filled=False
        for at,prices in sorted(groups.items()):
            entry_hit=any(p+spread<=order.entry_ticks if order.side=='BUY'
                          else p>=order.entry_ticks for p in prices)
            target_hit=any(p>=order.target_ticks if order.side=='BUY'
                           else p+spread<=order.target_ticks for p in prices)
            stop_hit=any(p<=order.stop_ticks if order.side=='BUY'
                         else p+spread>=order.stop_ticks for p in prices)
            if not filled:
                if not entry_hit:continue
                if target_hit or stop_hit:return None
                filled=True
            elif stop_hit:
                return None
            elif target_hit:
                return 'TARGET_AFTER_ENTRY'
        return 'FILLED_WITHOUT_EXIT_IN_MINUTE' if filled else None

    def prove_gap(self, order, state, start, end, stop, target, spread, as_of,
                  calendar, base_tf):
        duration=minutes(base_tf)
        if duration is None or duration<=0 or state not in ('PENDING','FILLED'):
            return None
        start,end,as_of=utc(start),utc(end),utc(as_of)
        if not start<=end<=as_of or (state=='PENDING' and order.kind!='LIMIT'):return None
        stop,target,spread=Decimal(stop),Decimal(target),Decimal(spread)
        ready=start;proofs=[]
        for slot in expected_slots(start,end,base_tf,calendar):
            i=bisect_right(self._starts,slot)-1
            if i<0:return None
            bar=self._coarse[i]
            if (bar.instrument!=order.instrument or not bar.complete or bar.available_at>as_of
                    or not bar.start<=slot or slot+timedelta(minutes=duration)>bar.end):
                return None
            if state=='PENDING':
                safe=(bar.low_ticks+spread>order.entry_ticks if order.side=='BUY'
                      else bar.high_ticks<order.entry_ticks)
            else:
                safe=(stop<bar.low_ticks and target>bar.high_ticks if order.side=='BUY'
                      else stop>bar.high_ticks+spread and target<bar.low_ticks+spread)
            if not safe:return None
            ready=max(ready,bar.available_at)
            if bar.id not in proofs:proofs.append(bar.id)
        return ready,tuple(proofs)


def load_refinement_evidence(directory, coarse_bars, fine_feed):
    directory=Path(directory)
    status_raw=(directory/'status.json').read_bytes();status=json.loads(status_raw)
    if status['status']!='RAW_QUOTE_AUDIT_COLLECTED':
        raise ValueError('quote evidence collection was not completed')
    documents=[];hashes=[]
    for record in status['records']:
        name=Path(record['path']).name
        raw=(directory/name).read_bytes()
        doc,rows=_validated_document(raw,record,fine_feed)
        documents.append((doc,rows));hashes.append((name,record['sha256']))
    if not documents:raise ValueError('quote evidence is empty')
    inst=fine_feed['instrument']
    by_bar={};uncomparable=0
    for bar in fine_feed['bars']:
        if bar.tf!='M1' or bar.end-bar.start!=timedelta(minutes=1):
            raise ValueError('quote refinement currently requires M1 execution bars')
        lo=int(bar.start.timestamp()*1000);hi=int(bar.end.timestamp()*1000)
        selected={}
        for quote in ('BID','ASK'):
            matches=[(d,r) for d,r in documents if d['quote']==quote and d['complete']
                     and d['from_ms']<=lo and d['to_exclusive_ms']>=hi]
            if len(matches)!=1:break
            selected[quote]=tuple((at,inst.to_ticks(Decimal(p)/Decimal(100000)))
                                  for at,p in matches[0][1] if lo<=at<hi)
        if len(selected)!=2 or not selected['BID']:continue
        rows=selected['BID']
        if (len({p for at,p in rows if at==rows[0][0]})!=1
                or len({p for at,p in rows if at==rows[-1][0]})!=1
                or (rows[0][1],max(p for _,p in rows),min(p for _,p in rows),rows[-1][1])
                !=(bar.open_ticks,bar.high_ticks,bar.low_ticks,bar.close_ticks)):
            uncomparable+=1;continue
        by_bar[bar.id]=(bar.available_at,rows)
    coarse=tuple(coarse_bars)
    if any(b.instrument!=inst.symbol or b.tf!='H1' or not b.complete for b in coarse):
        raise ValueError('coarse proof requires same-instrument complete H1 bars')
    if any(a.end>b.start for a,b in zip(coarse,coarse[1:])):
        raise ValueError('coarse proof bars must be ordered and nonoverlapping')
    audit=dict(scope='VALIDATED_QUOTE_ORDERING_AND_COARSE_NO_TOUCH_PROOFS',
        quote_status_sha256=sha256(status_raw).hexdigest(),quote_files=hashes,
        comparable_m1_bars=len(by_bar),uncomparable_m1_bars=uncomparable,
        coarse_proof_policy='STRICT_UNTOUCHED_BOUNDS_PUBLISHED_BY_SIMULATION_ASOF',
        quote_policy='CONSTANT_SPREAD_SAME_MS_ORDER_UNRESOLVED_MINUTE_PUBLICATION',
        silent_quote_minutes_are_not_market_closure_proofs=True)
    identity=stable_id('refinement_evidence',audit,tuple((b.id,b.available_at) for b in coarse),
                       tuple((b.id,b.available_at) for b in fine_feed['bars']),fine_feed.get('hashes',{}))
    return RefinementEvidence(identity,coarse,tuple(b.start for b in coarse),
                              _freeze(by_bar),_freeze(audit))

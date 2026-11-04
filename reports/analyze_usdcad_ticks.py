"""Inspect quote evidence; never inject inferred quotes or alter execution state."""
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
import csv
import gzip
import json
from pathlib import Path
from bishop.v2.types import utc
from reports.collect_usdcad_ticks import OUT, PREVIOUS, VALIDATION


def target_sequence(order, rows, *, spread=0):
    """Constant-spread diagnostic; same-ms entry/exit ordering stays unknown."""
    if not rows:return {'status':'NO_TICKS'}
    groups=defaultdict(list)
    for at,price in rows:groups[at].append(price)
    entry=order['entry_ticks'];stop=order['stop_ticks'];target=order['target_ticks']
    filled_at=None
    for at,prices in sorted(groups.items()):
        entry_hit=any(p+spread<=entry if order['side']=='BUY' else p>=entry for p in prices)
        target_hit=any(p>=target if order['side']=='BUY' else p+spread<=target for p in prices)
        stop_hit=any(p<=stop if order['side']=='BUY' else p+spread>=stop for p in prices)
        if filled_at is None:
            if not entry_hit:continue
            if target_hit or stop_hit:return dict(status='UNRESOLVED_SAME_MS_ORDERING',at_ms=at)
            filled_at=at
        elif stop_hit or target_hit:
            if stop_hit and target_hit:return dict(status='UNRESOLVED_SAME_MS_ORDERING',at_ms=at)
            return dict(status='TARGET_AFTER_ENTRY' if target_hit else 'STOP_AFTER_ENTRY',
                        entry_at_ms=filled_at,exit_at_ms=at)
    return dict(status='FILLED_WITHOUT_EXIT_IN_MINUTE' if filled_at is not None else 'NO_ENTRY_IN_MINUTE',
                entry_at_ms=filled_at)


def main():
    status=json.loads((OUT/'status.json').read_text())
    if status['status']!='RAW_QUOTE_AUDIT_COLLECTED':raise ValueError('raw quote audit failed')
    previous=json.loads(PREVIOUS.read_text());validation=json.loads(VALIDATION.read_text())
    documents=[]
    for record in status['records']:
        raw=Path(record['path']).read_bytes()
        if sha256(raw).hexdigest()!=record['sha256']:raise ValueError('raw tick hash mismatch')
        documents.append(json.loads(gzip.decompress(raw)))
    def minute(quote,lo):
        hi=lo+60000
        candidates=[d for d in documents if d['quote']==quote and d['from_ms']<=lo and d['to_exclusive_ms']>=hi]
        if len(candidates)!=1 or not candidates[0]['complete']:return [],False
        return [r for r in candidates[0]['ticks'] if lo<=r[0]<hi],True
    path=Path('data/usdcad_execution_m1/execution_m1_d850134abd75da6381676020.csv.gz')
    bars={r['time']:r for r in csv.DictReader(gzip.decompress(path.read_bytes()).decode().splitlines())}
    cases=[]
    for ob in previous['observations']:
        if ob.get('censor_reason')!='UNRESOLVED_INTRABAR_SEQUENCE':continue
        order=next(o for o in previous['orders'] if o['id']==ob['id'])
        stamp=ob['fill_window']['start'];lo=int(utc(stamp).timestamp()*1000)
        bid,complete=minute('BID',lo);ask,ask_complete=minute('ASK',lo)
        bar=bars[stamp];expected={k:int(Decimal(bar[k])*100000) for k in ('open','high','low','close')}
        # Boundary ties may not establish one unique opening/closing price.
        tied_boundary=bool(bid) and (len({p for at,p in bid if at==bid[0][0]})>1
                                    or len({p for at,p in bid if at==bid[-1][0]})>1)
        actual=dict(open=bid[0][1],high=max(p for _,p in bid),low=min(p for _,p in bid),close=bid[-1][1]) if bid else None
        match=complete and not tied_boundary and actual==expected
        cases.append(dict(order=order,minute=stamp,bid_complete=complete,ask_complete=ask_complete,
            bid_rows=len(bid),ask_rows=len(ask),expected_m1=expected,observed_tick_ohlc=actual,
            boundary_tie=tied_boundary,comparable=match,
            constant_zero_spread_sequence=target_sequence(order,bid) if match else {'status':'UNRESOLVED_FEED_COMPARABILITY'}))
    gaps=[]
    for stamp in validation['coverage']['missing']:
        lo=int(utc(stamp).timestamp()*1000);bid,bc=minute('BID',lo);ask,ac=minute('ASK',lo)
        gaps.append(dict(minute=stamp,bid_complete=bc,ask_complete=ac,bid_rows=len(bid),ask_rows=len(ask),
                         status='BID_QUOTES_PRESENT_M1_ABSENT' if bc and bid else
                         'NO_BID_QUOTES_RETURNED' if bc else 'INCOMPLETE_QUOTE_REQUEST',
                         historical_market_closed_inferred=False))
    report=dict(scope='FROZEN_QUOTE_AUDIT_NOT_PORTFOLIO_REPLAY_OR_TEACHER_ACCEPTANCE',
        cases=cases,gaps=gaps,actual_variable_spread_simulated=False,
        limitations=['Zero-spread sequence is a diagnostic, not an actual broker fill.',
                    'No returned quotes do not establish historical closure or authorize filled-in bars.',
                    'Current broker schedule is not automatically a historical June calendar.'])
    (OUT/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(cases=[dict(minute=r['minute'],comparable=r['comparable'],sequence=r['constant_zero_spread_sequence']) for r in cases],
        missing_minutes=len(gaps),missing_with_bid_quotes=sum(g['status']=='BID_QUOTES_PRESENT_M1_ABSENT' for g in gaps)),indent=2))


if __name__=='__main__':main()

"""Bounded native IC candle audit; no anchor search or teacher-match claim.

Only --collect opens a broker connection. HistoricalClient is SELECT/auth/history
only and cannot refresh Kevin's borrowed credentials. Native periods are read
from the installed protocol descriptor; an unsupported H2 is never synthesized.
"""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import gzip
from hashlib import sha256
import json
from pathlib import Path
import signal

from bishop.collect_teacher_data import HistoricalClient, exact_prices, safe_failure
from bishop.v2.aggregation import aggregate
from bishop.v2.feed import load_feed
from bishop.v2.types import utc
from ctrader.framing import model, oa

START = utc('2026-07-09T00:00:00Z')
END = utc('2026-07-13T05:24:00Z')
REPORT = 'reports/implementation_review/teacher_trace_40525741669/pdf-p22-xagusd-sell-1.json.gz'
METADATA = 'reports/teacher_icmarkets_metadata.json'
DURATIONS = {'H1': timedelta(hours=1), 'H2': timedelta(hours=2), 'H4': timedelta(hours=4)}


def supported_periods():
    return tuple(model.ProtoOATrendbarPeriod.keys())


def compare_rows(native, rebuilt):
    """Compare only equal start/end candles; boundaries are independently visible."""
    def indexed(rows):
        out = {}
        for row in rows:
            key = (row['start'], row['end'])
            if key in out:
                raise ValueError('duplicate candle boundaries')
            out[key] = row
        return out
    left, right = indexed(native), indexed(rebuilt)
    common = sorted(set(left) & set(right))
    differences = []
    for key in common:
        delta = {field: format(Decimal(left[key][field])-Decimal(right[key][field]), 'f')
                 for field in ('open', 'high', 'low', 'close')}
        if any(Decimal(value) != 0 for value in delta.values()):
            differences.append(dict(start=key[0], end=key[1], native=left[key],
                                    rebuilt=right[key], native_minus_rebuilt=delta))
    return dict(native_count=len(left), rebuilt_count=len(right), equal_boundary_count=len(common),
                exact_ohlc_count=len(common)-len(differences), ohlc_difference_count=len(differences),
                native_only_boundaries=[dict(start=a,end=b) for a,b in sorted(set(left)-set(right))],
                rebuilt_only_boundaries=[dict(start=a,end=b) for a,b in sorted(set(right)-set(left))],
                differences=differences)


def load_frozen_inputs(report_path=REPORT, metadata_path=METADATA):
    report_raw=Path(report_path).read_bytes()
    report=json.loads(gzip.decompress(report_raw))
    plan=report['plan']
    if plan['pair'] != 'XAGUSD' or utc(plan['as_of']) != END:
        raise ValueError('only reviewed XAGUSD observation ceiling is authorized')
    manifest_raw=Path(plan['manifest_path']).read_bytes()
    if sha256(manifest_raw).hexdigest() != plan['manifest_sha256']:
        raise ValueError('frozen manifest hash mismatch')
    manifest=json.loads(manifest_raw)
    if manifest['sha256'] != plan['input_sha256'] or manifest['base_tf'] != 'M1':
        raise ValueError('reviewed frozen M1 input required')
    metadata_raw=Path(metadata_path).read_bytes()
    metadata=json.loads(metadata_raw)['XAGUSD']
    if metadata.get('broker_symbol') != 'XAGUSD' or metadata.get('symbol_mapping_status') != 'EXACT_BROKER_NAME_ALTERNATE_SOURCE_FEED':
        raise ValueError('verified exact XAGUSD mapping required')
    # This also checks the frozen data hash, tick grid and declared calendar.
    feed=load_feed(plan['input_path'], manifest, END, plan['history_start'])
    return report, metadata, manifest, feed, dict(report_sha256=sha256(report_raw).hexdigest(),
        metadata_sha256=sha256(metadata_raw).hexdigest(), manifest_sha256=plan['manifest_sha256'],
        frozen_m1_sha256=plan['input_sha256'])


def rebuilt_rows(feed, manifest, period):
    result=aggregate(feed['bars'],period,feed['instrument'],END,
                     calendar=manifest.get('calendar',manifest['calendar_id']))
    tick=Decimal(str(feed['instrument'].tick_size))
    rows=[dict(start=b.start.isoformat(),end=b.end.isoformat(),
               **{k:format(Decimal(getattr(b,k+'_ticks'))*tick,'f') for k in ('open','high','low','close')})
          for b in result['bars'] if START<=b.start and b.end<=END and b.available_at<=END]
    return rows, result['coverage']


def collect_native(client, info, period):
    """One short request per supported period, raw exact protocol observations."""
    if period not in supported_periods() or period not in DURATIONS:
        raise ValueError('unsupported declared native period')
    response=client._hist_request(oa.ProtoOAGetTrendbarsReq(
        ctidTraderAccountId=client.account_id,symbolId=info['symbol_id'],
        period=model.ProtoOATrendbarPeriod.Value(period),
        fromTimestamp=int(START.timestamp()*1000),toTimestamp=int(END.timestamp()*1000)))
    raw=[]; closed={}; forming=0
    tick=Decimal(10)**-int(info['digits'])
    for tb in response.trendbar:
        at=datetime.fromtimestamp(int(tb.utcTimestampInMinutes)*60,timezone.utc)
        if not START<=at<END:
            continue
        prices=exact_prices(tb)
        if any(p/tick!=(p/tick).to_integral_value() for p in prices):
            raise ValueError('native prices off verified broker grid')
        record=dict(start=at.isoformat(),end=(at+DURATIONS[period]).isoformat(),
                    **dict(zip(('open','high','low','close'),(format(p,'f') for p in prices))),
                    volume=int(getattr(tb,'volume',0)),
                    protocol=dict(low=int(tb.low),deltaOpen=int(tb.deltaOpen),
                                  deltaHigh=int(tb.deltaHigh),deltaClose=int(tb.deltaClose),
                                  utcTimestampInMinutes=int(tb.utcTimestampInMinutes)))
        raw.append(record)
        if at+DURATIONS[period]>END:
            forming+=1
            continue
        row={k:record[k] for k in ('start','end','open','high','low','close')}
        if at in closed and closed[at] != row:
            raise ValueError('conflicting native candle')
        closed[at]=row
    return dict(raw=raw,closed=[closed[t] for t in sorted(closed)],
                excluded_forming_count=forming,request_count=1,
                completeness='UNVALIDATED_NO_PAGINATION_FLAG')


def _timeout(*_):
    raise TimeoutError('bounded native audit budget reached')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect',action='store_true')
    parser.add_argument('--out',default='reports/native_candle_alignment')
    args=parser.parse_args(argv)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    report,metadata,manifest,feed,hashes=load_frozen_inputs()
    periods=supported_periods()
    plan=dict(scope='NATIVE_BROKER_ALIGNMENT_NOT_TEACHER_ACCEPTANCE',instrument='XAGUSD',
        start=START.isoformat(),end=END.isoformat(),supported_native_periods=periods,
        requested_native_periods=[p for p in ('H1','H4','H2') if p in periods],
        native_H2_status='SUPPORTED' if 'H2' in periods else 'UNAVAILABLE_IN_INSTALLED_PROTOCOL',
        frozen_anchor=manifest['anchor_id'],frozen_calendar=manifest.get('calendar',manifest['calendar_id']),
        hashes=hashes,network_requested=args.collect,
        limitations=['No anchor search; only broker-native boundaries versus existing declared aggregation.',
                     'Source Saxo/FOREXcom candle equivalence is not established.',
                     'Frozen M1 schedule is a declared uncertain derivation; withheld data may affect OHLC.',
                     'Historical availability is assumed at close; no actual receipt timestamps.',
                     'Differences can reflect anchor, source/version drift or incomplete data; no automatic attribution.'])
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    if not args.collect:
        return 0
    status=dict(status='STARTING',periods={})
    def save():
        (out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    save();client=None
    previous=signal.signal(signal.SIGALRM,_timeout);signal.setitimer(signal.ITIMER_REAL,240)
    try:
        client=HistoricalClient();client.connect();client.app_auth();client.account_auth()
        info=client.symbol(metadata['broker_symbol'])
        if info['name'] != metadata['broker_symbol']:
            raise ValueError('broker symbol resolved to a different name')
        for period in plan['requested_native_periods']:
            native=collect_native(client,info,period)
            if not native['closed']:
                raise ValueError('no closed native candles returned')
            rebuilt,coverage=rebuilt_rows(feed,manifest,period)
            record=dict(period=period,native=native,rebuilt=rebuilt,
                        comparison=compare_rows(native['closed'],rebuilt),rebuilt_coverage=coverage)
            raw=(json.dumps(record,indent=2)+'\n').encode()
            path=out/(period+'.json.gz')
            if path.exists():
                raise FileExistsError('native audit output already frozen')
            path.write_bytes(gzip.compress(raw,mtime=0))
            status['periods'][period]=dict(status='COLLECTED_UNVALIDATED',file=str(path),
                sha256=sha256(path.read_bytes()).hexdigest(),comparison=record['comparison'])
            save()
        status['status']='COLLECTED_UNVALIDATED'
    except Exception as exc:
        status.update(status='PARTIAL' if status['periods'] else 'FAILED',**safe_failure(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                status['close_failure']=safe_failure(exc)
                if status['status']=='COLLECTED_UNVALIDATED':
                    status['status']='PARTIAL'
        save()
    print(json.dumps(dict(status=status['status'],periods={p:r['status'] for p,r in status['periods'].items()})))
    return 0 if status['status']=='COLLECTED_UNVALIDATED' else 1


if __name__=='__main__':
    raise SystemExit(main())

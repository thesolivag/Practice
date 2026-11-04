"""Inspect frozen pre-snapshot candles and literal engulf predicates, not matches.

No detector rerun, anchor search, acquisition, fixture editing or price fitting.
The explicitly supplied window is exploratory chart context, not a fill clock.
"""
import argparse
from decimal import Decimal
import gzip
from hashlib import sha256
import json
from pathlib import Path

from bishop.v2.aggregation import aggregate
from bishop.v2.entries import _engulfs
from bishop.v2.feed import load_feed
from bishop.v2.types import jsonable, utc


def _components(a, b, side):
    return dict(same_segment=a.segment_id == b.segment_id,
                previous_opposite=a.side != side, previous_non_doji=a.side is not None,
                current_direction=b.side == side,
                body_low_covers=min(b.open_ticks,b.close_ticks) <= min(a.open_ticks,a.close_ticks),
                body_high_covers=max(b.open_ticks,b.close_ticks) >= max(a.open_ticks,a.close_ticks),
                closes_beyond_previous_open=b.close_ticks > a.open_ticks if side == 'BUY'
                else b.close_ticks < a.open_ticks,
                engine_engulfs=_engulfs(a,b,side))


def trace(report_path, since):
    raw=Path(report_path).read_bytes()
    report=json.loads(gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw)
    plan=report['plan']; at=utc(plan['as_of']); since=utc(since)
    if not utc(plan['history_start']) <= since < at:
        raise ValueError('explicit since must lie within frozen history before snapshot')
    manifest_path=Path(plan['manifest_path']); manifest_raw=manifest_path.read_bytes()
    if sha256(manifest_raw).hexdigest() != plan['manifest_sha256']:
        raise ValueError('frozen manifest hash mismatch')
    metadata=json.loads(manifest_raw)
    if metadata.get('sha256') != plan['input_sha256']:
        raise ValueError('report and manifest input hashes differ')
    feed=load_feed(plan['input_path'],metadata,at,plan['history_start'])
    if any(b.available_at > at or b.end > at for b in feed['bars']):
        raise ValueError('future base bar in snapshot')
    tick=Decimal(str(feed['instrument'].tick_size))
    def bar_row(b):
        return dict(id=b.id,tf=b.tf,start=b.start,end=b.end,available_at=b.available_at,
                    segment_id=b.segment_id,side=b.side,
                    ticks={k:getattr(b,k+'_ticks') for k in ('open','high','low','close')},
                    prices={k:str(Decimal(getattr(b,k+'_ticks'))*tick)
                            for k in ('open','high','low','close')},
                    in_original_scan=b.available_at >= utc(plan['scan_start']))
    output=dict(scope='FROZEN_CANDLE_PRIMITIVE_DIAGNOSTIC_NOT_TEACHER_ACCEPTANCE',
                report_sha256=sha256(raw).hexdigest(),fixture_sha256=report['fixture_sha256'],
                input_sha256=plan['input_sha256'],manifest_sha256=plan['manifest_sha256'],
                source_plan=report['source_plan'],as_of=at,since=since,
                original_scan_start=plan['scan_start'],anchor=metadata['anchor_id'],
                base_coverage=feed['coverage'],timeframes={},
                limitations=['Explicit window is exploratory chart context, not a teacher setup/fill clock.',
                             'IC Markets and source-feed candle equivalence is unverified.',
                             'Primitive engulfing alone does not establish H4 reaction, KL availability or an eligible order.',
                             'Emitted setup groups come from the supplied report; no detector is rerun.'])
    for tf in ('H2','H4'):
        aggregated=aggregate(feed['bars'],tf,feed['instrument'],at,
                             calendar=metadata.get('calendar',metadata['calendar_id']))
        bars=tuple(aggregated['bars'])
        if any(not b.complete or b.available_at > at or b.end > at for b in bars):
            raise ValueError('future or incomplete aggregate in closed-bar trace')
        pairs=[]
        if tf=='H2':
            for a,b in zip(bars,bars[1:]):
                if b.start < since: continue
                ids={a.id,b.id}
                linked=[dict(setup_id=g['setup_id'],model=g['model'],status=g['status'],
                             available_at=g['available_at'],prices=g['prices'],
                             matched_bar_ids=sorted(ids.intersection(g['evidence_ids'])))
                        for g in report['plan_groups'] if ids.intersection(g['evidence_ids'])]
                pairs.append(dict(previous=bar_row(a),current=bar_row(b),
                                  contiguous=a.end==b.start,
                                  predicates={side:_components(a,b,side) for side in ('BUY','SELL')},
                                  emitted_setup_groups=linked))
        selected=[bar_row(b) for b in bars if b.start >= since]
        output['timeframes'][tf]=dict(bars=selected,adjacent_pairs=pairs,coverage=aggregated['coverage'],
            counts=dict(closed_bars=len(selected),adjacent_pairs=len(pairs),
                        engulfing_by_side={side:sum(p['predicates'][side]['engine_engulfs'] for p in pairs)
                                          for side in ('BUY','SELL')}))
    return jsonable(output)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--since',required=True,help='Explicit timezone-aware exploratory window start')
    args=parser.parse_args(argv)
    result=trace(args.report,args.since)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({tf:r['counts'] for tf,r in result['timeframes'].items()}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())

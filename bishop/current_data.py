"""Incremental, read-only IC Markets H1 acquisition for paper bias scans.

Kevin owns token refresh. This client never writes shared settings, submits
orders, or substitutes another feed. Closed candles only; revisions fail closed.
"""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path

from .collect_teacher_data import HistoricalClient, collect_job, safe_failure
from .v2.types import utc, stable_id


def closed_hour(now=None):
    return utc(now or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)


def rows(path):
    with gzip.open(path, 'rt', newline='') as stream:
        return list(csv.DictReader(stream))


def refresh(client, pair, metadata, cache, *, as_of, days=400):
    end = utc(as_of)
    if end != closed_hour(end) or type(days) is not int or not 35 <= days <= 400:
        raise ValueError('A closed-hour boundary and 35–400 days are required')
    if metadata.get('calendar_id') != 'fx_ny_v1' or metadata.get('broker_symbol') != pair:
        raise ValueError('Current bias acquisition requires an explicitly mapped FX symbol/calendar')
    directory = Path(cache)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (pair + '.csv.gz')
    manifest_path = directory / (pair + '.csv.manifest.json')
    lower = end - timedelta(days=days)
    old, previous = [], None
    if target.exists() or manifest_path.exists():
        if not target.is_file() or not manifest_path.is_file():
            raise ValueError('Incomplete source cache; explicit rebuild required')
        previous = json.loads(manifest_path.read_text())
        if sha256(target.read_bytes()).hexdigest() != previous.get('sha256'):
            raise ValueError('Source cache hash mismatch')
        if previous.get('symbol') != pair or previous.get('base_tf') != 'H1':
            raise ValueError('Source cache identity mismatch')
        if any(previous.get(key) != metadata.get(key) for key in
               ('anchor_id', 'calendar_id', 'broker_symbol', 'calendar_version', 'anchor_version')):
            raise ValueError('Source cache metadata changed; explicit rebuild required')
        if utc(previous['requested_end']) > end:
            raise ValueError('Source cache belongs to a later clock')
        old = rows(target)
        if any(utc(r['time']) >= end for r in old):
            raise ValueError('Source cache belongs to a later clock')
        if not old:
            raise ValueError('Empty source cache')
        # A repeated hour reuses the frozen snapshot; no new broker request.
        if utc(previous['requested_end']) == end:
            if utc(previous['requested_start']) != lower:
                raise ValueError('Source cache warmup changed; explicit rebuild required')
            return dict(path=str(target), manifest=str(manifest_path), as_of=end.isoformat(), reused=True)
    start = max(lower, utc(old[-1]['time']) - timedelta(days=2)) if old else lower
    if previous and utc(previous['requested_start']) > lower:
        start = lower
    job = dict(id=stable_id('current_bias', pair, start, end), pair=pair, base_tf='H1',
               start=start.isoformat(), end=end.isoformat(), case_ids=[])
    result = collect_job(client, job, metadata, directory / 'delta')
    new_manifest = json.loads(Path(result['manifest']).read_text())
    if previous and any(previous.get(key) != new_manifest.get(key) for key in
                        ('source_id', 'tick_size', 'distance_unit', 'anchor_id', 'calendar_id')):
        raise ValueError('Source cache conventions changed; explicit rebuild required')
    merged = {utc(r['time']): r for r in old}
    for row in rows(result['path']):
        at = utc(row['time'])
        if at in merged and any(merged[at][k] != row[k] for k in ('open', 'high', 'low', 'close', 'volume')):
            raise ValueError('Previously closed broker candle changed; preserve evidence and review')
        merged[at] = row
    selected = [r for at, r in sorted(merged.items()) if lower <= at < end]
    if not selected:
        raise ValueError('No closed candles in current window')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=('time', 'open', 'high', 'low', 'close', 'volume'), lineterminator='\n')
    writer.writeheader()
    writer.writerows(selected)
    raw = gzip.compress(stream.getvalue().encode(), mtime=0)
    manifest = {**new_manifest, 'sha256': sha256(raw).hexdigest(),
                'requested_start': lower.isoformat(), 'requested_end': end.isoformat(),
                'first_bar': selected[0]['time'], 'last_bar': selected[-1]['time'], 'rows': len(selected),
                'purpose': 'CURRENT_BIAS_PAPER_ONLY', 'coverage_status': 'NOT_CALENDAR_VALIDATED',
                'current_acquisition': dict(delta_sha256=new_manifest['sha256'],
                                            previous_sha256=previous['sha256'] if previous else None,
                                            overlap_revision_policy='FAIL_CLOSED', warmup_days=days)}
    # Recompute whole-window diagnostics rather than retaining delta-only counts.
    manifest.pop('chunks', None)
    manifest.pop('empty_chunks', None)
    manifest.pop('observed_outside_fx_weekend_hours', None)
    manifest.pop('zero_volume_rows', None)
    target.with_suffix('.tmp').write_bytes(raw)
    manifest_path.with_suffix('.tmp').write_text(json.dumps(manifest, indent=2) + '\n')
    target.with_suffix('.tmp').replace(target)
    manifest_path.with_suffix('.tmp').replace(manifest_path)
    import shutil
    shutil.rmtree(directory / 'delta')  # Successful merge contains the same candles; failed deltas stay as evidence.
    return dict(path=str(target), manifest=str(manifest_path), as_of=end.isoformat(), reused=False)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair', required=True, choices=('GBPUSD', 'EURNZD'))
    p.add_argument('--cache', required=True)
    p.add_argument('--as-of')
    p.add_argument('--out', required=True)
    a = p.parse_args(argv)
    metadata = json.loads(Path('reports/teacher_icmarkets_metadata.json').read_text())[a.pair]
    at = closed_hour(a.as_of)
    if at > closed_hour():
        raise ValueError('Future collection clock refused')
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    try:
        cached_manifest = Path(a.cache) / (a.pair + '.csv.manifest.json')
        same_hour = cached_manifest.is_file() and utc(json.loads(cached_manifest.read_text())['requested_end']) == at
        if same_hour:
            result = refresh(None, a.pair, metadata, a.cache, as_of=at)
        else:
            client = HistoricalClient()
            try:
                client.connect()
                client.app_auth()
                client.account_auth()
                result = refresh(client, a.pair, metadata, a.cache, as_of=at)
            finally:
                client.close()
    except Exception as exc:
        result = dict(status='FAILED', pair=a.pair, as_of=at.isoformat(), **safe_failure(exc))
        Path(a.out).write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
        return 1
    Path(a.out).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(pair=a.pair, as_of=result['as_of'], reused=result['reused'])))


if __name__ == '__main__':
    raise SystemExit(main())

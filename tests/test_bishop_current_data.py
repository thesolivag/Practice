from datetime import datetime, timedelta, timezone
import csv
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import pytest
from bishop import current_data

T = datetime(2026, 7, 1, tzinfo=timezone.utc)
METADATA = dict(calendar_id='fx_ny_v1', broker_symbol='GBPUSD', anchor_id='ny17_wall_v2')


def acquisition(monkeypatch, points, calls):
    def collect(client, job, metadata, out):
        calls.append(job)
        path = Path(out) / 'delta.csv.gz'
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = io.StringIO()
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(('time', 'open', 'high', 'low', 'close', 'volume'))
        writer.writerows(points)
        raw = gzip.compress(stream.getvalue().encode())
        path.write_bytes(raw)
        manifest = path.with_suffix('.manifest.json')
        manifest.write_text(json.dumps(dict(symbol='GBPUSD', base_tf='H1', source_id='broker', tick_size='0.00001',
                                           distance_unit='0.0001', **metadata, sha256=sha256(raw).hexdigest())))
        return dict(path=str(path), manifest=str(manifest))
    monkeypatch.setattr(current_data, 'collect_job', collect)


def point(at, close='1.25'):
    return (at.isoformat(), '1.25', '1.26', '1.24', close, '10')


def test_cache_reuses_same_hour_and_only_fetches_overlap_next_hour(tmp_path, monkeypatch):
    calls=[]
    acquisition(monkeypatch, [point(T-timedelta(hours=1))], calls)
    first = current_data.refresh(None, 'GBPUSD', METADATA, tmp_path, as_of=T)
    assert not first['reused'] and len(calls)==1
    assert current_data.refresh(None, 'GBPUSD', METADATA, tmp_path, as_of=T)['reused']
    assert len(calls)==1
    acquisition(monkeypatch, [point(T-timedelta(hours=1)), point(T)], calls)
    latest = current_data.refresh(None, 'GBPUSD', METADATA, tmp_path, as_of=T+timedelta(hours=1))
    assert calls[-1]['start'] == (T-timedelta(hours=49)).isoformat()
    assert json.loads(Path(latest['manifest']).read_text())['rows'] == 2
    assert not (tmp_path/'delta').exists()


def test_revision_fails_without_rewriting_frozen_cache(tmp_path, monkeypatch):
    acquisition(monkeypatch, [point(T-timedelta(hours=1))], [])
    first = current_data.refresh(None, 'GBPUSD', METADATA, tmp_path, as_of=T)
    original = Path(first['path']).read_bytes()
    acquisition(monkeypatch, [point(T-timedelta(hours=1), '1.251')], [])
    with pytest.raises(ValueError, match='changed'):
        current_data.refresh(None, 'GBPUSD', METADATA, tmp_path, as_of=T+timedelta(hours=1))
    assert Path(first['path']).read_bytes() == original
    assert (tmp_path/'delta').exists()  # disputed source data preserved


def test_current_source_refuses_unknown_calendar_before_broker_request(tmp_path):
    with pytest.raises(ValueError, match='FX symbol'):
        current_data.refresh(None, 'GBPUSD', {**METADATA,'calendar_id':'unresolved_broker_schedule'}, tmp_path, as_of=T)


def test_same_hour_cli_reuse_does_not_need_broker_auth(tmp_path, monkeypatch):
    acquisition(monkeypatch, [point(T-timedelta(hours=1))], [])
    metadata = json.loads(Path('reports/teacher_icmarkets_metadata.json').read_text())['GBPUSD']
    current_data.refresh(None, 'GBPUSD', metadata, tmp_path/'cache', as_of=T)
    def no_broker():
        raise AssertionError('A cached hour must not authenticate')
    monkeypatch.setattr(current_data, 'HistoricalClient', no_broker)
    assert current_data.main(['--pair','GBPUSD','--cache',str(tmp_path/'cache'),
                              '--as-of',T.isoformat(),'--out',str(tmp_path/'status.json')]) is None
    assert json.loads((tmp_path/'status.json').read_text())['reused'] is True


def test_same_hour_cache_rejects_changed_anchor_or_warmup(tmp_path, monkeypatch):
    acquisition(monkeypatch, [point(T-timedelta(hours=1))], [])
    current_data.refresh(None, 'GBPUSD', METADATA, tmp_path, as_of=T)
    with pytest.raises(ValueError, match='metadata changed'):
        current_data.refresh(None, 'GBPUSD', {**METADATA,'anchor_id':'other'}, tmp_path, as_of=T)
    with pytest.raises(ValueError, match='warmup changed'):
        current_data.refresh(None, 'GBPUSD', METADATA, tmp_path, as_of=T, days=35)

"""Literal candle components and frozen snapshot boundaries, no detector run."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json

import pytest
from bishop.v2.types import Bar,Instrument
from reports import trace_teacher_candles as mod

T=datetime(2026,7,9,tzinfo=timezone.utc)


def test_components_use_exact_engine_engulfing_including_segment_boundary():
    a=Bar('X','H2',T,T+timedelta(hours=2),100,111,99,110)
    b=Bar('X','H2',a.end,a.end+timedelta(hours=2),110,112,98,99)
    assert mod._components(a,b,'SELL')['engine_engulfs'] is True
    assert mod._components(a,b,'BUY')['engine_engulfs'] is False
    separated=Bar('X','H2',b.start,b.end,110,112,98,99,segment_id='new')
    result=mod._components(a,separated,'SELL')
    assert result['body_low_covers'] and result['body_high_covers']
    assert not result['same_segment'] and not result['engine_engulfs']


def test_trace_rejects_future_aggregate_instead_of_exporting_it(tmp_path,monkeypatch):
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'sha256':'frozen',
        'calendar_id':'24x7_utc_v1','anchor_id':'utc_epoch_v1'}))
    report=tmp_path/'report.json';report.write_text(json.dumps({'fixture_sha256':'fixture',
        'source_plan':{},'plan_groups':[],'plan':{'manifest_path':str(manifest),
        'manifest_sha256':sha256(manifest.read_bytes()).hexdigest(),'input_sha256':'frozen',
        'input_path':'unused','history_start':T.isoformat(),'scan_start':T.isoformat(),
        'as_of':(T+timedelta(hours=4)).isoformat()}}))
    monkeypatch.setattr(mod,'load_feed',lambda *a:{'bars':(),
        'instrument':Instrument('X','1','1'),'coverage':{}})
    future=Bar('X','H2',T+timedelta(hours=4),T+timedelta(hours=6),100,111,99,110)
    monkeypatch.setattr(mod,'aggregate',lambda *a,**k:{'bars':(future,),'coverage':{}})
    with pytest.raises(ValueError,match='future or incomplete aggregate'):
        mod.trace(report,T.isoformat())

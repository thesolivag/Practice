"""Offline protocol/calendar contract checks, synthetic schedules and files only."""
from datetime import datetime, timezone
from hashlib import sha256
import gzip
import json
import pytest
from bishop.teacher_calendar import build_calendar, derive_snapshot, UnsupportedCalendar


def record(zone='UTC', intervals=None, holiday=None):
    return {'name':'X','scheduleTimeZone':zone,
            'schedule':intervals if intervals is not None else [{'startSecond':86400,'endSecond':2*86400}],
            'holiday':holiday if holiday is not None else []}


def test_sunday_origin_inclusive_start_exclusive_end():
    r=build_calendar(record(), '2026-05-03T00:00:00Z','2026-05-06T00:00:00Z')
    assert r['status']=='SUPPORTED_HYPOTHESIS'
    assert r['calendar']['open_intervals']==[['2026-05-04T00:00:00+00:00','2026-05-05T00:00:00+00:00']]
    assert r['certification']=='NOT_HISTORICAL_CALENDAR_CERTIFICATION'


@pytest.mark.parametrize('intervals',[
    [{'startSecond':-1,'endSecond':20}],
    [{'startSecond':1,'endSecond':604801}],
    [{'startSecond':False,'endSecond':2}],
    [{'startSecond':20,'endSecond':10}],
    [{'startSecond':0,'endSecond':100},{'startSecond':90,'endSecond':120}],
])
def test_invalid_weekly_intervals_block(intervals):
    assert build_calendar(record(intervals=intervals),'2026-05-03T00:00:00Z','2026-05-06T00:00:00Z')['status']=='UNSUPPORTED'


def test_timezone_no_alias_guess_and_dst_transition_rejected():
    assert build_calendar(record('BrokerCustomGMT'),'2026-05-03T00:00:00Z','2026-05-06T00:00:00Z')['status']=='UNSUPPORTED'
    r=build_calendar(record('America/New_York'),'2026-05-04T00:00:00Z','2026-05-06T00:00:00Z')
    assert r['status']=='SUPPORTED_HYPOTHESIS'
    assert r['calendar']['open_intervals'][0][0]=='2026-05-04T04:00:00+00:00'
    r=build_calendar(record('America/New_York'),'2026-11-01T04:00:00Z','2026-11-04T00:00:00Z')
    assert r['status']=='UNSUPPORTED' and 'DST' in r['reason']


def test_holiday_epoch_days_recurring_explicit_and_unknown_optional_fields():
    epoch=datetime(1970,1,1,tzinfo=timezone.utc)
    days=(datetime(2025,5,4,tzinfo=timezone.utc)-epoch).days
    h={'holidayDate':days,'isRecurring':True,'scheduleTimeZone':'UTC','startSecond':3600,'endSecond':7200}
    r=build_calendar(record(holiday=[h]),'2026-05-03T00:00:00Z','2026-05-06T00:00:00Z')
    assert r['calendar']['closed_intervals']==[['2026-05-04T01:00:00+00:00','2026-05-04T02:00:00+00:00']]
    del h['startSecond']
    r=build_calendar(record(holiday=[h]),'2026-05-03T00:00:00Z','2026-05-06T00:00:00Z')
    assert r['status']=='UNSUPPORTED' and 'OPTIONAL_HOLIDAY' in r['reason']


def files(tmp_path, asset='METAL_CFD'):
    raw=gzip.compress(b'time,open,high,low,close,volume\n2026-05-03T23:00:00Z,1,2,0,1,0\n2026-05-04T00:00:00Z,1,2,0,1,0\n2026-05-04T02:00:00Z,1,2,0,1,3\n',mtime=0)
    p=tmp_path/'raw.csv.gz';p.write_bytes(raw)
    m={'symbol':'X','broker_symbol':'X','base_tf':'H1','requested_start':'2026-05-03T23:00:00Z','requested_end':'2026-05-04T03:00:00Z',
       'sha256':sha256(raw).hexdigest(),'asset_class':asset,'zero_volume_rows':2}
    mp=tmp_path/'raw.manifest.json';mp.write_text(json.dumps(m))
    sp=tmp_path/'schedule.json';sp.write_text(json.dumps({'symbols':[{'requested_pair':'X','broker_symbol':'X','record':record()}]}))
    return p,mp,sp,raw


def test_derived_frozen_file_preserves_raw_zero_volume_and_inside_gaps(tmp_path):
    p,mp,sp,raw=files(tmp_path)
    before=(p.read_bytes(),mp.read_bytes(),sp.read_bytes())
    output=derive_snapshot(p,mp,sp,tmp_path/'derived')
    ledger=json.loads(open(output['ledger']).read()); manifest=json.loads(open(output['manifest']).read())
    assert ledger['missing_in_session_slots']==['2026-05-04T01:00:00+00:00']
    assert ledger['excluded_rows'][0]['reason']=='OUTSIDE_DECLARED_CALENDAR'
    assert ledger['retained_rows']==2 and ledger['coverage_status']=='INCOMPLETE'
    content=gzip.decompress(open(output['path'],'rb').read()).decode()
    assert '2026-05-04T00:00:00Z,1,2,0,1,0' in content
    assert '23:00' not in content and '01:00' not in content
    assert manifest['calendar_id']=='explicit_intervals_v1'
    assert manifest['replay_calendar_status'].endswith('DIAGNOSTIC_ONLY')
    assert (p.read_bytes(),mp.read_bytes(),sp.read_bytes())==before
    with pytest.raises(FileExistsError):derive_snapshot(p,mp,sp,tmp_path/'derived')


def test_surrogate_stays_blocked(tmp_path):
    p,mp,sp,_=files(tmp_path,'CRYPTO_SURROGATE')
    with pytest.raises(UnsupportedCalendar,match='SURROGATE'):derive_snapshot(p,mp,sp,tmp_path/'derived')


def test_explicit_subset_keeps_raw_evidence_and_crop_ledger(tmp_path):
    p,mp,sp,raw=files(tmp_path)
    output=derive_snapshot(p,mp,sp,tmp_path/'derived',start='2026-05-04T01:00:00Z',end='2026-05-04T03:00:00Z')
    ledger=json.loads(open(output['ledger']).read());m=json.loads(open(output['manifest']).read())
    assert ledger['raw_sha256']==sha256(raw).hexdigest()
    assert ledger['derived_subset_range']==['2026-05-04T01:00:00+00:00','2026-05-04T03:00:00+00:00']
    assert m['requested_start']=='2026-05-04T01:00:00+00:00'
    assert m['raw_requested_range'][0]=='2026-05-03T23:00:00+00:00'
    assert m['rows']==1 and m['zero_volume_rows']==0
    assert len(ledger['excluded_rows'])==2
    assert all(r['reason']=='OUTSIDE_DERIVED_SUBSET' for r in ledger['excluded_rows'])
    assert p.read_bytes()==raw
    with pytest.raises(ValueError,match='within'):derive_snapshot(p,mp,sp,tmp_path/'bad',start='2026-05-02T00:00:00Z')


def test_subset_can_avoid_unsupported_dst_context_and_batch_keeps_refusals(tmp_path):
    from bishop.teacher_calendar import derive_batch
    p,mp,sp,raw=files(tmp_path)
    m=json.loads(mp.read_text());m['requested_start']='2025-06-01T00:00:00Z';mp.write_text(json.dumps(m))
    schedules=json.loads(sp.read_text());schedules['symbols'][0]['record']=record('America/New_York');sp.write_text(json.dumps(schedules))
    with pytest.raises(UnsupportedCalendar,match='DST'):derive_snapshot(p,mp,sp,tmp_path/'full')
    inputs=[{'path':p,'manifest':mp}, {'path':p,'manifest':mp,'start':'2026-05-03T23:00:00Z','end':'2026-05-04T03:00:00Z'}]
    results=derive_batch(inputs,sp,tmp_path/'subset')
    assert [r['status'] for r in results]==['UNSUPPORTED','DERIVED_HYPOTHESIS']
    assert json.loads(open(results[1]['manifest']).read())['calendar_derivation']['raw_sha256']==sha256(raw).hexdigest()


def test_disputed_quote_withheld_as_required_gap_censors_existing_exposure(tmp_path):
    from bishop.v2.feed import load_feed
    from bishop.v2.simulation import simulate, Costs
    from bishop.v2.types import Order, Clock, utc
    # One quote contradicts a one-minute current-schedule closure.
    text='time,open,high,low,close,volume\n'+''.join(
        f'2026-05-04T00:0{i}:00Z,100,101,99,100,7\n' for i in range(5))
    raw=gzip.compress(text.encode(),mtime=0)
    p=tmp_path/'raw.csv.gz';p.write_bytes(raw)
    m={'symbol':'X','broker_symbol':'X','base_tf':'M1','requested_start':'2026-05-04T00:00:00Z','requested_end':'2026-05-04T00:05:00Z',
       'sha256':sha256(raw).hexdigest(),'asset_class':'METAL_CFD','tick_size':'1','distance_unit':'1',
       'calendar_id':'unresolved_broker_schedule','anchor_id':'utc_epoch_v1','price_basis':'BID','source_id':'test','venue':'TEST'}
    mp=tmp_path/'raw.manifest.json';mp.write_text(json.dumps(m))
    rec=record(intervals=[{'startSecond':86400,'endSecond':86520},{'startSecond':86580,'endSecond':86700}])
    sp=tmp_path/'schedule.json';sp.write_text(json.dumps({'symbols':[{'requested_pair':'X','broker_symbol':'X','record':rec}]}))
    strict=derive_snapshot(p,mp,sp,tmp_path/'strict')
    uncertain=derive_snapshot(p,mp,sp,tmp_path/'uncertain',withhold_disputed_slots=True)
    assert strict['path']!=uncertain['path']
    manifest=json.loads(open(uncertain['manifest']).read());ledger=json.loads(open(uncertain['ledger']).read())
    assert manifest['calendar_conflicts_handled_as_missing_observations'] is True
    assert manifest['calendar_conflict_required_missing_slots']==['2026-05-04T00:02:00+00:00']
    assert ledger['missing_in_session_slots']==['2026-05-04T00:02:00+00:00']
    assert '00:02:00Z' not in gzip.decompress(open(uncertain['path'],'rb').read()).decode()
    assert p.read_bytes()==raw and '00:02:00Z' in gzip.decompress(raw).decode()
    feed=load_feed(uncertain['path'],manifest,'2026-05-04T00:05:00Z')
    assert feed['coverage']['missing_slots']==1 and feed['bars'][2].segment_id!=feed['bars'][1].segment_id
    def order(oid,at):
        at=utc(at)
        return Order(id=oid,setup_id=oid,instrument='X',tf='M1',model='test',side='BUY',kind='MARKET',clock=Clock(at,at,at),entry_ticks=100,stop_ticks=90,target_ticks=110)
    result=simulate((order('across','2026-05-04T00:00:00Z'),order('after','2026-05-04T00:03:00Z')),feed['bars'],feed['instrument'],Costs(),'2026-05-04T00:05:00Z',calendar=manifest['calendar'])
    byid={r['id']:r for r in result['observations']}
    assert byid['across']['outcome']=='CENSORED' and byid['across']['censor_reason']=='MISSING_ACTIVE_DATA'
    assert byid['after']['outcome']!='CENSORED'


def test_required_disputed_slot_is_removed_from_closed_holiday_mask():
    from bishop.teacher_calendar import _required_observations
    from bishop.v2.aggregation import expected_slots
    c={'id':'explicit_intervals_v1','open_intervals':[['2026-05-04T00:00:00Z','2026-05-04T00:05:00Z']],
       'closed_intervals':[['2026-05-04T00:01:00Z','2026-05-04T00:04:00Z']]}
    obs=_required_observations(c,[{'start':'2026-05-04T00:02:00Z','end':'2026-05-04T00:03:00Z'}])
    slots=list(expected_slots('2026-05-04T00:00:00Z','2026-05-04T00:05:00Z','M1',obs))
    assert [s.minute for s in slots]==[0,2,4]
    assert obs['disputed_slots_are_tradable'] is False

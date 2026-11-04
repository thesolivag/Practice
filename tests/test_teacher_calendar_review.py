"""Independent calendar relevance and raw-boundary checks; offline synthetic data."""
from datetime import datetime,timezone
from hashlib import sha256
import gzip,json
import pytest
from bishop.teacher_calendar import build_calendar,derive_snapshot,UnsupportedCalendar


def weekly(holiday):
    return dict(name='X',scheduleTimeZone='UTC',schedule=[{'startSecond':86400,'endSecond':172800}],holiday=holiday)


@pytest.mark.parametrize('recurring',[False,True])
@pytest.mark.parametrize('limits',['zero','unknown'])
def test_irrelevant_january_holiday_does_not_block_may_calendar(recurring,limits):
    day=(datetime(2026,1,1,tzinfo=timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)).days
    holiday=dict(holidayDate=day,isRecurring=recurring)
    if limits=='zero':holiday.update(startSecond=0,endSecond=0,scheduleTimeZone='UTC')
    # Even unknown intraday limits/timezone cannot move January into May.
    result=build_calendar(weekly([holiday]),'2026-05-03T00:00:00Z','2026-05-06T00:00:00Z')
    reference=build_calendar(weekly([]),'2026-05-03T00:00:00Z','2026-05-06T00:00:00Z')
    assert result['status']=='SUPPORTED_HYPOTHESIS'
    assert result['calendar']==reference['calendar']
    assert result['certification']=='NOT_HISTORICAL_CALENDAR_CERTIFICATION'


def test_in_range_unknown_holiday_limits_remain_unsupported():
    day=(datetime(2026,5,4,tzinfo=timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)).days
    result=build_calendar(weekly([dict(holidayDate=day,isRecurring=False)]),
                          '2026-05-03T00:00:00Z','2026-05-06T00:00:00Z')
    assert result['status']=='UNSUPPORTED'


def test_1659_session_end_is_not_rounded_to_five_minute_boundary(tmp_path):
    raw=gzip.compress(b'time,open,high,low,close\n2026-05-04T00:00:00Z,1,2,0,1\n',mtime=0)
    path=tmp_path/'raw.csv.gz';path.write_bytes(raw)
    metadata=dict(symbol='X',broker_symbol='X',base_tf='M5',asset_class='INDEX_CFD',
                  sha256=sha256(raw).hexdigest(),requested_start='2026-05-04T00:00:00Z',requested_end='2026-05-05T00:00:00Z')
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(metadata))
    record=weekly([]);record['schedule']=[{'startSecond':86400,'endSecond':86400+16*3600+59*60}]
    schedules=tmp_path/'schedule.json';schedules.write_text(json.dumps({'symbols':[
        {'requested_pair':'X','broker_symbol':'X','record':record}]}))
    with pytest.raises(UnsupportedCalendar,match='NOT_BASE_ALIGNED'):
        derive_snapshot(path,manifest,schedules,tmp_path/'output')
    assert path.read_bytes()==raw and not (tmp_path/'output').exists()


@pytest.mark.parametrize('holiday',[
    {'holidayDate':'not-a-date','isRecurring':False},
    {'holidayDate':True,'isRecurring':False},
    {'holidayDate':0,'isRecurring':'unknown'},
])
def test_malformed_holiday_date_cannot_be_skipped_as_irrelevant(holiday):
    result=build_calendar(weekly([holiday]),'2026-05-03T00:00:00Z','2026-05-06T00:00:00Z')
    assert result['status']=='UNSUPPORTED'


def test_relevant_missing_timezone_and_adjacent_utc_date_remain_unsupported():
    day=(datetime(2026,5,4,tzinfo=timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)).days
    # A local May4 holiday might overlap UTC May3 under a positive UTC offset.
    holiday=dict(holidayDate=day,isRecurring=False,startSecond=0,endSecond=3600)
    result=build_calendar(weekly([holiday]),'2026-05-03T12:00:00Z','2026-05-03T23:00:00Z')
    assert result['status']=='UNSUPPORTED'
    assert 'HOLIDAY' in result['reason']


def test_exact_timezone_day_outside_window_does_not_invent_a_holiday_closure():
    day=(datetime(2026,5,4,tzinfo=timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)).days
    holiday=dict(holidayDate=day,isRecurring=False,scheduleTimeZone='UTC',startSecond=0,endSecond=0)
    result=build_calendar(weekly([holiday]),'2026-05-03T12:00:00Z','2026-05-04T00:00:00Z')
    assert result['status']=='SUPPORTED_HYPOTHESIS'
    assert result['calendar']['closed_intervals']==[]

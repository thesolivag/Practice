"""Compiled membership equals the literal calendar; no timing/source changes."""
from datetime import datetime,timedelta,timezone
from copy import deepcopy
import pytest
from bishop.v2.aggregation import calendar_open_lookup,is_open,expected_slots

T=datetime(2026,1,1,tzinfo=timezone.utc)


def test_overlapping_touching_closed_and_right_open_boundaries():
    calendar={'id':'explicit_intervals_v1','open_intervals':[
        (T,T+timedelta(hours=2)),(T+timedelta(hours=1),T+timedelta(hours=3)),
        (T+timedelta(hours=3),T+timedelta(hours=4)),(T,T)],
        'closed_intervals':[(T+timedelta(minutes=30),T+timedelta(hours=1)),
                            (T+timedelta(hours=1),T+timedelta(hours=2))]}
    original=deepcopy(calendar);lookup=calendar_open_lookup(calendar)
    for i in range(-1,4*60+2):
        at=T+timedelta(minutes=i)
        assert lookup(at)==is_open(at,calendar)
    assert lookup(T) and not lookup(T+timedelta(hours=4))
    assert lookup(T+timedelta(hours=2))  # Closed union's right edge reopens.
    assert calendar==original


@pytest.mark.parametrize('first,last',[
    ('2026-03-08T01:00:00-05:00','2026-03-08T04:00:00-04:00'),
    ('2026-11-01T00:30:00-04:00','2026-11-01T02:30:00-05:00')])
def test_offset_and_dst_intervals_are_literal_utc_membership(first,last):
    calendar={'id':'explicit_intervals_v1','open_intervals':[(first,last)]}
    lookup=calendar_open_lookup(calendar)
    start=datetime.fromisoformat(first).astimezone(timezone.utc)-timedelta(hours=1)
    for i in range(6*60):
        at=start+timedelta(minutes=i)
        assert lookup(at)==is_open(at,calendar)
    assert list(expected_slots(start,start+timedelta(hours=6),'M1',calendar))==[
        start+timedelta(minutes=i) for i in range(6*60) if is_open(start+timedelta(minutes=i),calendar)]


@pytest.mark.parametrize('calendar',[{'id':'explicit_intervals_v1'},
    {'id':'explicit_intervals_v1','open_intervals':[(T+timedelta(hours=2),T)]},
    'fx_ny_v1','24x7_utc_v1'])
def test_empty_reversed_and_standard_calendars(calendar):
    lookup=calendar_open_lookup(calendar)
    assert [lookup(T+timedelta(hours=i)) for i in range(96)]==[
        is_open(T+timedelta(hours=i),calendar) for i in range(96)]


def test_malformed_later_interval_preserves_literal_short_circuit():
    calendar={'id':'explicit_intervals_v1','open_intervals':[
        (T,T+timedelta(hours=1)),('malformed',T)]}
    lookup=calendar_open_lookup(calendar)
    assert lookup(T)==is_open(T,calendar)
    for query in (lookup,lambda t:is_open(t,calendar)):
        with pytest.raises(ValueError):query(T+timedelta(hours=2))


def test_empty_expected_range_never_compiles_calendar(monkeypatch):
    import bishop.v2.aggregation as aggregation
    monkeypatch.setattr(aggregation,'calendar_open_lookup',lambda c:pytest.fail('empty range compiled'))
    assert list(expected_slots(T,T,'M1',{'id':'not-valid'}))==[]
    assert list(expected_slots(T,T-timedelta(hours=1),'M1',None))==[]

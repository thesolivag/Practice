import pandas as pd
import pytest
from fzasm.native_daily import candles_from_native_daily


def frame(times):
    index = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    return pd.DataFrame({'open':100.,'high':110.,'low':90.,'close':105.},index=index)


def test_intraday_never_exposes_future_native_daily_ohlc():
    df=frame(['2026-03-02T22:00Z','2026-03-03T22:00Z','2026-03-04T22:00Z'])
    at=pd.Timestamp('2026-03-04T10:00Z')
    before,audit=candles_from_native_daily(df,at)
    assert len(before)==1 and before[0].available_at==df.index[1]
    df.loc[df.index[1]:,'high']=999.
    after,_=candles_from_native_daily(df,at)
    assert before==after
    assert audit['omitted_future_or_unclosed']==1
    assert audit['omitted_last_without_close']==1


@pytest.mark.parametrize('times,hours',[
    (['2026-03-08T22:00Z','2026-03-09T21:00Z'],23),
    (['2026-11-01T21:00Z','2026-11-02T22:00Z'],25),
])
def test_23_and_25_hour_native_boundaries_are_not_assumed_24h(times,hours):
    df=frame(times);bars,_=candles_from_native_daily(df,df.index[-1])
    assert len(bars)==1
    assert bars[0].available_at==df.index[-1]
    assert (bars[0].available_at-bars[0].timestamp).total_seconds()==hours*3600


def test_missing_weekday_omitted_but_weekend_conservatively_delayed():
    missing=frame(['2026-03-02T22:00Z','2026-03-04T22:00Z'])
    bars,audit=candles_from_native_daily(missing,'2026-03-05T00:00Z')
    assert bars==[] and audit['omitted_gap_rows']==1
    assert not audit['gaps'][0]['spans_utc_weekend']
    assert len(audit['missing_weekday_gaps'])==1
    weekend=frame(['2026-03-06T22:00Z','2026-03-09T21:00Z'])
    bars,audit=candles_from_native_daily(weekend,'2026-03-10T00:00Z')
    assert len(bars)==1 and audit['gaps'][0]['spans_utc_weekend']
    assert bars[0].available_at==weekend.index[1]
    assert audit['gaps'][0]['gap_hours']==71
    assert audit['weekend_delayed_rows']==1
    assert audit['missing_weekday_gaps']==[]
    assert candles_from_native_daily(weekend,'2026-03-09T20:59Z')[0]==[]


def test_explicit_provider_close_admits_last_only_when_closed():
    df=frame(['2026-03-03T22:00Z'])
    df['closed_at']=['2026-03-04T21:00Z']
    bars,_=candles_from_native_daily(df,'2026-03-04T20:59Z')
    assert bars==[]
    bars,_=candles_from_native_daily(df,'2026-03-04T21:00Z')
    assert len(bars)==1 and bars[0].available_at==pd.Timestamp('2026-03-04T21:00Z')
    df['closed_at']=['2026-03-03T21:00Z']
    with pytest.raises(ValueError,match='closed_at'):candles_from_native_daily(df,'2026-03-05T00:00Z')


def test_rejects_naive_non_utc_duplicate_and_invalid_prices():
    df=frame(['2026-03-02T22:00Z','2026-03-03T22:00Z'])
    with pytest.raises(ValueError,match='UTC'):candles_from_native_daily(df,'2026-03-04')
    for index in (df.index.tz_localize(None),df.index.tz_convert('Europe/Athens'),pd.DatetimeIndex([df.index[0]]*2),df.index[::-1]):
        bad=df.copy();bad.index=index
        with pytest.raises(ValueError):candles_from_native_daily(bad,'2026-03-04T00:00Z')
    for value in (80.,float('nan'),float('inf')):
        bad=df.copy();bad.iloc[0,bad.columns.get_loc('high')]=value
        with pytest.raises(ValueError):candles_from_native_daily(bad,'2026-03-04T00:00Z')


def test_explicit_provider_close_may_resolve_gap_without_bridging_it():
    df=frame(['2026-03-02T22:00Z','2026-03-04T22:00Z'])
    df['closed_at']=['2026-03-03T22:00Z',None]
    bars,audit=candles_from_native_daily(df,'2026-03-05T00:00Z')
    assert len(bars)==1 and bars[0].available_at==pd.Timestamp('2026-03-03T22:00Z')
    assert audit['gaps'][0]['omitted'] is False
    assert audit['omitted_gap_rows']==0


@pytest.mark.parametrize('times,expected',[
    (['2026-03-05T22:00Z','2026-03-08T21:00Z'],True),
    (['2026-03-06T22:00Z','2026-03-09T22:00Z'],True),
    (['2026-03-05T22:00Z','2026-03-09T21:00Z'],False),
    (['2026-03-04T22:00Z','2026-03-08T21:00Z'],False),
    (['2026-03-09T22:00Z','2026-03-11T22:00Z'],False),
])
def test_only_bounded_native_weekend_gaps_are_retained(times,expected):
    df=frame(times);bars,audit=candles_from_native_daily(df,df.index[-1])
    assert bool(bars)==expected
    assert bool(audit['missing_weekday_gaps']) is not expected
    if expected:
        assert bars[0].available_at==df.index[-1]
        assert bars[0].high==110. and bars[0].low==90.
        assert audit['weekend_delayed_rows']==1

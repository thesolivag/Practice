import math
import time

import numpy as np
import pandas as pd
import pytest
from slk import alert_data as A, deriv, store


def bars(start, count, grain=60):
    index = pd.date_range(start, periods=count, freq=pd.Timedelta(seconds=grain))
    frame = pd.DataFrame({'open': 1., 'high': 2., 'low': .5, 'close': 1.5}, index=index)
    frame.attrs['granularity'] = grain
    return frame


def test_minute_aggregation_waits_for_nominal_close_and_rejects_gaps():
    source = bars('2026-10-20 00:00Z', 11)
    now = pd.Timestamp('2026-10-20 00:10Z')
    complete = A.complete_bars(source, 'M5', 'DVR25', now)
    assert len(complete) == 2
    assert complete.end.tolist() == [pd.Timestamp('2026-10-20 00:05Z'), now]
    assert complete.close.tolist() == [1.5, 1.5]
    missing = source.drop(source.index[2])
    missing.attrs['granularity'] = 60
    result = A.complete_bars(missing, 'M5', 'DVR25', now)
    assert len(result) == 1 and result.start.iat[0] == pd.Timestamp('2026-10-20 00:05Z')
    result = A.complete_bars(source, 'M15', 'DVR25', now)
    assert result.empty


def test_hourly_source_cannot_fabricate_subhour_and_leading_partial_is_not_full():
    hourly = bars('2026-10-20 21:00Z', 4, 3600)
    with pytest.raises(ValueError, match='Finer source'):
        A.complete_bars(hourly, 'M30', 'EURUSD', pd.Timestamp('2026-10-21 01:00Z'))
    assert len(A.complete_bars(hourly, 'H4', 'EURUSD', pd.Timestamp('2026-10-21 01:00Z'))) == 1
    assert A.complete_bars(hourly.iloc[1:], 'H4', 'EURUSD', pd.Timestamp('2026-10-21 01:00Z')).empty


@pytest.mark.parametrize('start', ['2026-10-26 21:00Z', '2026-11-02 22:00Z'])
def test_forex_daily_edges_follow_new_york_through_dst(start):
    hourly = bars(start, 24, 3600)
    now = hourly.index[-1] + pd.Timedelta(hours=1)
    result = A.complete_bars(hourly, 'D', 'EURUSD', now)
    assert len(result) == 1
    assert result.start.iat[0] == pd.Timestamp(start)
    assert result.end.iat[0] == now
    assert A.complete_bars(hourly, 'D', 'DVR25', now).empty


def test_weekly_fx_five_days_deriv_seven_days():
    fx = bars('2026-10-18 21:00Z', 120, 3600)
    result = A.complete_bars(fx, 'W', 'EURUSD', pd.Timestamp('2026-10-23 21:00Z'))
    assert len(result) == 1 and result.end.iat[0] - result.start.iat[0] == pd.Timedelta(days=5)
    dv = bars('2026-10-19 00:00Z', 168, 3600)
    result = A.complete_bars(dv, 'W', 'DVR25', pd.Timestamp('2026-10-26 00:00Z'))
    assert len(result) == 1 and result.end.iat[0] - result.start.iat[0] == pd.Timedelta(days=7)
    assert A.complete_bars(dv.iloc[:-1], 'W', 'DVR25', pd.Timestamp('2026-10-26 00:00Z')).empty


def test_invalid_closed_ohlc_fails_closed_and_future_bars_do_not_leak():
    source = bars('2026-10-20 00:00Z', 6)
    source.loc[source.index[0], 'close'] = math.inf
    with pytest.raises(ValueError, match='Invalid broker'):
        A.complete_bars(source, 'M5', 'DVR25', pd.Timestamp('2026-10-20 00:05Z'))
    source.loc[source.index[0], 'close'] = 1.5
    source.loc[source.index[-1], 'close'] = math.inf
    result = A.complete_bars(source, 'M5', 'DVR25', pd.Timestamp('2026-10-20 00:05Z'))
    assert len(result) == 1


def test_all_intraday_intervals_use_full_component_windows():
    source = bars('2026-10-20 00:00Z', 24 * 60)
    for tf, minutes in A.TF_MINUTES.items():
        result = A.complete_bars(source, tf, 'DVR25', pd.Timestamp('2026-10-21 00:00Z'))
        assert len(result) == 1440 // minutes
        assert all((result.end - result.start) == pd.Timedelta(minutes=minutes))


def _fake_cache(monkeypatch, now):
    monkeypatch.setattr(store, 'update', lambda *args, **kwargs: None)
    class Cache:
        def __init__(self, pair): self.src = 'deriv' if pair.startswith('DV') else 'ctrader'
        def frame(self, lo=None): return bars(now.floor('h') - pd.Timedelta(hours=2), 2, 3600)
    monkeypatch.setattr(store, 'Pair', Cache)


def test_selected_provider_connections_are_shared_and_never_cross_routed(monkeypatch):
    now = pd.Timestamp('2026-10-20 12:07Z')
    _fake_cache(monkeypatch, now)
    opened, calls = [], []
    class DV:
        def __init__(self, **kwargs): opened.append('deriv')
        def __enter__(self): return self
        def __exit__(self, *args): calls.append(('close', 'deriv'))
        def prefetch(self, pairs=None): calls.append(('deriv-symbols', pairs))
        def info(self, pair):
            assert pair.startswith('DV')
            return {'symbol': pair[2:]}
        def request(self, payload):
            assert payload['ticks_history'] in ('R25', 'R75')
            if payload['style'] == 'ticks': return {'history': {'prices': [2.], 'times': [int(now.timestamp())]}}
            assert payload['count'] <= 720
            lo, hi = payload['start'], int(payload['end']) + 1
            calls.append(('minutes', payload['ticks_history']))
            return {'candles': [{'epoch': stamp, 'open': 1, 'high': 2, 'low': .5, 'close': 1.5} for stamp in range(lo, hi, 60)]}
    class IC:
        def __init__(self): opened.append('ctrader')
        def get_symbols(self, pairs): calls.append(('ctrader-symbols', pairs))
        def get_trendbars(self, pair, period, lo, hi):
            assert pair == 'EURUSD' and period == 'M1'
            return bars(lo, 1441)
        def get_spot(self, pair, timeout=None): return (1.2, 1.21)
        def close(self): calls.append(('close', 'ctrader'))
    monkeypatch.setattr(deriv, 'Feed', DV)
    monkeypatch.setattr(A, '_open_ctrader', IC)
    monkeypatch.setattr(A.time, 'time', lambda: now.timestamp())
    result = A.load(['DVR25', 'DVR75', 'EURUSD', 'EURUSD'], now)
    assert opened == ['deriv', 'ctrader']
    assert set(result) == {'DVR25', 'DVR75', 'EURUSD'}
    assert all(len(row['frame']) == 1440 for row in result.values())
    assert all(row['frame'].attrs['granularity'] == 60 for row in result.values())
    assert all(len(row['hourly']) == 2 for row in result.values())
    assert result['DVR25']['quote'] == 2 and result['EURUSD']['quote'] == 1.2
    assert ('close', 'deriv') in calls and ('close', 'ctrader') in calls


def test_data_budget_defers_without_provider_calls(monkeypatch):
    monkeypatch.setattr(A, '_open_ctrader', lambda: pytest.fail('no connection after budget'))
    result = A.load(['EURUSD'], pd.Timestamp('2026-10-20 12:00Z'), deadline=time.monotonic() - 1)
    assert result['EURUSD']['frame'].empty
    assert 'deferred' in result['EURUSD']['error']


def test_minute_failure_preserves_hourly_and_can_still_get_quote(monkeypatch):
    now = pd.Timestamp('2026-10-20 12:07Z')
    _fake_cache(monkeypatch, now)
    class IC:
        def get_symbols(self, pairs): pass
        def get_trendbars(self, *args): raise RuntimeError('minute data unavailable')
        def get_spot(self, *args, **kwargs): return (1.2, 1.3)
        def close(self): pass
    monkeypatch.setattr(A, '_open_ctrader', IC)
    result = A.load(['EURUSD'], now)['EURUSD']
    assert result['frame'].empty and len(result['hourly']) == 2 and result['quote'] == 1.2
    assert 'minute data unavailable' in result['error']


def test_ambiguous_new_york_clock_is_not_guessed():
    source = bars('2026-11-01 05:00Z', 120)
    result = A.complete_bars(source, 'M30', 'BTCUSD', pd.Timestamp('2026-11-01 07:00Z'))
    assert result.empty


@pytest.mark.parametrize('unit', ['s', 'ms', 'us', 'ns'])
def test_provider_timestamp_resolution_does_not_change_closed_bars(unit):
    minute = bars('2026-10-20 00:00Z', 60)
    minute.index = minute.index.as_unit(unit)
    now = pd.Timestamp('2026-10-20 01:00Z')
    result = A.complete_bars(minute, 'M5', 'DVR25', now)
    assert len(result) == 12
    assert result.start.iat[0] == pd.Timestamp('2026-10-20 00:00Z')
    assert result.end.iat[-1] == now
    hourly = bars('2026-10-20 21:00Z', 4, 3600)
    hourly.index = hourly.index.as_unit(unit)
    result = A.complete_bars(hourly, 'H4', 'EURUSD', pd.Timestamp('2026-10-21 01:00Z'))
    assert len(result) == 1
    assert result.start.iat[0] == pd.Timestamp('2026-10-20 21:00Z')
    assert result.end.iat[0] == pd.Timestamp('2026-10-21 01:00Z')


def test_fractional_minute_timestamp_is_not_treated_as_aligned():
    minute = bars('2026-10-20 00:00Z', 5)
    shifted = minute.index.to_list()
    shifted[2] += pd.Timedelta(milliseconds=500)
    minute.index = pd.DatetimeIndex(shifted)
    assert A.complete_bars(minute, 'M5', 'DVR25', pd.Timestamp('2026-10-20 00:05Z')).empty


@pytest.mark.parametrize('pair', ['EURUSD', 'DVR25'])
def test_quote_only_requirement_never_reads_or_downloads_history(monkeypatch, pair):
    now = pd.Timestamp('2026-10-20 12:07Z')
    monkeypatch.setattr(store, 'update', lambda *a, **k: pytest.fail('quote watch must not update H1'))
    monkeypatch.setattr(store, 'Pair', lambda *a, **k: pytest.fail('quote watch must not read H1 files'))
    class IC:
        def get_symbols(self, pairs): assert pairs == ['EURUSD']
        def get_spot(self, *a, **k): return (1.2, 1.3)
        def get_trendbars(self, *a, **k): pytest.fail('quote watch must not download candles')
        def close(self): pass
    class DV:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def prefetch(self, pairs=None): assert pairs is None
        def info(self, pair): return {'symbol': 'R_25'}
        def request(self, payload):
            assert payload['style'] == 'ticks' and payload['count'] == 1
            return {'history': {'prices': [123.], 'times': [int(now.timestamp())]}}
    monkeypatch.setattr(A, '_open_ctrader', IC)
    monkeypatch.setattr(deriv, 'Feed', DV)
    result = A.load([pair], now, requirements={pair: {'timeframes': [], 'quote': True}}, max_pairs=4)[pair]
    assert result['quote'] is not None and result['error'] is None
    assert result['frame'].empty and result['hourly'].empty


def test_m5_requirement_fetches_only_small_minute_window(monkeypatch):
    now = pd.Timestamp('2026-10-20 12:07Z')
    requests = []
    monkeypatch.setattr(store, 'update', lambda *a, **k: pytest.fail('intraday must not warm H1'))
    monkeypatch.setattr(store, 'Pair', lambda *a, **k: pytest.fail('intraday must not read H1'))
    class DV:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def prefetch(self, pairs=None): pass
        def info(self, pair): return {'symbol': 'R_25'}
        def request(self, payload):
            requests.append(payload)
            assert payload['style'] == 'candles' and payload['granularity'] == 60
            lo, hi = payload['start'], int(payload['end']) + 1
            return {'candles': [{'epoch': t, 'open': 1, 'high': 2, 'low': .5, 'close': 1.5} for t in range(lo, hi, 60)]}
    monkeypatch.setattr(deriv, 'Feed', DV)
    result = A.load(['DVR25'], now, requirements={'DVR25': {
        'primary_timeframes': ['M5'], 'timeframes': ['M5', 'M1'], 'quote': False}}, max_pairs=4)['DVR25']
    assert len(requests) == 1 and requests[0]['count'] == 55
    assert len(result['frame']) == 55 and result['hourly'].empty
    assert len(A.complete_bars(result['frame'], 'M5', 'DVR25', now)) >= 10


def test_hourly_current_cache_avoids_repeated_download(monkeypatch):
    now = pd.Timestamp('2026-10-20 12:07Z')
    class Cache:
        src = 'ctrader'
        def __init__(self, pair): pass
        def frame(self, lo=None): return bars(now.floor('h') - pd.Timedelta(days=31), 31*24, 3600)
    monkeypatch.setattr(store, 'Pair', Cache)
    monkeypatch.setattr(store, 'update', lambda *a, **k: pytest.fail('fresh cached H1 needs no download'))
    monkeypatch.setattr(A, '_open_ctrader', lambda: pytest.fail('fresh cached H1 needs no connection'))
    result = A.load(['EURUSD'], now, requirements={'EURUSD': {'primary_timeframes': ['D'], 'timeframes': ['D', 'H4'], 'quote': False}})['EURUSD']
    assert len(result['hourly']) == 31*24 and result['error'] is None
    assert result['frame'].empty and result['quote'] is None


def test_same_hour_does_not_repeat_completed_short_history_refresh(monkeypatch):
    now = pd.Timestamp('2026-10-20 12:07Z')
    _fake_cache(monkeypatch, now)
    monkeypatch.setattr(A, '_HOURLY_CHECKS', {})
    calls = []
    monkeypatch.setattr(store, 'update', lambda *a, **k: calls.append(k['days']))
    class IC:
        def get_symbols(self, pairs): pass
        def close(self): pass
    monkeypatch.setattr(A, '_open_ctrader', IC)
    requirements = {'EURUSD': {'timeframes': ['W'], 'quote': False}}
    A.load(['EURUSD'], now, requirements=requirements)
    A.load(['EURUSD'], now + pd.Timedelta(minutes=1), requirements=requirements)
    assert calls == [80]
    A.load(['EURUSD'], now + pd.Timedelta(hours=1), requirements=requirements)
    assert calls == [80, 80]


def test_long_confirmation_context_contains_ten_complete_h4_bars():
    need = A._requested('DVR25', {'DVR25': {'primary_timeframes': ['H4'], 'quote': False}})
    assert need['minutes'] == 44*60 and not need['hourly']
    now = pd.Timestamp('2026-10-20 12:07Z')
    source = bars(now.floor('min') - pd.Timedelta(minutes=need['minutes']), need['minutes'])
    result = A.complete_bars(source, 'H4', 'DVR25', now)
    assert len(result) == 10


def test_missing_latest_hour_retries_next_minute_instead_of_waiting_an_hour(monkeypatch):
    now = pd.Timestamp('2026-10-20 12:00Z')
    monkeypatch.setattr(A, '_HOURLY_CHECKS', {})
    class Cache:
        src = 'ctrader'
        def __init__(self, pair): pass
        def frame(self, lo=None): return bars(now - pd.Timedelta(hours=3), 2, 3600)
    calls = []
    monkeypatch.setattr(store, 'Pair', Cache)
    monkeypatch.setattr(store, 'update', lambda *a, **k: calls.append(1))
    class IC:
        def get_symbols(self, pairs): pass
        def close(self): pass
    monkeypatch.setattr(A, '_open_ctrader', IC)
    requirements = {'EURUSD': {'timeframes': ['D'], 'quote': False}}
    A.load(['EURUSD'], now, requirements=requirements)
    A.load(['EURUSD'], now + pd.Timedelta(minutes=1), requirements=requirements)
    assert calls == [1, 1]


def test_delisted_deriv_watch_does_not_suppress_another_valid_symbol(monkeypatch):
    now = pd.Timestamp('2026-10-20 12:07Z')
    opened, requested = [], []
    monkeypatch.setattr(store, 'Pair', lambda *a, **k: pytest.fail('quote-only must not read history'))
    monkeypatch.setattr(store, 'update', lambda *a, **k: pytest.fail('quote-only must not write history'))
    class DV:
        def __init__(self, **kwargs): opened.append(1)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def prefetch(self, pairs=None):
            assert pairs is None, 'Catalogue initialization must not validate a whole user watchlist'
        def info(self, pair):
            if pair == 'DVDELISTED': raise ValueError('Symbol no longer available')
            assert pair == 'DVR75'
            return {'symbol': 'R_75'}
        def request(self, payload):
            requested.append(payload['ticks_history'])
            return {'history': {'prices': [75.], 'times': [int(now.timestamp())]}}
    monkeypatch.setattr(deriv, 'Feed', DV)
    requirements = {pair: {'timeframes': [], 'quote': True} for pair in ('DVDELISTED', 'DVR75')}
    result = A.load(['DVDELISTED', 'DVR75'], now, requirements=requirements)
    assert opened == [1] and requested == ['R_75']
    assert 'no longer available' in result['DVDELISTED']['error']
    assert result['DVR75']['quote'] == 75. and result['DVR75']['error'] is None


@pytest.mark.parametrize('pair',['EURUSD','XAUUSD','XAGUSD'])
@pytest.mark.parametrize('date,close_wat',[('2026-10-29',6),('2026-11-02',7)])
def test_metals_and_fx_h4_follow_us_dst_not_fixed_wat(pair,date,close_wat):
    from slk import candles
    from slk.live import drop_forming
    close=pd.Timestamp(f'{date} {close_wat:02}:00',tz='Africa/Lagos').tz_convert('UTC')
    source=bars(close-pd.Timedelta(hours=4),4,3600)
    before=close-pd.Timedelta(seconds=1)
    assert A.complete_bars(source,'H4',pair,before).empty
    result=A.complete_bars(source,'H4',pair,close)
    assert len(result)==1 and result.end.iat[0]==close
    with candles.market(pair):
        assert drop_forming(source,'H4',before).empty
        assert len(drop_forming(source,'H4',close))==4

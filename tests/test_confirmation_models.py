"""Normalized candle geometry from Bishop Part5 sheets007–012.

Prices are deliberately synthetic: diagrams establish relationships, not exact
broker OHLC. Fixtures include examples that the previous implementation missed.
"""
import pandas as pd
import pytest
from slk import user_alerts as A


def bars(rows):
    start = pd.date_range('2026-10-20', periods=len(rows), freq='h', tz='UTC')
    return [dict(zip(('open','high','low','close'),r),start=t,end=t+pd.Timedelta(hours=1)) for t,r in zip(start,rows)]


def mirror(rows):
    return [(40-o,40-lo,40-hi,40-c) for o,hi,lo,c in rows]


def watch(condition,side='BUY'):
    return dict(pair='DVR75',condition=condition,side=side,timeframe='H1',level=10 if side=='BUY' else 30,
                created_at=int(pd.Timestamp('2026-10-19',tz='UTC').timestamp()),last_checked=0,
                expires_at=int(pd.Timestamp('2026-10-25',tz='UTC').timestamp()),engulfing=False)


@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('colour',['bearish','bullish','doji'])
def test_fourth_man_sweep_colour_unrestricted_source_diagram(side,colour):
    opening={'bearish':13,'bullish':10,'doji':11}[colour]
    rows=[(10,16,8,14),(opening,15,7,11)]
    if side=='SELL': rows=mirror(rows)
    b=bars(rows);detail=A.confirmation_detail(watch('fourth_man',side),b,1,side)
    assert detail['reference_level']==(8 if side=='BUY' else 32)
    assert detail['pattern_level']==(11 if side=='BUY' else 29)
    assert 'retest pending' in detail['stage']


@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('bad',[(13,17,7,11),(13,16,7,11),(13,15,8,11),
                                 (13,15,7,8),(13,17,7,16),(13,17,7,17),(13,15,7,7.5)])
def test_fourth_man_requires_sweep_standing_extreme_and_strict_range_close(side,bad):
    rows=[(10,16,8,14),bad]
    if side=='SELL': rows=mirror(rows)
    assert A.confirmation_detail(watch('fourth_man',side),bars(rows),1,side) is None


@pytest.mark.parametrize('side',['BUY','SELL'])
def test_engulfing_invalidates_oc_not_whole_body_or_run_open(side):
    rows=[(16,17,11,12),(12.01,13,8,9),(9,14,8,13)]
    if side=='SELL': rows=mirror(rows)
    b=bars(rows);d=A.confirmation_detail(watch('engulfing',side),b,2,side)
    assert d['reference_level']==(12 if side=='BUY' else 28)
    # BUY close13 is below first open16, still invalidates OC12.


@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('last',[(9,14,8,12),(9,14,8,11),(9,14,8,9)])
def test_engulfing_wick_or_equal_close_not_confirmation(side,last):
    rows=[(16,17,11,12),(12,13,8,9),last]
    if side=='SELL':rows=mirror(rows)
    assert A.confirmation_detail(watch('engulfing',side),bars(rows),2,side) is None


@pytest.mark.parametrize('side',['BUY','SELL'])
def test_engulfing_rejects_delayed_break_of_older_oc_and_reused_boundary(side):
    rows=[(16,17,11,12),(12,13,8,9),(9,11,8,10),(10,11,8,10),(10,14,9,13)]
    if side=='SELL':rows=mirror(rows)
    assert A.confirmation_detail(watch('engulfing',side),bars(rows),4,side) is None
    rows=[(16,17,11,12),(12,13,8,9),(9,14,8,13),(13,14,8,10),(10,14,9,13)]
    if side=='SELL':rows=mirror(rows)
    assert A.confirmation_detail(watch('engulfing',side),bars(rows),4,side) is None


@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('sweep',[False,True])
def test_one_breakout_model_covers_with_and_without_sweep(side,sweep):
    rows=[(11,12,10,11),(11,15,10,14),(14,15,10,12),(12,16,7 if sweep else 9,15)]
    if side=='SELL':rows=mirror(rows)
    d=A.confirmation_detail(watch('breakout',side),bars(rows),3,side)
    assert d['reference_level']==(14 if side=='BUY' else 26)


@pytest.mark.parametrize('side',['BUY','SELL'])
def test_user_level_crossing_or_pivot_wick_is_not_structural_breakout(side):
    rows=[(11,12,10,11),(11,15,10,14),(14,15,8,9),(9,16,8,11)]
    if side=='SELL':rows=mirror(rows)
    assert A.confirmation_detail(watch('breakout',side),bars(rows),3,side) is None


@pytest.mark.parametrize('condition,rows',[
    ('fourth_man',[(10,16,8,14),(13,15,7,11)]),
    ('engulfing',[(16,17,11,12),(12,13,8,9),(9,14,8,13)]),
    ('breakout',[(11,12,10,11),(11,15,10,14),(14,15,10,12),(12,16,9,15)])])
@pytest.mark.parametrize('side',['BUY','SELL'])
def test_complete_pipeline_candle_close_prefix_invariance_and_gaps(condition,rows,side):
    if side=='SELL':rows=mirror(rows)
    b=bars(rows); h=pd.DataFrame(rows,columns=['open','high','low','close'],index=[r['start'] for r in b]);w=watch(condition,side)
    end=b[-1]['end'];event=A.evaluate(w,h,end)
    assert event and event['time']==int(end.timestamp())
    assert A.evaluate(w,h,end-pd.Timedelta(seconds=1)) is None
    future=pd.DataFrame([(25,35,2,3)],columns=h.columns,index=[end])
    assert A.evaluate(w,pd.concat([h,future]),end)==event
    assert A.evaluate({**w,'level':1},h,end) is None
    assert A.evaluate({**w,'created_at':int(end.timestamp())},h,end) is None
    # A watch created mid-candle cannot establish whether that candle touched earlier.
    assert A.evaluate({**w,'created_at':int(end.timestamp())-1800},h,end) is None
    assert A.evaluate(w,h.drop(h.index[-2]),end) is None


def test_only_three_confirmation_choices_and_retired_names_rejected():
    assert A.CONFIRMATIONS=={'breakout','engulfing','fourth_man'}
    assert not (A.VALUES & A.RETIRED)
    for condition in A.RETIRED|{'sweep_and_break'}:
        with pytest.raises(ValueError):A.validate(dict(pair='DVR75',level=10,condition=condition))


def test_legacy_pending_rules_expire_explicitly_without_reinterpreting_them():
    class Repo(A.Repository):
        def __init__(self):self.calls=[]
        def execute(self,sql,args):self.calls.append((sql,args));return 0
        def query(self,*args):return []
    repo=Repo();repo.pending(1234)
    sql,args=repo.calls[0]
    assert "('pinbar_v1','cisd_v1')" in sql and "status='EXPIRED'" in sql
    assert 'recreate' in sql and 'lease_until<=%s' in sql and args==(1234,)


def test_optional_lower_engulfing_before_level_touch_does_not_validate_later_sweep():
    rows=[(12,17,11,16),(16,17,12,16),(16,18,10,14),(14,17,11,12),
          (12,17,11,15),(15,16,7,13)]
    h=pd.DataFrame(rows,columns=['open','high','low','close'],index=pd.date_range('2026-10-20',periods=6,freq='h',tz='UTC'))
    w={**watch('fourth_man'),'timeframe':'H2'}
    end=h.index[-1]+pd.Timedelta(hours=1)
    assert A.evaluate(w,h,end) is not None
    assert A.evaluate({**w,'engulfing':True},h,end) is None


def test_breakout_does_not_reuse_an_already_broken_swing():
    b=bars([(11,12,10,11),(11,15,10,14),(14,15,8,12),
            (12,16,8,15),(15,16,9,12),(12,16,9,15)])
    w=watch('breakout')
    assert A.confirmation_detail(w,b,3,'BUY')['reference_level']==14
    # The old14 swing is consumed; the new15 swing is only matched, not broken.
    assert A.confirmation_detail(w,b,5,'BUY') is None

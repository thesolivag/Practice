from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
from bishop.v2.detection_feed import shared_segments, prepare_detection_frames
from bishop.v2.types import Bar, Instrument

T=datetime(2026,6,12,tzinfo=timezone.utc)


def bar(tf,at,minutes,segment='0'):
    return Bar('USDCAD',tf,at,at+timedelta(minutes=minutes),10,12,9,11,segment_id=segment)


def test_physical_epoch_matches_across_different_native_segment_numbers():
    gaps=((T,T+timedelta(minutes=1)),)
    h1=bar('H1',T+timedelta(hours=1),60,'99')
    m30=bar('M30',T+timedelta(hours=1),30,'0')
    a,_=shared_segments((h1,),gaps,T-timedelta(days=1))
    b,_=shared_segments((m30,),gaps,T-timedelta(days=1))
    assert a[0].segment_id==b[0].segment_id
    assert a[0].id==h1.id and b[0].id==m30.id


def test_coincident_native_segment_numbers_cannot_bridge_a_fine_gap():
    gaps=((T+timedelta(minutes=40),T+timedelta(minutes=41)),)
    h1=bar('H1',T,60,'0')
    child=bar('M30',T+timedelta(hours=1),30,'0')
    a,crossing=shared_segments((h1,),gaps,T)
    b,_=shared_segments((child,),gaps,T)
    assert crossing==[h1.id]
    assert a[0].segment_id!=b[0].segment_id


def test_missing_minute_is_not_filled_and_incomplete_m30_is_absent():
    inst=Instrument('USDCAD','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    h1=(bar('H1',T,60),)
    minutes=tuple(bar('M1',T+timedelta(minutes=i),1) for i in range(60) if i!=10)
    fine=dict(instrument=inst,bars=minutes,manifest={'base_tf':'M1'},hashes={'sha256':'fine'},
              coverage={'missing':[(T+timedelta(minutes=10)).isoformat()],'missing_slots':1,'status':'INCOMPLETE'})
    detection=dict(instrument=inst,manifest={},coverage={'missing':[]})
    with patch('bishop.v2.detection_feed.prepare_execution_feed',return_value=(fine,{})):
        frames,coverage,audit=prepare_detection_frames({},detection,h1,{'H1':h1},T,T+timedelta(hours=1))
    assert len(frames['M30'])==1
    assert frames['M30'][0].start==T+timedelta(minutes=30)
    assert coverage['M30']['incomplete'][0]['missing_slots']==1
    assert audit['coverage']['missing_slots']==1 and audit['no_imputation']
    assert frames['H1'][0].segment_id!=frames['M30'][0].segment_id


def test_mixed_detection_refuses_non_h1_context():
    with pytest.raises(ValueError,match='H1 context'):
        prepare_detection_frames({}, {}, (bar('M30',T,30),), {}, T, T+timedelta(hours=1))


def test_engine_reanalyzes_remapped_h1_and_real_child_before_detection(monkeypatch):
    import bishop.v2.engine as engine
    from bishop.v2.types import StrategyPolicy
    from bishop.v2.simulation import Costs
    inst=Instrument('USDCAD','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    coarse=(bar('H1',T,60),)
    fine=dict(instrument=inst,bars=tuple(bar('M1',T+timedelta(minutes=i),1) for i in range(60) if i!=10),
              manifest={'base_tf':'M1'},hashes={'sha256':'fine'},
              coverage={'missing':[(T+timedelta(minutes=10)).isoformat()],'missing_slots':1,'status':'INCOMPLETE'})
    captured={}
    original=engine.analyze
    def analyze(bs,*args,**kwargs):
        if bs:captured[bs[0].tf]=bs
        return original(bs,*args,**kwargs)
    monkeypatch.setattr(engine,'analyze',analyze)
    with patch('bishop.v2.detection_feed.prepare_execution_feed',return_value=(fine,{})):
        result=engine.run({'instrument':inst,'bars':coarse,'manifest':{}},as_of=T+timedelta(hours=1),
                          scan_start=T,policy=StrategyPolicy(source_profile='nested_confirmation',entry_tfs=('M30',),origin_tfs=('H4',)),
                          costs=Costs(),detection_feed={'path':'real-m1','manifest':'declared'})
    assert len(captured['M30'])==1
    assert captured['H1'][0].id==coarse[0].id
    assert captured['H1'][0].segment_id!=captured['M30'][0].segment_id
    assert result['input']['detection_child']['sha256']=='fine'
    assert result['detection_input']['coverage']['missing_slots']==1
    assert result['status']=='PARTIAL_UNVALIDATED'
    assert not result['orders']

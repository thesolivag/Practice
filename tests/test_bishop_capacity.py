from datetime import datetime,timedelta,timezone
from copy import deepcopy
from dataclasses import replace
from bishop.v2.types import Bar,Clock,Order
from slk.bishop_capacity import occupies
T=datetime(2026,1,5,tzinfo=timezone.utc)

def row(side='BUY'):
    o=Order(id='o',setup_id='s',instrument='X',tf='H1',model='confirmation_bo',side=side,kind='LIMIT',clock=Clock(T,T,T),entry_ticks=100,stop_ticks=90 if side=='BUY' else 110,target_ticks=110 if side=='BUY' else 90,expires_at=T+timedelta(hours=2))
    return {'order':o,'actions':[],'observation':{'outcome':'CENSORED','net_r':None}}

def bar(h,low=95,high=105):
    return Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),100,high,low,100,T+timedelta(hours=h+1),'test')

def test_expiry_alone_is_not_flat_proof():
    r=row();assert occupies(r,(bar(0,80,120),bar(2)),T+timedelta(hours=3))

def test_after_expiry_exit_frees_slot_without_changing_outcome():
    for side in ('BUY','SELL'):
        r=row(side);obs=dict(r['observation'])
        assert not occupies(r,(bar(2,80,120),),T+timedelta(hours=3))
        assert r['observation']==obs
        assert r['capacity_released_at']==(T+timedelta(hours=3)).isoformat()

def test_future_proof_cannot_free_capacity_early():
    r=row();future=bar(2,80,120)
    assert occupies(r,(future,),T+timedelta(hours=2))
    assert 'capacity_released_at' not in r
    assert not occupies(r,(future,),T+timedelta(hours=3))
    assert occupies(r,(future,),T+timedelta(hours=2))

def test_forming_or_amended_orders_are_not_proven():
    r=row();assert occupies(r,(replace(bar(2,80,120),complete=False),),T+timedelta(hours=3))
    r['actions']=[{'kind':'AMEND','available_at':T.isoformat()}]
    assert occupies(r,(bar(2,80,120),),T+timedelta(hours=3))

def test_cancellation_can_bound_pending_but_not_position():
    r=row();r['actions']=[{'kind':'CANCEL','available_at':(T+timedelta(hours=1)).isoformat()}]
    assert occupies(r,(bar(1),),T+timedelta(hours=2))
    assert not occupies(r,(bar(1,80,120),),T+timedelta(hours=2))


def test_saved_minute_feed_roundtrip_and_hash_guard(tmp_path):
    import pytest
    from slk import bishop_capacity_jobs as J,bishop_capacity_replay as C
    from slk.bishop_unknown_jobs import digest
    from bishop.v2.types import Instrument
    inst=Instrument('X','1','1','24x7_utc_v1')
    hour=bar(0);minute=replace(hour,tf='M1',end=T+timedelta(minutes=1),available_at=T+timedelta(minutes=1))
    path=tmp_path/'X.json.gz';fine=tmp_path/'minutes/X.json.gz'
    C.dump(path,{'instrument':inst,'bars':[hour],'manifest':{}})
    C.dump(fine,{T.isoformat():[minute]})
    C.dump(tmp_path/'manifest.json',{'markets':{'X':{'sha256':digest(path),'minute_file_sha256':digest(fine)}}})
    loaded=J.load_feed(path)
    assert loaded['minute_evidence'][T]==(minute,)
    C.dump(fine,{})
    with pytest.raises(ValueError,match='M1 hash'):J.load_feed(path)

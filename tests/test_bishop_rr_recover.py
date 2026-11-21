from copy import deepcopy
from test_bishop_unknown_jobs import fixture
from bishop.v2.types import jsonable
from slk.bishop_paper import history_hash,thaw_order
from slk.bishop_rr_recover import recover

def case(path):
    row,feed,end,minute=fixture(path)
    study=dict(id='study',pair='TEST',version='test',status='COMPLETE',source_order=row['order'],stop_proof={'status':'READY','stop_ticks':90},
        instrument=jsonable(feed['instrument']),calendar=feed['instrument'].calendar_id,costs={},history_to=end.isoformat(),
        history_hash=history_hash(feed['bars'],thaw_order(row['order']),end),source_actions=[],
        variants={'1':{'order':row['order'],'observation':row['observation']}})
    return study,feed['bars'],minute


def test_resolves_with_immutable_order_and_retains_original_observation():
    s,b,m=case([(102,111,101,110)]);before=deepcopy(s)
    new,a=recover(s,b,lambda _:m)
    assert a[0]['reason']=='RESOLVED' and new['variants']['1']['observation']['outcome']=='WIN'
    assert new['variants']['1']['order']==s['variants']['1']['order']
    assert new['variants']['1']['m1_recovery']['original_observation']==s['variants']['1']['observation']
    assert s==before


def test_missing_original_hash_prevents_recovery():
    s,b,m=case([(102,111,101,110)]);s['history_hash']='wrong'
    new,a=recover(s,b,lambda _:m)
    assert new==s and a[0]['reason']=='ORIGINAL_H1_HISTORY_HASH_MISMATCH'


def test_same_minute_collision_stays_unchanged():
    s,b,m=case([(102,111,89,105)])
    new,a=recover(s,b,lambda _:m)
    assert new==s and a[0]['reason']=='UNRESOLVED_INTRABAR_SEQUENCE'

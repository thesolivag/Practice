"""Indexed reaction selection retains visibility, maxima and stable ties."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from bishop.v2.entries import _latest_reaction
T=datetime(2026,1,5,tzinfo=timezone.utc)
def bar(h,receipt=None):
    return SimpleNamespace(id=f'b{h}',start=T+timedelta(hours=h),end=T+timedelta(hours=h+1),
                           available_at=T+timedelta(hours=h+1 if receipt is None else receipt))
def test_index_matches_full_scan_for_delayed_same_candle_and_future_reactions():
    bs=(bar(0),bar(2,7),bar(3),bar(4),bar(5))
    rows=[(b,SimpleNamespace(id='level'),f'parent{b.id}') for b in bs]
    rows.extend(((bs[3],SimpleNamespace(id='z'),'first'),(bs[3],SimpleNamespace(id='z'),'second')))
    rows=tuple(sorted(rows,key=lambda r:(r[0].end,r[0].available_at,r[1].id)))
    ends=tuple(r[0].end for r in rows)
    for candle in (*bs,bar(1),bar(6),bar(8)):
        visible=[r for r in rows if (r[0].id==candle.id or r[0].end<=candle.start) and r[0].available_at<=candle.available_at]
        expected=max(visible,key=lambda r:(r[0].end,r[0].available_at,r[1].id),default=None)
        assert _latest_reaction(rows,ends,candle)==expected
    assert _latest_reaction(rows,ends,bs[3])[2]=='first'
    assert _latest_reaction((),(),bar(0)) is None

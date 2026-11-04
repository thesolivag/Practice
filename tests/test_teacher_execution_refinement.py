from types import SimpleNamespace
from bishop.v2.types import utc
from reports.refine_teacher_execution import compare_coarse


def bar(stamp, high=110):
    return SimpleNamespace(start=utc(stamp), open_ticks=100, high_ticks=high, low_ticks=90, close_ticks=105)


def test_finer_feed_must_reconstruct_every_coarse_bar_and_prices():
    a = bar('2026-01-01T01:00:00Z')
    b = bar('2026-01-01T02:00:00Z')
    assert compare_coarse([a, b], [a, b])['status'] == 'CONSISTENT'
    missing = compare_coarse([a, b], [a])
    assert missing['status'] == 'UNRESOLVED'
    assert missing['missing_fine_aggregates'] == [b.start.isoformat()]
    mismatch = compare_coarse([a], [bar('2026-01-01T01:00:00Z', high=111)])
    assert mismatch['status'] == 'UNRESOLVED'
    assert len(mismatch['mismatches']) == 1
    assert compare_coarse([], [])['status'] == 'UNRESOLVED'

from copy import deepcopy
from test_bishop_unknown_jobs import fixture
from slk.bishop_oc_unknown_jobs import refine
from bishop.v2.types import jsonable
from bishop.v2.research_stop_simulation import simulate,Costs
from slk.bishop_paper import thaw_order


def test_existing_minute_ambiguity_is_preserved_without_refetching_hour():
    row,feed,end,minute=fixture([(102,111,89,105)])
    row['observation']=jsonable(simulate((thaw_order(row['order']),),minute,feed['instrument'],Costs(),end)['observations'][0])
    feed['minute_evidence']={feed['bars'][0].start:minute}
    before=deepcopy(row)
    def fail(_):raise AssertionError('Already have M1')
    result=refine(row,feed,end,fail)
    assert result['reason']=='STILL_AMBIGUOUS_WITHIN_ONE_MINUTE'
    assert row==before


def test_fresh_hour_refinement_still_resolves_and_preserves_geometry():
    row,feed,end,minute=fixture([(102,111,101,110)])
    before=deepcopy(row)
    result=refine(row,feed,end,lambda _:minute)
    assert result['status']=='RESOLVED'
    assert result['observation']['outcome']=='WIN'
    assert result['order']==before['order'] and row==before

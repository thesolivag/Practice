"""Independent publication-clock and scope-boundary checks for weekly context."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from bishop.v2.weekly_context import POLICY, resolve

T = datetime(2026, 5, 8, 21, tzinfo=timezone.utc)


def story(ident, side='BUY', hour=0, instrument='X', scope='ROOT', tf='W'):
    return SimpleNamespace(id=ident, side=side, available_at=T+timedelta(hours=hour),
                           instrument=instrument, origin_tf=tf, details={'scope_type':scope})


def event(kind, ident, hour=1, details=None):
    return SimpleNamespace(kind=kind, reference_id=ident, available_at=T+timedelta(hours=hour),
                           details=details or {})


def test_exact_same_clock_weekly_confirmation_is_available_and_all_ids_preserved():
    stories = (story('old','SELL',-24),story('z'),story('a'))
    original = deepcopy(stories)
    result = resolve(stories,(),T,'X')
    assert result == dict(status='KNOWN',side='BUY',story_ids=('a','z'),
                          available_at=T.isoformat(),policy=POLICY)
    assert stories == original
    assert resolve(tuple(reversed(stories)),(),T,'X') == result


def test_future_story_and_retirement_cannot_change_earlier_context():
    current = (story('current'),)
    baseline = resolve(current,(),T,'X')
    assert resolve((*current,story('future','SELL',1)),
                   (event('STORY_INVALIDATED','current',1),),T,'X') == baseline
    assert resolve((*current,story('future','SELL',1)),(),T+timedelta(hours=1),'X')['side']=='SELL'


def test_same_clock_opposing_stories_are_conflicted_without_id_winner():
    a = resolve((story('a'),story('z','SELL')),(),T,'X')
    b = resolve((story('z','SELL'),story('a')),(),T,'X')
    assert a == b
    assert a['status']=='CONFLICTED' and a['side'] is None
    assert a['story_ids']==('a','z')


def test_only_matching_instrument_weekly_root_is_eligible():
    candidates = (story('wrong_instrument',instrument='Y'),story('child',scope='CHILD'),
                  story('daily',tf='D'))
    result = resolve(candidates,(),T,'X')
    assert result['status']=='UNKNOWN' and result['story_ids']==()
    assert resolve((*candidates,story('root')),(),T,'X')['story_ids']==('root',)


@pytest.mark.parametrize('kind',['STORY_INVALIDATED','STORY_SUSPENDED','STORY_RETIRED'])
@pytest.mark.parametrize('details_reference',[False,True])
def test_retired_latest_batch_does_not_revive_older_opposite(kind,details_reference):
    retirement = event(kind,None if details_reference else 'new',
                       details={'story_id':'new'} if details_reference else {})
    result = resolve((story('old','SELL',-24),story('new')),
                     (retirement,),T+timedelta(hours=1),'X')
    assert result['status']=='UNKNOWN' and result['side'] is None
    assert result['story_ids']==('new',) and result['available_at']==T.isoformat()


def test_destination_touch_is_not_directional_flip_or_retirement():
    result = resolve((story('current'),),
                     (event('STORY_DESTINATION_REACHED','current'),),T+timedelta(hours=1),'X')
    assert result['status']=='KNOWN' and result['side']=='BUY'


def test_unrelated_retirement_does_not_erase_context():
    result = resolve((story('current'),),(event('STORY_RETIRED','other'),),T+timedelta(hours=1),'X')
    assert result['status']=='KNOWN' and result['side']=='BUY'

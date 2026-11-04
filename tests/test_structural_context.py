from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from bishop.structural_context import summarize
from bishop.v2.types import Clock, Event
from bishop.bias_snapshot import snapshot

T = datetime(2026, 6, 24, tzinfo=timezone.utc)


def event(identifier, side, at=T):
    return Event(id=identifier, kind='BREAKOUT', instrument='GBPUSD', tf='D',
                 side=side, clock=Clock(at, at, at))


def structure(events, ranges=()):
    return SimpleNamespace(events=events, ranges=ranges)


def test_direction_uses_closed_available_breaks_and_keeps_tied_opposites_unresolved():
    events = [event('sell', 'SELL'), event('future', 'BUY', T + timedelta(days=1))]
    assert summarize({'D': structure(events)}, T)['D']['side'] == 'SELL'
    events.append(event('buy-same-close', 'BUY'))
    row = summarize({'D': structure(events)}, T)['D']
    assert row['state'] == 'CONFLICT' and row['side'] is None


def test_provisional_parent_scope_is_not_presented_as_defined():
    root = SimpleNamespace(id='root', parent_id=None, status='PROVISIONAL_BREAKOUT', direction='SELL',
                           protected_turn_id='origin', origin_ticks=132000, available_at=T)
    row = summarize({'D': structure([event('sell', 'SELL')], [root])}, T)['D']
    assert row['active_root_ranges'][0]['status'] == 'PROVISIONAL_BREAKOUT'


def test_daily_breakout_context_is_not_daily_reaction_to_h4_setup_direction():
    context = summarize({'D': structure([event('sell', 'SELL')])}, T)
    reaction_story = dict(id='daily-reaction', instrument='GBPUSD', side='BUY', origin_tf='D',
                          confirmation_tf='H4', clock={'available_at': T.isoformat()},
                          state='CONFIRMED', route='kl_structural', details={})
    result = dict(as_of=T.isoformat(), instrument={'symbol': 'GBPUSD'}, status='COMPUTED_UNVALIDATED',
                  policy={'origin_tfs': ['D']}, stories=[reaction_story], structural_context=context)
    row = snapshot(result)['rows'][0]
    assert row['side'] == 'SELL' and row['basis'] == 'SAME_TIMEFRAME_STRUCTURE'
    assert row['setup_story_side'] == 'BUY'
    result['status'] = 'PARTIAL_UNVALIDATED'
    assert snapshot(result)['rows'][0]['side'] is None


def segment_case(old_reference=False, trailing_gap=False):
    from bishop.v2.types import Bar, Turn
    from bishop.structural_context import current_segment_readiness
    base = [Bar('GBPUSD','H1',T-timedelta(hours=8),T-timedelta(hours=7),10,12,9,11,segment_id='old')]
    base += [Bar('GBPUSD','H1',T+timedelta(hours=i),T+timedelta(hours=i+1),10,12,9,11,segment_id='new') for i in range(12)]
    reference = Bar('GBPUSD','H4',T,T+timedelta(hours=4),10,12,9,11)
    if old_reference:
        reference = Bar('GBPUSD','H4',T-timedelta(hours=12),T-timedelta(hours=8),10,12,9,11)
    confirmation = Bar('GBPUSD','H4',T+timedelta(hours=4),T+timedelta(hours=8),10,12,9,11)
    breaking = Bar('GBPUSD','H4',T+timedelta(hours=8),T+timedelta(hours=12),10,13,9,12)
    turn = Turn(id='turn',instrument='GBPUSD',tf='H4',kind='H',price_ticks=12,
                formed_at=reference.end,available_at=confirmation.end,
                anchor_bar_id=reference.id,confirmation_bar_id=confirmation.id)
    e = Event(id='closed-break',kind='BREAKOUT',instrument='GBPUSD',tf='H4',side='BUY',
              reference_id=turn.id,bar_ids=(breaking.id,),clock=breaking.clock)
    analysis = SimpleNamespace(events=(e,),ranges=(),turns=(turn,))
    contexts = summarize({'H4':analysis},breaking.end)
    missing = [(T-timedelta(hours=4)).isoformat()]
    if trailing_gap:
        missing.append(breaking.end.isoformat())
    clock=breaking.end+timedelta(hours=1) if trailing_gap else breaking.end
    current_segment_readiness(contexts,{'H4':analysis},{'H4':(reference,confirmation,breaking)},base,
                              {'missing':missing,'missing_slots':len(missing)},clock)
    return contexts, clock


def test_known_current_structure_can_be_shown_without_erasing_historical_gaps():
    contexts,clock=segment_case()
    proof=contexts['H4']['current_segment']
    assert proof['ready'] and proof['historical_missing_slots']==1
    result=dict(scope='BIAS_ONLY',as_of=clock.isoformat(),instrument={'symbol':'GBPUSD'},
                status='PARTIAL_UNVALIDATED',policy={'origin_tfs':['H4']},structural_context=contexts)
    row=snapshot(result)['rows'][0]
    assert row['side']=='BUY' and row['historical_data_incomplete']
    assert row['coverage_scope']=='CURRENT_SEGMENT_ONLY'
    result['scope']='PAPER_ENTRIES'
    assert snapshot(result)['rows'][0]['side'] is None


def test_old_reference_or_trailing_hole_never_gets_current_segment_readiness():
    contexts,_=segment_case(old_reference=True)
    assert not contexts['H4']['current_segment']['ready']
    assert 'REFERENCE_NOT_PROVEN_IN_CURRENT_SEGMENT' in contexts['H4']['current_segment']['reasons']
    contexts,_=segment_case(trailing_gap=True)
    assert not contexts['H4']['current_segment']['ready']

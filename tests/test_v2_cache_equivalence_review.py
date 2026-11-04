"""Independent cached-versus-reference equivalence, not source-rule acceptance."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import random
import pytest
import bishop.v2.aggregation as aggregation
import bishop.v2.stories as stories
from bishop.v2.types import Bar,Clock,Event,Level,StrategyPolicy,Instrument
from bishop.v2.structure import StructureResult,analyze

T=datetime(2026,1,1,tzinfo=timezone.utc)


@pytest.mark.parametrize('day',[datetime(2026,3,8,tzinfo=timezone.utc),datetime(2026,11,1,tzinfo=timezone.utc)])
@pytest.mark.parametrize('tf',['M45','H3'])
def test_bound_cache_matches_original_through_offset_change_and_rewinds(day,tf):
    stamps=[day+timedelta(minutes=5*i) for i in range(144)]
    # Production traverses expected slots then revisits observed rows.
    probes=stamps+list(reversed(stamps))+stamps[::7]
    for anchor in ('ny17_wall_v2','utc_epoch_v1'):
        lookup=aggregation._BoundLookup(tf,anchor)
        assert [lookup(at) for at in probes]==[aggregation.bounds(at,tf,anchor) for at in probes]


def test_aggregate_output_equals_uncached_bounds_on_fall_m45_missing_data(monkeypatch):
    start=datetime(2026,11,1,tzinfo=timezone.utc)
    bars=tuple(Bar('X','M5',start+timedelta(minutes=5*i),start+timedelta(minutes=5*(i+1)),100,101+i%3,99,100)
               for i in range(288) if i not in range(100,115))
    kwargs=dict(calendar='24x7_utc_v1',anchor='ny17_wall_v2',as_of=start+timedelta(days=1))
    cached=aggregation.aggregate(bars,'M45',**kwargs)
    monkeypatch.setattr(aggregation,'_BoundLookup',lambda tf,anchor:lambda at:aggregation.bounds(at,tf,anchor))
    plain=aggregation.aggregate(bars,'M45',**kwargs)
    assert cached==plain and cached['coverage']['status']=='PARTIAL'


def test_role_qualification_cache_preserves_same_clock_ties_unknown_and_unavailability():
    level=Level(id='l',instrument='X',tf='D',kind='V',price_ticks=100,side='BUY',formed_at=T,available_at=T)
    def ev(ident,kind,hour,ref,side=None,status='KNOWN',**details):
        at=T+timedelta(hours=hour)
        return Event(id=ident,kind=kind,instrument='X',tf='D',clock=Clock(at,at,at),
                     reference_id=ref,side=side,evidence_status=status,details=details)
    events=(ev('change_a','LEVEL_ROLE_CHANGE',1,'l','SELL',qualification='RAW_BREAK'),
            ev('change_z','LEVEL_ROLE_CHANGE',1,'l','BUY',qualification='RAW_BREAK'),
            ev('assessment_a','IMPULSE_ASSESSMENT',2,'change_z',qualification='IMPULSE_CONFIRMED'),
            ev('assessment_z','IMPULSE_ASSESSMENT',2,'change_z',qualification='NOT_CONFIRMED'),
            ev('unknown','IMPULSE_ASSESSMENT',3,'change_z',status='UNKNOWN',qualification='UNKNOWN'),
            ev('retire','LEVEL_UNAVAILABLE',4,'l'))
    plain=StructureResult((),(level,),(),events,())
    cached=stories._StoryStructureView(plain)
    for hour in (0,1,1.5,2,3,4,5,2,1):
        at=T+timedelta(hours=hour)
        assert stories._role_qualification(level,cached,at)==stories._role_qualification(level,plain,at)
        for profile in ('bishop_confirmation','core_course','plug_and_play'):
            assert stories._role(level,cached,at,profile)==stories._role(level,plain,at,profile)
    assert stories._role(level,cached,T+timedelta(hours=3),'core_course') is None
    assert stories._role(level,cached,T+timedelta(hours=4)) is None


def test_range_version_cache_preserves_first_same_clock_and_excludes_future():
    def r(ident,hour,version):return SimpleNamespace(id=ident,available_at=T+timedelta(hours=hour),version_id=version)
    first=r('r',1,'first');same=r('r',1,'same_clock_later');latest=r('r',2,'latest');future=r('r',4,'future')
    other=r('other',1,'other')
    result=StructureResult((),(),(),(),(first,same,latest,future,other))
    view=stories._StoryStructureView(result)
    for hour in (0,1,2,3,1):
        at=T+timedelta(hours=hour);reference={}
        for candidate in result.ranges:
            if candidate.available_at<=at and (candidate.id not in reference or candidate.available_at>reference[candidate.id].available_at):
                reference[candidate.id]=candidate
        actual,ordered=view._versions_at(at)
        assert actual==reference
        assert ordered==tuple(sorted(reference.values(),key=lambda r:(r.available_at,r.id)))
    assert view._versions_at(T+timedelta(hours=1))[0]['r'] is first


def test_full_nonempty_story_output_matches_plain_structure_path(monkeypatch):
    rand=random.Random(41);price=1000;bars=[]
    for i in range(96):
        close=price+rand.choice((-12,-8,-4,4,8,12))
        bars.append(Bar('X','H1',T+timedelta(hours=i),T+timedelta(hours=i+1),price,max(price,close)+3,min(price,close)-3,close));price=close
    instrument=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    policy=StrategyPolicy(origin_tfs=('H4',),entry_tfs=('H1',))
    frames={tf:aggregation.aggregate(bars,tf,instrument,bars[-1].end)['bars'] for tf in ('H1','H4','D','W')}
    structures={tf:analyze(bs,policy) for tf,bs in frames.items()}
    cached=stories.find_stories(frames,structures,policy)
    monkeypatch.setattr(stories,'_indexed_structures',lambda structures,bars_by_tf=None:structures)
    plain=stories.find_stories(frames,structures,policy)
    assert cached.stories and cached.reactions
    assert cached==plain


@pytest.mark.parametrize('other_hour,expected',[(3,True),(2.5,False),(5,True)])
def test_confirm_cache_preserves_strict_earlier_break_predicate_all_statuses(other_hour,expected):
    origin=Bar('X','D',T,T+timedelta(hours=4),100,110,95,108)
    lower=(Bar('X','H1',T,T+timedelta(hours=1),100,102,99,101),
           Bar('X','H1',T+timedelta(hours=1),T+timedelta(hours=2),101,104,100,103),
           Bar('X','H1',T+timedelta(hours=2),T+timedelta(hours=3),103,107,102,106))
    reaction=Event(id='reaction',kind='PRIOR_CANDLE_SWEEP',instrument='X',tf='D',
                   clock=Clock(origin.end,origin.end,origin.end),side='BUY',price_ticks=100)
    reference=SimpleNamespace(id='high',available_at=T-timedelta(hours=1),formed_at=T-timedelta(hours=2))
    completion=T+timedelta(hours=3)
    candidate=Event(id='candidate',kind='BREAKOUT',instrument='X',tf='H1',
                    clock=Clock(completion,completion,completion),side='BUY',reference_id=reference.id)
    other_at=T+timedelta(hours=other_hour)
    other=Event(id='other',kind='BOS',instrument='X',tf='H1',
                clock=Clock(other_at,other_at,other_at),side='SELL',reference_id=reference.id,evidence_status='UNKNOWN')
    plain=StructureResult((reference,),(),(),(other,candidate),())
    cached=stories._StoryStructureView(plain,lower)
    args=(reaction,origin,'H1',lower)
    old=stories._confirm(*args,plain,(origin,),{})
    new=stories._confirm(*args,cached,(origin,),{})
    assert new==old and (new is not None) is expected
    late=SimpleNamespace(id='high',available_at=T+timedelta(hours=4),formed_at=T+timedelta(hours=2))
    late_plain=StructureResult((late,),(),(),(candidate,),())
    late_cached=stories._StoryStructureView(late_plain,lower)
    assert stories._confirm(*args,late_plain,(origin,),{}) is None
    assert stories._confirm(*args,late_cached,(origin,),{}) is None


def test_confirmation_minimum_search_uses_semantic_occurrence_not_policy_id(monkeypatch):
    origin=Bar('X','D',T,T+timedelta(hours=4),100,110,95,108)
    lower=tuple(Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),100,110,99,105) for h in range(5))
    reaction=Event(id='reaction',kind='PRIOR_CANDLE_SWEEP',instrument='X',tf='D',
                   clock=Clock(origin.end,origin.end,origin.end),side='BUY',price_ticks=100)
    refs=tuple(SimpleNamespace(id=ident,available_at=T-timedelta(hours=1),formed_at=T-timedelta(hours=2))
               for ident in ('r_z','r_a','r_future'))
    def completion(ident,ref,hour):
        at=T+timedelta(hours=hour)
        return Event(id=ident,kind='BREAKOUT',instrument='X',tf='H1',clock=Clock(at,at,at),side='BUY',reference_id=ref)
    # z and a both publish at reaction04:00. The earlier actual break z wins;
    # policy-sensitive lexical IDs and future evidence cannot change that.
    events=(completion('0_future','r_future',5),completion('a','r_a',3),completion('z','r_z',2))
    plain=StructureResult(refs,(),(),events,())
    args=(reaction,origin,'H1',lower)
    expected=stories._confirm(*args,plain,(origin,),{})
    assert expected[2].id=='z' and expected[0]==origin.end
    calls=[];original=stories._related_reference_uncached
    def traced(event,*a):
        calls.append(event.id)
        return original(event,*a)
    monkeypatch.setattr(stories,'_related_reference_uncached',traced)
    actual=stories._confirm(*args,stories._StoryStructureView(plain,lower),(origin,),{})
    assert actual==expected and calls==['z','a']


@pytest.mark.parametrize('confirmation_hour,invalidation_receipt,valid',[(5,8,True),(8,8,False),(9,8,False),(9,10,True)])
def test_confirmation_bar_invalidation_bound_uses_publication_clock(confirmation_hour,invalidation_receipt,valid):
    origin=Bar('X','D',T,T+timedelta(hours=4),100,110,95,108)
    invalid=Bar('X','D',origin.end,T+timedelta(hours=8),108,110,94,94,
                available_at=T+timedelta(hours=invalidation_receipt))
    lower=tuple(Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),100,110,99,105) for h in range(10))
    reaction=Event(id='reaction',kind='PRIOR_CANDLE_SWEEP',instrument='X',tf='D',
                   clock=Clock(origin.end,origin.end,origin.end),side='BUY',price_ticks=100)
    ref=SimpleNamespace(id='ref',available_at=T-timedelta(hours=1),formed_at=T-timedelta(hours=2))
    at=T+timedelta(hours=confirmation_hour)
    completion=Event(id='completion',kind='BREAKOUT',instrument='X',tf='H1',clock=Clock(at,at,at),side='BUY',reference_id=ref.id)
    plain=StructureResult((ref,),(),(),(completion,),())
    args=(reaction,origin,'H1',lower)
    expected=stories._confirm(*args,plain,(origin,invalid),{})
    actual=stories._confirm(*args,stories._StoryStructureView(plain,lower),(origin,invalid),{})
    assert actual==expected and (actual is not None)==valid


def test_role_only_loss_is_not_a_permanent_confirmation_time_bound():
    origin=Bar('X','D',T,T+timedelta(hours=4),100,110,95,108)
    later=Bar('X','D',origin.end,T+timedelta(hours=8),108,110,101,105)
    lower=tuple(Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),100,110,99,105) for h in range(8))
    level=Level(id='kl',instrument='X',tf='D',kind='V',side='BUY',price_ticks=100,formed_at=T,available_at=T)
    reaction=Event(id='reaction',kind='KL_REJECTION',instrument='X',tf='D',
        clock=Clock(origin.end,origin.end,origin.end),side='BUY',reference_id=level.id,price_ticks=100,
        details={'level_tf':'D','source_profile':'bishop_confirmation'})
    refs=tuple(SimpleNamespace(id=ident,available_at=T-timedelta(hours=1),formed_at=T-timedelta(hours=2)) for ident in ('ref5','ref7'))
    completions=[];flips=[]
    for h,side in ((5,'SELL'),(7,'BUY')):
        at=T+timedelta(hours=h)
        flips.append(Event(id=f'flip{h}',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='D',clock=Clock(at,at,at),side=side,reference_id=level.id))
        completions.append(Event(id=f'ce{h}',kind='BREAKOUT',instrument='X',tf='H1',clock=Clock(at,at,at),side='BUY',reference_id=f'ref{h}'))
    plain=StructureResult(refs,(),(),tuple(completions),())
    structures={'D':StructureResult((),(level,),(),tuple(flips),())}
    args=(reaction,origin,'H1',lower)
    expected=stories._confirm(*args,plain,(origin,later),structures)
    actual=stories._confirm(*args,stories._StoryStructureView(plain,lower),(origin,later),structures)
    assert actual==expected and actual[2].id=='ce7'


def test_event_range_index_matches_frozen_full_snapshot_links_and_parent_versions():
    def version(ident,hour,tag,parent=None,seed=None):
        return SimpleNamespace(id=ident,available_at=T+timedelta(hours=hour),version_id=tag,
                               parent_id=parent,details={'seed_break_event_id':seed} if seed else {})
    rows=(version('parent',0,'p0'),version('scope',1,'first','parent'),
          version('scope',1,'same_clock_later','parent'),version('seeded',2,'seed','parent','break'),
          version('unrelated',1,'unused'),version('future_seed',0,'unlinked'),version('future_seed',5,'future_link',seed='break'),version('parent',3,'p3'),version('scope',4,'future','parent'))
    view=stories._StoryStructureView(StructureResult((),(),(),(),rows))
    for hour in (1,2,3,4):
        at=T+timedelta(hours=hour)
        event=Event(id='break',kind='BREAKOUT',instrument='X',tf='H1',clock=Clock(at,at,at),side='BUY',scope_id='scope')
        all_versions,ordered=view._versions_at(at)
        expected=tuple(v for v in ordered if v.id==event.scope_id or v.details.get('seed_break_event_id')==event.id)
        actual,linked=view._event_versions_at(event)
        assert linked==expected
        assert all(actual[v.id] is v for v in expected)
        for v in expected:
            if v.parent_id in all_versions:assert actual[v.parent_id] is all_versions[v.parent_id]
        assert 'unrelated' not in actual
    assert view._range_at('scope',T+timedelta(hours=1)).version_id=='first'
    earlier=view._event_versions_at(Event(id='break',kind='BREAKOUT',instrument='X',tf='H1',clock=Clock(T,T,T),side='BUY',scope_id='scope'))
    assert earlier==({},())


@pytest.mark.parametrize('case,valid',[('none',True),('parent_broken',False),('opposite_unknown',False),('future_opposite',True),('other_scope',True)])
def test_scoped_lineage_event_indexes_preserve_unknown_and_future_evidence(case,valid):
    lower=tuple(Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),100,105,95,100) for h in range(5))
    touch=lower[0]
    reference=SimpleNamespace(id='reference',formed_at=T+timedelta(hours=2),available_at=T+timedelta(hours=3))
    protected=SimpleNamespace(id='protected',anchor_bar_id=touch.id,formed_at=T,available_at=T+timedelta(hours=2))
    def lineage(ident,parent,available):
        return SimpleNamespace(id=ident,parent_id=parent,available_at=T+timedelta(hours=available),
            direction='BUY',status='DEFINED',protected_turn_id=protected.id,endpoint_turn_id=reference.id,
            origin_ticks=90,endpoint_ticks=110,details={},version_id=ident+'_v')
    parent=lineage('parent',None,0);child=lineage('child','parent',3)
    at=T+timedelta(hours=4)
    completion=Event(id='completion',kind='BREAKOUT',instrument='X',tf='H1',clock=Clock(at,at,at),side='BUY',reference_id=reference.id,scope_id='child')
    events=[completion]
    if case!='none':
        occurs=T+timedelta(hours=3);receipt=T+timedelta(hours=5) if case=='future_opposite' else occurs
        events.append(Event(id='intervening',kind='RANGE_BROKEN' if case=='parent_broken' else 'BOS',
            instrument='X',tf='H1',clock=Clock(occurs,occurs,receipt),side='SELL',
            scope_id='parent' if case=='parent_broken' else 'other' if case=='other_scope' else 'child',
            evidence_status='UNKNOWN' if case=='opposite_unknown' else 'KNOWN'))
    plain=StructureResult((reference,protected),(),(),tuple(events),(parent,child))
    expected=stories._related_reference_uncached(completion,reference,touch,lower,plain)
    actual=stories._related_reference(completion,reference,touch,lower,stories._StoryStructureView(plain,lower))
    assert actual==expected and (actual is not None)==valid


def test_confirmation_range_index_preserves_historical_seed_matches_and_first_ties():
    def version(ident,hour,tag,seed=None):
        return SimpleNamespace(id=ident,available_at=T+timedelta(hours=hour),version_id=tag,
                               parent_id=None,details={'seed_break_event_id':seed} if seed else {})
    rows=(version('seeded',1,'old_seed','break'),version('direct',1,'direct_first'),
          version('seeded',2,'new_unseeded'),version('tie',1,'later_tie','break'),
          version('direct',3,'direct_latest'),version('future',5,'future','break'))
    view=stories._StoryStructureView(StructureResult((),(),(),(),rows))
    for scope in (None,'direct','missing'):
        for hour in (0,1,2,3,4,5):
            at=T+timedelta(hours=hour)
            event=Event(id='break',kind='BREAKOUT',instrument='X',tf='H1',clock=Clock(at,at,at),side='BUY',scope_id=scope)
            candidates=[r for r in rows if r.available_at<=at and (r.id==scope or r.details.get('seed_break_event_id')==event.id)]
            expected=max(candidates,key=lambda r:r.available_at,default=None)
            assert view._confirmation_range_at(event,at) is expected
    at=T+timedelta(hours=2)
    assert view._confirmation_range_at(Event(id='break',kind='BREAKOUT',instrument='X',tf='H1',clock=Clock(at,at,at),side='BUY'),at).version_id=='old_seed'

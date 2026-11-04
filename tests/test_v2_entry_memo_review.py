"""Independent memo isolation and same-clock completion-event preservation."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from collections import Counter
import bishop.v2.entries as entries
from bishop.v2.structure import StructureResult
from bishop.v2.types import Bar,Clock,Event,Instrument,Level,Liquidity,StrategyPolicy

T=datetime(2026,1,5,tzinfo=timezone.utc)


def fixture():
    def b(h,high=103,close=101):
        return Bar('X','H1',T+timedelta(hours=h),T+timedelta(hours=h+1),100,high,95,close)
    pool=Liquidity(id='pool',instrument='X',tf='H4',kind='HIGH',price_ticks=104,
                   formed_at=T+timedelta(hours=4),available_at=T+timedelta(hours=4),form='BAR',details={'role':'IRL'})
    context=Level(id='context',instrument='X',tf='H4',kind='A',price_ticks=100,side='SELL',formed_at=T,available_at=T)
    child=Level(id='child',instrument='X',tf='H1',kind='V',price_ticks=98,side='BUY',formed_at=T,available_at=T)
    parent=Event(id='parent',kind='BREAKOUT',instrument='X',tf='H4',clock=Clock(T,T,T),side='SELL',reference_id=context.id)
    first,extension,reaction,confirmation=b(4,105,104),b(5,109,104),b(6,102,99),b(7,101,97)
    completions=tuple(Event(id=ident,kind=kind,instrument='X',tf='H1',
            clock=Clock(confirmation.end,confirmation.end,confirmation.end),side='SELL',
            reference_id=child.id,bar_ids=(confirmation.id,),scope_id=scope)
            for ident,kind,scope in (('ce_a','BREAKOUT','scope_a'),('ce_b','BOS','scope_b')))
    structures={'H4':StructureResult((),(context,),(pool,),(parent,),()),
                'H1':StructureResult((),(child,),(),(*completions,Event(id='flip',kind='LEVEL_ROLE_CHANGE',instrument='X',tf='H1',clock=Clock(confirmation.end,confirmation.end,confirmation.end),side='SELL',reference_id=child.id)),())}
    frames={'H4':(Bar('X','H4',T,T+timedelta(hours=4),100,104,95,101),),
            'H1':(*tuple(b(h) for h in range(4)),first,extension,reaction,confirmation)}
    return frames,structures,completions


def test_risk_memo_separates_context_guards_destination_and_ordered_scope_proofs(monkeypatch):
    frames,structures,completions=fixture()
    contexts=[('plain_a',{} ,None,None),('plain_b',{},None,None),
              ('guard',{'counterweekly_target_guard_required':True},None,None),
              ('weekly',{'initial_weekly_relation':'COUNTER_WEEKLY'},None,None),
              ('retracement',{'retracement':True},None,None),
              ('dest_a',{},150,'dest_a'),('dest_b',{},150,'dest_b')]
    stories=tuple(SimpleNamespace(id=ident,side='SELL',available_at=T,clock=Clock(T,T,T),
                    details=details,destination_ticks=price,destination_ref_id=ref)
                  for ident,details,price,ref in contexts)
    calls=[]
    def risk(side,entry,at,tf,bars,levels,liquidity,story,instrument,policy,**kwargs):
        signature=(story.destination_ticks,story.destination_ref_id,
                   story.details.get('counterweekly_target_guard_required'),
                   story.details.get('initial_weekly_relation'),story.details.get('retracement'))
        scopes=kwargs['protection_range_ids'];proofs=kwargs['protection_evidence_ids']
        calls.append((signature,scopes,proofs))
        code=int(bool(signature[2]))+2*int(signature[3]=='COUNTER_WEEKLY')+4*int(bool(signature[4]))+8*int(signature[0] is not None)
        return SimpleNamespace(stop_ticks=106+int('scope_b' in scopes),target_ticks=90-code,
            status='ELIGIBLE',details={'unresolved_reasons':[],'risk_context':signature,
                                     'risk_scopes':scopes,'risk_proofs':proofs})
    monkeypatch.setattr(entries,'plan',risk)
    reference_calls=[];original_reference=entries._breakout_retest_level
    def reference(*a,**k):
        reference_calls.append(a[0].id)
        return original_reference(*a,**k)
    monkeypatch.setattr(entries,'_breakout_retest_level',reference)
    result=entries.detect_setups(frames,structures,stories,Instrument('X','1','1',calendar_id='24x7_utc_v1'),
                                StrategyPolicy(entry_tfs=('H1',),origin_tfs=('D',)))
    actual=[s for s in result.setups if s.model=='confirmation_bo']
    assert len(actual)==14
    assert Counter(reference_calls)==Counter({'ce_a':1,'ce_b':1})
    assert len(calls)==12  # identical-context story aliases reuse; differing contexts/proofs do not.
    assert Counter(s.story_id for s in actual)==Counter({s.id:2 for s in stories})
    by_story={s.id:s for s in stories}
    for setup in actual:
        story=by_story[setup.story_id]
        assert setup.details['risk_context']==(story.destination_ticks,story.destination_ref_id,
            story.details.get('counterweekly_target_guard_required'),story.details.get('initial_weekly_relation'),story.details.get('retracement'))
        chosen=[e for e in completions if e.id in setup.evidence_ids]
        assert len(chosen)==1
        assert setup.details['risk_scopes']==(chosen[0].scope_id,)
        assert chosen[0].id in setup.details['risk_proofs']


def test_shared_reaction_cache_preserves_story_birth_and_sponsoring_break_cutoffs():
    frames,structures,_=fixture()
    def story(ident,hour=0,birth=None):
        occurrence=T+timedelta(hours=hour);available=T+timedelta(hours=hour if birth is None else birth)
        return SimpleNamespace(id=ident,side='SELL',available_at=available,
            clock=Clock(occurrence,occurrence,available),details={},destination_ticks=None,destination_ref_id=None)
    early=story('early');later_parent=story('later_parent',1);unborn=story('unborn',birth=9)
    instrument=Instrument('X','1','1',calendar_id='24x7_utc_v1')
    policy=StrategyPolicy(entry_tfs=('H1',),origin_tfs=('D',),target_profile='fixed3r')
    baseline=entries.detect_setups(frames,structures,(early,),instrument,policy)
    # Build the shared cache while visiting an ineligible later-parent story
    # first. It must not remove eligible reactions from the earlier story.
    combined=entries.detect_setups(frames,structures,(later_parent,early,unborn),instrument,policy)
    assert baseline.setups
    assert tuple(s for s in combined.setups if s.story_id=='early')==baseline.setups
    assert not any(s.story_id in ('later_parent','unborn') for s in combined.setups)

"""Confirmed story bias is distinct from a naked latest structural break."""
import json,random
from datetime import datetime,timedelta,timezone
import pytest
from bishop.bias_snapshot import snapshot,TERMINAL
from bishop.v2.types import Bar,Instrument,StrategyPolicy
from bishop.v2.simulation import Costs
from bishop.v2 import engine

AT='2026-06-24T12:00:00+00:00'


def view(stories,partial=False,proof=None):
    return dict(as_of=AT,instrument={'symbol':'GBPUSD'},policy={'origin_tfs':['D']},
                scope='CONFIRMED_BIAS_ONLY',story_context_evaluated=True,
                status='PARTIAL_UNVALIDATED' if partial else 'COMPUTED_UNVALIDATED',
                stories=[dict(id=side,instrument='GBPUSD',origin_tf='D',side=side,
                              clock={'available_at':AT},state='CONFIRMED',route='kl_structural',
                              details={},level_id='level') for side in stories],
                story_events=[],coverage={},story_context_readiness={} if proof is None else {'D':proof},
                structural_context={'D':{'state':'DIRECTIONAL','side':'SELL','current_segment':{'ready':True}}})


def test_latest_internal_break_cannot_overwrite_confirmed_rejection_bias():
    row=snapshot(view(['BUY']))['rows'][0]
    assert row['side']=='BUY' and row['basis']=='CONFIRMED_STORIES'
    assert row['structural_context']['side']=='SELL'
    for sides,state in [(['BUY','SELL'],'CONFLICT'),([], 'NO_CONFIRMED_BIAS')]:
        row=snapshot(view(sides))['rows'][0]
        assert row['side'] is None and row['state']==state


def test_raw_current_segment_readiness_cannot_certify_story_evidence():
    row=snapshot(view(['BUY'],partial=True))['rows'][0]
    assert row['side'] is None and row['state']=='DATA_INCOMPLETE'
    row=snapshot(view(['BUY'],partial=True,proof={'ready':True}))['rows'][0]
    assert row['side']=='BUY' and row['coverage_scope']=='CURRENT_SEGMENT_ONLY'
    row=snapshot(view(['BUY'],proof={'ready':False}))['rows'][0]
    assert row['side'] is None and row['state']=='DATA_INCOMPLETE'


def test_waiting_external_break_never_falls_back_to_raw_direction():
    data=view([])
    data['story_events']=[dict(id='wait',kind='BIAS_WAIT_EXTERNAL_BREAK',tf='D',
                              clock={'available_at':AT},details={'reason':'required_reference_not_broken'})]
    row=snapshot(data)['rows'][0]
    assert row['state']=='WAIT_EXTERNAL_BREAK' and row['side'] is None
    assert row['waiting_external_break'][0]['id']=='wait'


def test_confirmed_bias_mode_builds_stories_but_never_detects_or_executes_entries(monkeypatch):
    at=datetime(2026,1,5,tzinfo=timezone.utc);price=1000;bars=[];rng=random.Random(41)
    for i in range(72):
        close=price+rng.choice((-12,-8,-4,4,8,12))
        bars.append(Bar('X','H1',at+timedelta(hours=i),at+timedelta(hours=i+1),price,max(price,close)+3,min(price,close)-3,close));price=close
    feed={'instrument':Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1'),'bars':bars}
    args=dict(as_of=bars[-1].end,costs=Costs(),policy=StrategyPolicy(origin_tfs=('H4',),entry_tfs=('H1',),
        source_profile='source_all',bias_reference_profile='source_lineage',risk_profile='fixed11',target_profile='fixed3r'))
    full=engine.run(feed,**args)
    def forbidden(*a,**k):pytest.fail('Confirmed-bias mode must not detect or execute entries')
    monkeypatch.setattr(engine,'detect_setups',forbidden);monkeypatch.setattr(engine,'simulate',forbidden)
    bias=engine.run(feed,**args,confirmed_story_bias_only=True)
    terminal={e['reference_id'] for e in full['story_events'] if e['kind'] in TERMINAL}
    active=[s for s in full['stories'] if s['id'] not in terminal and s['state']=='CONFIRMED'
            and s['details'].get('owner_selection')!='BLOCKED_COUNTERWEEKLY']
    assert full['stories'] and active
    assert bias['summary']['stories']==len(active)
    assert {(s['origin_tf'],s['side']) for s in bias['stories']}=={(s['origin_tf'],s['side']) for s in active}
    assert len(bias['stories'])==len(bias['active_story_groups'])
    assert bias['scope']=='CONFIRMED_BIAS_ONLY' and bias['story_context_evaluated']
    assert bias['setups']==bias['orders']==bias['observations']==[]
    assert bias['run_id']!=full['run_id']
    assert len(json.dumps(bias).encode())<2_000_000
    assert bias['story_reactions'] and bias['bias_confirmation_events']


@pytest.mark.parametrize('extra',[{'bias_only':True},{'detection_only':True},{'execution_feed':{}},
                                 {'management_actions':({'kind':'CANCEL'},)}])
def test_confirmed_bias_mode_rejects_incompatible_execution_modes(extra):
    with pytest.raises(ValueError,match='confirmed-story'):
        engine.run({},as_of=AT,confirmed_story_bias_only=True,**extra)


def test_scan_requires_external_environment_and_keeps_source_comparison_explicit(tmp_path,monkeypatch):
    from bishop import scan_bias
    metadata=tmp_path/'manifest.json';metadata.write_text(json.dumps({'venue':'ICMARKETS','symbol':'GBPUSD'}))
    calls=[]
    def compute(*a,**k):
        calls.append(k)
        return {**view([]),'scope':'BIAS_ONLY' if k['bias_only'] else 'CONFIRMED_BIAS_ONLY'}
    monkeypatch.setattr(scan_bias,'run',compute)
    args=['--input',str(tmp_path/'unused.csv'),'--manifest',str(metadata),'--as-of',AT,'--out',str(tmp_path/'out')]
    scan_bias.main(args)
    assert calls[-1]['confirmed_story_bias_only'] and not calls[-1]['bias_only']
    assert calls[-1]['policy'].bias_reference_profile=='last_pre_touch'
    scan_bias.main([*args,'--bias-reference-profile','source_lineage'])
    assert calls[-1]['policy'].bias_reference_profile=='source_lineage'
    scan_bias.main([*args,'--structural-only'])
    assert calls[-1]['bias_only'] and not calls[-1]['confirmed_story_bias_only']


@pytest.mark.parametrize('wrong', ['policy','mode'])
def test_persisted_confirmed_hour_cannot_reuse_wrong_policy_or_mode(tmp_path,monkeypatch,wrong):
    from bishop import scan_bias,settings
    from bishop.paper_store import Store
    from bishop.v2.types import stable_id
    from dataclasses import replace
    from hashlib import sha256
    raw=tmp_path/'raw.csv';raw.write_text('frozen\n')
    meta={'venue':'ICMARKETS','symbol':'GBPUSD'};path=tmp_path/'manifest.json';path.write_text(json.dumps(meta))
    policy=replace(settings.strategy_policy(settings.DEFAULTS),bias_reference_profile='last_pre_touch')
    saved={**view([]),'schema':'test','scope':'BIAS_ONLY' if wrong=='mode' else 'CONFIRMED_BIAS_ONLY',
           'input':{'sha256':sha256(raw.read_bytes()).hexdigest(),'manifest':stable_id('manifest',meta)},
           'policy':{'origin_tfs':['D'],'id':'another' if wrong=='policy' else policy.id}}
    store=Store();store.persist_result(saved,'2026-06-24T12:00:00+00:00',namespace='confirmed-bias-scan-GBPUSD')
    monkeypatch.setattr('bishop.runtime.application_store',lambda:store)
    with pytest.raises(ValueError,match='different bias '+wrong):
        scan_bias.main(['--input',str(raw),'--manifest',str(path),'--as-of',AT,'--out',str(tmp_path/'out'),'--persist'])


def test_current_pending_reference_can_wait_despite_older_gap_but_not_a_missing_tail():
    from bishop.v2.types import Clock,Event,Level,Turn
    from bishop.v2.structure import StructureResult
    from bishop.v2.stories import StoryResult
    at=datetime(2026,1,5,tzinfo=timezone.utc)
    def bar(tf,hours,duration,o=100,hi=106,lo=94,c=100):
        return Bar('X',tf,at+timedelta(hours=hours),at+timedelta(hours=hours+duration),o,hi,lo,c)
    formation=bar('D',-24,24);origin=bar('D',0,24,c=101)
    anchor=bar('H4',0,4,c=105);confirm=bar('H4',4,4,c=100);touch=bar('H4',8,4,c=101)
    ref=Turn(id='frozen',instrument='X',tf='H4',kind='H',price_ticks=105,
             formed_at=anchor.end,available_at=confirm.end,anchor_bar_id=anchor.id,
             confirmation_bar_id=confirm.id,bar_ids=(anchor.id,confirm.id))
    level=Level(id='daily',instrument='X',tf='D',kind='V',price_ticks=95,side='BUY',
                formed_at=formation.end,available_at=formation.end,bar_ids=(formation.id,))
    reaction=Event(id='reaction',kind='KL_REJECTION',instrument='X',tf='D',side='BUY',
                   clock=origin.clock,reference_id=level.id,price_ticks=95,bar_ids=(origin.id,),
                   details={'origin_bar_id':origin.id,'level_tf':'D'})
    frozen=Event(id='frozen_event',kind='BIAS_REFERENCE_FROZEN',instrument='X',tf='H4',side='BUY',
                 clock=Clock(touch.start,touch.end,origin.end),reference_id=ref.id,price_ticks=105,
                 bar_ids=(touch.id,),details={'origin_tf':'D','confirmation_tf':'H4','reaction_id':reaction.id})
    wait=Event(id='wait',kind='BIAS_WAIT_EXTERNAL_BREAK',instrument='X',tf='D',side='BUY',
               clock=origin.clock,reference_id=reaction.id,bar_ids=(origin.id,),details={'confirmation_tf':'H4'})
    stories=StoryResult((),(frozen,wait),(reaction,),())
    structures={'D':StructureResult((),(level,),(),(),()),'H4':StructureResult((ref,),(),(),(),())}
    frames={'D':(formation,origin),'H4':(anchor,confirm,touch)}
    base=tuple(bar('H1',i,1) for i in range(-24,28))
    inst=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    policy=StrategyPolicy(origin_tfs=('D',),entry_tfs=('H1',))
    clock=at+timedelta(hours=28)
    coverage={'D':{'status':'COMPLETE'},'H4':{'status':'COMPLETE'}}
    raw={'D':{'state':'DIRECTIONAL','side':'SELL','current_segment':{'ready':True}}}
    def projected(bars,missing):
        feed={'instrument':inst,'bars':bars,'hashes':{},'coverage':{'status':'INCOMPLETE','missing':missing,'missing_slots':len(missing)}}
        return engine._confirmed_bias_result(feed,inst,clock,None,policy,Costs(),stories,structures,frames,coverage,raw,())
    older=[(at-timedelta(hours=25)).isoformat()]
    row=snapshot(projected(base,older))['rows'][0]
    assert row['state']=='WAIT_EXTERNAL_BREAK' and row['side'] is None
    assert row['coverage_scope']=='CURRENT_SEGMENT_ONLY'
    assert row['story_context_readiness']['proof_kind']=='PENDING_EXTERNAL_BREAK'
    missing_tail=[*older,(clock-timedelta(hours=1)).isoformat()]
    row=snapshot(projected(base[:-1],missing_tail))['rows'][0]
    assert row['state']=='DATA_INCOMPLETE' and row['side'] is None
    # Same-clock reactions must retain their own frozen/wait pairing.
    from dataclasses import replace
    reaction2=replace(reaction,id='reaction2')
    frozen2=replace(frozen,id='frozen2',details={**frozen.details,'reaction_id':reaction2.id})
    wait2=replace(wait,id='wait2',reference_id=reaction2.id)
    stories=StoryResult((),(frozen,wait2,frozen2,wait),(reaction,reaction2),())
    paired=snapshot(projected(base,older))['rows'][0]
    assert paired['state']=='WAIT_EXTERNAL_BREAK'
    assert set(paired['story_context_readiness']['proven_pending_event_ids'])=={'wait','wait2'}
    # Liquidity waiting evidence depends on the prior candle, with no KL required.
    liquidity=replace(reaction,kind='PRIOR_CANDLE_SWEEP',reference_id=formation.id)
    stories=StoryResult((),(frozen,wait),(liquidity,),())
    structures={**structures,'D':StructureResult((),(),(),(),())}
    liquidity_row=snapshot(projected(base,older))['rows'][0]
    assert liquidity_row['state']=='WAIT_EXTERNAL_BREAK'
    assert liquidity_row['story_context_readiness']['proof_kind']=='PENDING_EXTERNAL_BREAK'
    frames={**frames,'D':(origin,)}
    missing_source=snapshot(projected(base,older))['rows'][0]
    assert missing_source['state']=='DATA_INCOMPLETE'


def test_source_comparison_cannot_persist_operational_bias(tmp_path):
    from bishop import scan_bias
    with pytest.raises(ValueError, match='diagnostic only'):
        scan_bias.main(['--input','unused','--manifest','unused',
                        '--as-of',AT,'--out',str(tmp_path),
                        '--bias-reference-profile','source_lineage','--persist'])

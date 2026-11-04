"""Offline collection replay orchestration; never source-match acceptance tests."""
import json
from pathlib import Path
from copy import deepcopy
import pytest
from reports import replay_collected_teacher_examples_v2 as mod


def example():
    return deepcopy(json.loads(Path('tests/bishop_examples.json').read_text())['examples'][0])


def input_item(tmp_path, case, tf='H1', **updates):
    data=tmp_path/'collect.csv.gz';data.write_bytes(b'frozen-test-input')
    meta=dict(symbol=case['pair'],case_ids=[case['id']],base_tf=tf,tick_size='0.00001',
        distance_unit='0.0001',calendar_id='fx_ny_v1',anchor_id='ny17_wall_v2',
        calendar_version='declared',asset_class='FX',price_basis='BID',source_id='test',
        venue='ICMARKETS',sha256=mod.digest(data),requested_start='2025-01-01T00:00:00Z',
        requested_end='2027-01-01T00:00:00Z',**updates)
    sidecar=tmp_path/'collect.csv.manifest.json';sidecar.write_text(json.dumps(meta))
    return mod.inventory_manifests(tmp_path)


def test_resolution_and_case_id_are_required_no_upsampling(tmp_path):
    c=example();c['tf']='M45'
    items=input_item(tmp_path,c)
    assert mod.plan_case(c,items)['status']=='MISSING_EXPLICIT_MATCHING_INPUT'
    items=input_item(tmp_path,c,tf='M5')
    assert mod.plan_case(c,items)['status']=='PLANNED'
    items[0]['metadata']['case_ids']=[]
    assert mod.plan_case(c,items)['status']=='MISSING_EXPLICIT_MATCHING_INPUT'
    assert mod.required_base('H3')=='H1'
    assert mod.required_base('M2') is None


def test_finer_minute_input_can_support_m45_without_approving_conflicting_calendar(tmp_path):
    c=example();c['tf']='M45'
    items=input_item(tmp_path,c,tf='M1')
    result=mod.plan_case(c,items)
    assert result['status']=='PLANNED'
    assert result['base_tf']=='M1' and result['requested_base_tf']=='M5'
    items[0]['metadata']['calendar_conflict_nonzero_or_unknown_volume_rows']=1
    assert mod.plan_case(c,items)['status']=='OBSERVED_CALENDAR_CONFLICT_UNRESOLVED'


def test_preferred_valid_resolution_is_selected_before_finer_input(tmp_path):
    c=example();preferred=input_item(tmp_path,c)[0]
    finer=deepcopy(preferred);finer['metadata']['base_tf']='M1'
    finer['metadata']['requested_start']='2026-06-01T00:00:00Z'
    assert mod.plan_case(c,[finer,preferred])['base_tf']=='H1'
    preferred['metadata']['calendar_id']='unresolved_broker_schedule'
    assert mod.plan_case(c,[finer,preferred])['base_tf']=='M1'


def test_snapshot_date_is_explicit_end_of_date_not_setup_clock():
    c=example();c['chart_snapshot_date']='2026-07-31'
    p=mod.plan_case(c,[])
    assert p['as_of']=='2026-08-01T00:00:00+00:00'
    assert p['clock_kind']=='EXPLORATORY_END_OF_SNAPSHOT_DATE_NOT_TEACHER_CLOCK'
    c['id']='pdf-p08-eurgbp-buy-1';c['chart_snapshot_date']='2026-07-23'
    assert mod.plan_case(c,[])['as_of']=='2026-07-23T18:08:00+00:00'
    c['chart_snapshot_date']=None
    assert mod.plan_case(c,[])['status']=='UNRESOLVED_DATE'


@pytest.mark.parametrize('updates,status',[
    ({'anchor_id':'unresolved'},'UNRESOLVED_CALENDAR'),
    ({'asset_class':'CRYPTO_SURROGATE'},'SURROGATE_MARKET_UNRESOLVED'),
    ({'symbol_mapping_status':'SURROGATE_QUOTE_CURRENCY_DIFFERENT'},'SURROGATE_MARKET_UNRESOLVED'),
])
def test_unresolved_market_and_calendar_remain_inventory_rows(tmp_path,updates,status):
    c=example();items=input_item(tmp_path,c)
    items[0]['metadata'].update(updates)
    assert mod.plan_case(c,items)['status']==status


def test_all_forty_remain_denominator_without_data(tmp_path,monkeypatch):
    monkeypatch.setattr(mod,'run',lambda *a,**k:pytest.fail('no inputs must not execute'))
    result=mod.execute('tests/bishop_examples.json',tmp_path/'missing',tmp_path/'out',
                       case_ids=[example()['id']])
    assert result['fixture_count']==40 and len(result['results'])==40
    assert result['strict_counts']=={'PASS':0,'FAIL':0,'UNRESOLVED':40}
    assert sum(r['status']=='NOT_REQUESTED' for r in result['results'])==39


def fixture_file(tmp_path):
    c=example();path=tmp_path/'fixture.json'
    path.write_text(json.dumps({'schema_version':1,'examples':[c]}));return path,c


def empty_engine(**extra):
    return dict(instrument={'tick_size':'0.00001'},setups=[],orders=[],stories=[],observations=[],
                policy={},costs={},summary={'setups':0,'orders':0},coverage={'base':{'missing_slots':0}},
                selection={'rejected':[]},support=[],**extra)


@pytest.mark.parametrize('profile',['bishop_confirmation','owner_aggressive'])
def test_explicit_profile_is_declared_before_run_and_preserved_in_diagnostics(tmp_path,monkeypatch,profile):
    fixture,c=fixture_file(tmp_path);input_item(tmp_path,c);out=tmp_path/profile
    def engine(*args,**kwargs):
        declaration=json.loads((out/'run_plan.json').read_text())
        assert declaration['source_profile']==profile
        assert declaration['risk_profile']=='context_liquidity'
        assert kwargs['policy'].source_profile==profile
        assert kwargs['policy'].risk_profile=='context_liquidity'
        assert kwargs['policy'].research_later_kl_irl is False
        result=empty_engine()
        result['policy']={'source_profile':profile,'risk_profile':'context_liquidity'}
        result['selection']['rejected']=[{'reason':'AMBIGUOUS_EXECUTION_PLAN'}]
        result['support']=[{'route':'direct_entry_episode','reason':'direct_scope_broken'}]
        return result
    monkeypatch.setattr(mod,'run',engine)
    result=mod.execute(fixture,tmp_path,out,time_budget_seconds=0,forward_days=0,source_profile=profile)
    assert result['results'][0]['strict_status']=='UNRESOLVED'
    import gzip
    report=json.loads(gzip.decompress(Path(result['results'][0]['report']).read_bytes()))
    assert report['policy']['source_profile']==profile
    assert report['implementation_diagnostics']['selection_reasons']=={'AMBIGUOUS_EXECUTION_PLAN':1}
    assert report['implementation_diagnostics']['retired_direct_reasons']=={'direct_scope_broken':1}


def test_unknown_profile_rejected_without_running_engine(tmp_path,monkeypatch):
    monkeypatch.setattr(mod,'run',lambda *a,**k:pytest.fail('invalid profile must not execute'))
    with pytest.raises(ValueError,match='source_profile'):
        mod.execute('tests/bishop_examples.json',tmp_path,tmp_path/'out',source_profile='source_all')


def test_declares_before_engine_and_keeps_actual_strict_gate(tmp_path,monkeypatch):
    fixture,c=fixture_file(tmp_path);input_item(tmp_path,c);out=tmp_path/'out'
    def engine(*args,**kwargs):
        assert (out/'run_plan.json').exists()
        assert kwargs['costs'].spread_ticks==0
        assert kwargs['policy'].entry_tfs==('H4','H2','H1')
        return empty_engine()
    monkeypatch.setattr(mod,'run',engine)
    result=mod.execute(fixture,tmp_path,out,time_budget_seconds=0)
    assert result['results'][0]['status']=='COMPUTED_DIAGNOSTIC'
    assert result['results'][0]['strict_status']=='UNRESOLVED'


def test_runtime_abort_never_becomes_zero_signal_computation(tmp_path,monkeypatch):
    fixture,c=fixture_file(tmp_path);input_item(tmp_path,c)
    def timeout(*a,**k):raise mod.ReplayBudgetExceeded()
    monkeypatch.setattr(mod,'run',timeout)
    r=mod.execute(fixture,tmp_path,tmp_path/'out')
    assert r['results'][0]['status']=='ABORTED_RUNTIME'
    assert r['strict_counts']['UNRESOLVED']==1
    assert 'summary' not in r['results'][0]


def test_frozen_fixture_mutation_aborts_before_reporting_match(tmp_path,monkeypatch):
    fixture,c=fixture_file(tmp_path);input_item(tmp_path,c)
    def mutate(*a,**k):
        fixture.write_text(fixture.read_text()+'\n')
        return empty_engine()
    monkeypatch.setattr(mod,'run',mutate)
    with pytest.raises(RuntimeError,match='frozen replay'):
        mod.execute(fixture,tmp_path,tmp_path/'out',time_budget_seconds=0)


def forward_fixture():
    from datetime import datetime,timedelta,timezone
    from bishop.v2.types import Bar,Clock,Order,Instrument,jsonable
    from bishop.v2.simulation import Costs,simulate
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    inst=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    order=Order(id='frozen',setup_id='s',instrument='X',tf='M1',model='test',side='BUY',
                kind='MARKET',clock=Clock(t,t,t),entry_ticks=10,stop_ticks=5,target_ticks=20)
    past=(Bar('X','M1',t,t+timedelta(minutes=1),10,21,9,20),
          Bar('X','M1',t+timedelta(minutes=1),t+timedelta(minutes=2),20,21,19,20))
    snap=t+timedelta(minutes=2);horizon=t+timedelta(minutes=3)
    original=simulate((order,),past,inst,Costs(),snap)
    result=jsonable(dict(orders=(order,),observations=original['observations'],actions=[],costs=Costs()))
    plan=dict(as_of=snap.isoformat(),forward_as_of=horizon.isoformat(),input_path='frozen.csv.gz',history_start=t.isoformat())
    return t,inst,past,result,plan


def test_forward_uses_frozen_orders_no_detector_and_preserves_closed_prefix(monkeypatch):
    from datetime import timedelta
    from bishop.v2.types import Bar
    t,inst,past,result,plan=forward_fixture()
    future=Bar('X','M1',t+timedelta(minutes=2),t+timedelta(minutes=3),20,100,1,5)
    monkeypatch.setattr(mod,'run',lambda *a,**k:pytest.fail('forward must never detect again'))
    monkeypatch.setattr(mod,'load_feed',lambda *a,**k:dict(instrument=inst,bars=(*past,future),coverage={'missing_slots':0}))
    out=mod.forward_outcomes(result,plan,{'calendar_id':'24x7_utc_v1'})
    assert out['frozen_order_ids']==['frozen']
    assert out['observations']==result['observations']
    assert out['observations'][0]['outcome']=='WIN'
    assert out['future_detector_calls']==0 and not out['post_snapshot_management_inferred']
    # Even an explicit future management row is not inferred/used at snapshot.
    result['actions']=[{'order_id':'frozen','kind':'BREAK_EVEN','at':plan['forward_as_of']}]
    assert mod.forward_outcomes(result,plan,{'calendar_id':'24x7_utc_v1'})['known_actions']==[]


def test_forward_without_future_data_is_explicit_not_claimed_outcome(monkeypatch):
    t,inst,past,result,plan=forward_fixture()
    monkeypatch.setattr(mod,'load_feed',lambda *a,**k:dict(instrument=inst,bars=past,coverage={'missing_slots':1}))
    out=mod.forward_outcomes(result,plan,{'calendar_id':'24x7_utc_v1'})
    assert out['status']=='NO_POST_SNAPSHOT_DATA'
    assert out['observations']==result['observations']


def test_annotation_is_explicit_exploration_not_fixture_clock_mutation(tmp_path):
    c=example();c['chart_snapshot_date']=None
    items=input_item(tmp_path,c)
    annotation=dict(example_id=c['id'],pair=c['pair'],clock_status='CROSSHAIR_ONLY',
                    candidate_event_search=['2026-08-03T00:00:00Z','2026-08-08T00:00:00Z'])
    assert mod.plan_case(c,items)['status']=='UNRESOLVED_DATE'
    p=mod.plan_case(c,items,annotation)
    assert p['status']=='PLANNED' and p['as_of']=='2026-08-08T00:00:00+00:00'
    assert p['clock_kind']=='ANNOTATED_EXPLORATORY_EVENT_SEARCH_NOT_SETUP_OR_FILL_CLOCK'
    assert c['chart_snapshot_date'] is None


def test_p22_source_ceiling_is_not_end_of_date_or_fill_clock():
    case=next(c for c in json.loads(Path('tests/bishop_examples.json').read_text())['examples']
              if c['id']=='pdf-p22-xagusd-sell-1')
    before=json.dumps(case,sort_keys=True)
    plan=mod.plan_case(case,[])
    assert plan['as_of']=='2026-07-13T05:24:00+00:00'
    assert plan['scan_start']=='2026-07-09T00:00:00+00:00'
    assert plan['clock_kind']=='SOURCE_SNAPSHOT_MINUTE_NOT_SETUP_CLOCK'
    assert json.dumps(case,sort_keys=True)==before
    assert case['verification']=='unresolved' and case['setup_time'] is None

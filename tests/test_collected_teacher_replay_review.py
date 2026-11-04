"""Independent collected-data replay boundaries; local fakes only."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import pytest
from reports import replay_collected_teacher_examples_v2 as mod
from bishop.v2.types import Bar,Clock,Order,Instrument,jsonable
from bishop.v2.simulation import Costs,simulate

T=datetime(2026,1,1,tzinfo=timezone.utc)


def open_snapshot():
    instrument=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    order=Order(id='frozen',setup_id='setup',instrument='X',tf='M1',model='synthetic',
                side='BUY',kind='MARKET',clock=Clock(T,T,T),entry_ticks=10,stop_ticks=5,target_ticks=20)
    past=Bar('X','M1',T,T+timedelta(minutes=1),10,11,9,10)
    snapshot=past.end;end=T+timedelta(minutes=2)
    actions=[dict(order_id='frozen',kind='AMEND',target_ticks=15,available_at=snapshot.isoformat()),
             dict(order_id='frozen',kind='MANUAL_CLOSE',price_ticks=99,available_at=end.isoformat())]
    original=simulate((order,),(past,),instrument,Costs(),snapshot,actions=actions)
    result=jsonable(dict(orders=(order,),observations=original['observations'],actions=actions,costs=Costs()))
    plan=dict(as_of=snapshot.isoformat(),forward_as_of=end.isoformat(),input_path='local',history_start=T.isoformat())
    return instrument,result,plan,past


def test_open_forward_uses_typed_frozen_order_and_only_snapshot_known_management(monkeypatch):
    instrument,result,plan,past=open_snapshot();before=deepcopy(result)
    future=Bar('X','M1',past.end,T+timedelta(minutes=2),10,16,9,15)
    monkeypatch.setattr(mod,'run',lambda *a,**k:pytest.fail('future detection forbidden'))
    monkeypatch.setattr(mod,'load_feed',lambda *a,**k:dict(instrument=instrument,bars=(past,future),coverage={'missing_slots':0}))
    actual_simulate=mod.simulate
    def checked(orders,*args,**kwargs):
        assert len(orders)==1 and isinstance(orders[0],Order) and isinstance(orders[0].clock,Clock)
        return actual_simulate(orders,*args,**kwargs)
    monkeypatch.setattr(mod,'simulate',checked)
    output=mod.forward_outcomes(result,plan,{'calendar_id':'24x7_utc_v1'})
    assert result==before
    assert output['frozen_order_ids']==['frozen']
    assert len(output['known_actions'])==1 and output['known_actions'][0]['kind']=='AMEND'
    assert output['observations'][0]['outcome']=='WIN'
    assert output['observations'][0]['realized_ticks_quantity']=='5'
    assert output['observations'][0]['fill_window']['start']==T.isoformat()
    assert output['future_detector_calls']==0


def test_future_order_in_snapshot_selection_is_rejected_before_loading_forward_prices(monkeypatch):
    _,result,plan,_=open_snapshot()
    future=T+timedelta(minutes=2)
    result['orders'][0]['clock']=jsonable(Clock(future,future,future))
    monkeypatch.setattr(mod,'load_feed',lambda *a,**k:pytest.fail('future-order selection must fail first'))
    with pytest.raises(ValueError,match='future order'):
        mod.forward_outcomes(result,plan,{'calendar_id':'24x7_utc_v1'})


def test_bad_input_hash_cannot_drop_case_from_all_forty_denominator(tmp_path,monkeypatch):
    document=json.loads(Path('tests/bishop_examples.json').read_text());case=document['examples'][0]
    data=tmp_path/'raw.csv.gz';data.write_bytes(b'original')
    metadata=dict(symbol=case['pair'],case_ids=[case['id']],base_tf='H1',tick_size='0.00001',
        distance_unit='0.0001',calendar_id='fx_ny_v1',anchor_id='ny17_wall_v2',calendar_version='declared',
        asset_class='FX',price_basis='BID',source_id='test',venue='ICMARKETS',sha256=mod.digest(data),
        requested_start='2025-01-01T00:00:00Z',requested_end='2027-01-01T00:00:00Z')
    (tmp_path/'raw.csv.manifest.json').write_text(json.dumps(metadata));data.write_bytes(b'changed')
    monkeypatch.setattr(mod,'run',lambda *a,**k:pytest.fail('bad hash must prevent detector'))
    output=mod.execute('tests/bishop_examples.json',tmp_path,tmp_path/'output',case_ids=(case['id'],))
    assert output['fixture_count']==40 and len(output['results'])==40
    row=next(r for r in output['results'] if r['id']==case['id'])
    assert row['status']=='INPUT_HASH_MISMATCH' and row['strict_status']=='UNRESOLVED'
    assert output['strict_counts']=={'PASS':0,'FAIL':0,'UNRESOLVED':40}
    declaration=json.loads((tmp_path/'output'/'run_plan.json').read_text())
    assert declaration['budget_scope']=='DETECTOR_AND_FORWARD_LOOP_EXCLUDES_PLANNING_AND_FINAL_HASH_CHECKS'



def test_new_completed_bar_straddling_snapshot_advances_existing_order_only(monkeypatch):
    instrument=Instrument('X','1','1',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1')
    order=Order(id='existing',setup_id='s',instrument='X',tf='M5',model='synthetic',
                side='BUY',kind='MARKET',clock=Clock(T,T,T),entry_ticks=10,stop_ticks=5,target_ticks=20)
    past=Bar('X','M5',T,T+timedelta(minutes=5),10,11,9,10)
    snapshot=T+timedelta(minutes=8)
    original=simulate((order,),(past,),instrument,Costs(),snapshot)
    result=jsonable(dict(orders=(order,),observations=original['observations'],actions=[],costs=Costs()))
    overlapping=Bar('X','M5',past.end,T+timedelta(minutes=10),10,21,9,20)
    plan=dict(as_of=snapshot.isoformat(),forward_as_of=overlapping.end.isoformat(),
              input_path='local',history_start=T.isoformat())
    monkeypatch.setattr(mod,'run',lambda *a,**k:pytest.fail('forward must not detect'))
    monkeypatch.setattr(mod,'load_feed',lambda *a,**k:dict(instrument=instrument,bars=(past,overlapping),coverage={'missing_slots':0}))
    output=mod.forward_outcomes(result,plan,{'calendar_id':'24x7_utc_v1'})
    assert output['status']=='SIMULATED_FROZEN_ORDERS'
    assert output['frozen_order_ids']==['existing']
    assert output['observations'][0]['outcome']=='WIN'
    assert output['observations'][0]['fill_window']==result['observations'][0]['fill_window']
    assert output['events'][-1]['clock']['occurred_from']==overlapping.start.isoformat()
    assert output['events'][-1]['clock']['occurred_to']==overlapping.end.isoformat()

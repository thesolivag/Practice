"""Finer execution must preserve detection prices and prospective causality."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from bishop.v2.types import Instrument, Bar, Setup, Clock, StrategyPolicy
from bishop.v2.execution_feed import prepare_execution_feed
from bishop.v2.simulation import Costs

T = datetime(2026, 1, 1, tzinfo=timezone.utc)
INST = Instrument('X', '1', '1', calendar_id='24x7_utc_v1', anchor_id='utc_epoch_v1')


def feeds(tmp_path, missing=False, changed=False):
    p=tmp_path/'m1.csv'
    rows=['time,open,high,low,close']
    for i in range(180):
        if missing and i==20: continue
        rows.append(f'{(T+timedelta(minutes=i)).isoformat()},10,{12 if changed and i==20 else 11},9,10')
    p.write_text('\n'.join(rows)+'\n')
    manifest=dict(symbol='X',tick_size='1',distance_unit='1',calendar_id='24x7_utc_v1',
                  anchor_id='utc_epoch_v1',price_basis='BID',source_id='fine',venue='UNSPECIFIED',base_tf='M1')
    base=tuple(Bar('X','H1',T+timedelta(hours=i),T+timedelta(hours=i+1),10,11,9,10) for i in range(3))
    detection=dict(instrument=INST,bars=base,manifest={})
    return {'path':str(p),'manifest':manifest},detection,base


def test_exact_finer_rollup_and_separate_hashes(tmp_path):
    spec,detection,base=feeds(tmp_path)
    fine,audit=prepare_execution_feed(spec,detection,base,T,T+timedelta(hours=3))
    assert len(fine['bars'])==180
    assert audit['compared_bars']==3 and audit['rollup_status']=='EXACT_OHLC_MATCH'
    assert audit['hashes']['sha256']


def test_holes_preserved_and_incomplete_bins_not_certified(tmp_path):
    spec,detection,base=feeds(tmp_path,missing=True)
    fine,audit=prepare_execution_feed(spec,detection,base,T,T+timedelta(hours=3))
    assert len(fine['bars'])==179
    assert audit['coverage']['missing_slots']==1
    assert audit['compared_bars']==2
    assert audit['incomparable_bins']==[T.isoformat()]
    assert audit['rollup_status']=='EXACT_ON_COMPLETE_BINS_PARTIAL_COVERAGE'


def test_corrected_fine_prices_cannot_rewrite_frozen_detection(tmp_path):
    spec,detection,base=feeds(tmp_path,changed=True)
    with pytest.raises(ValueError,match='OHLC differs'):
        prepare_execution_feed(spec,detection,base,T,T+timedelta(hours=3))


def test_incomplete_bins_still_reject_observed_price_contradictions(tmp_path):
    spec,detection,base=feeds(tmp_path,missing=True)
    from pathlib import Path
    p=Path(spec['path']);p.write_text(p.read_text().replace(',10,11,9,10',',10,12,9,10',1))
    with pytest.raises(ValueError,match='contradict'):
        prepare_execution_feed(spec,detection,base,T,T+timedelta(hours=3))


def test_cross_feed_price_basis_rejected(tmp_path):
    spec,detection,base=feeds(tmp_path)
    spec['manifest']['price_basis']='ASK'
    with pytest.raises(ValueError,match='price_basis'):
        prepare_execution_feed(spec,detection,base,T,T+timedelta(hours=3))


@pytest.mark.parametrize('missing',[False,True])
def test_engine_uses_fine_for_cap_and_final_but_coarse_for_detection(tmp_path,monkeypatch,missing):
    import bishop.v2.engine as engine
    spec,detection,base=feeds(tmp_path,missing=missing)
    story=SimpleNamespace(id='story',details={})
    setups=tuple(Setup(id=f's{i}',instrument='X',tf='H1',model='test',side='BUY',story_id='story',
        clock=Clock(at,at,at),entry_ticks=8,stop_ticks=5,target_ticks=12,risk_profile='fixed11')
        for i,at in enumerate((T,T+timedelta(hours=1))))
    seen=[]
    def detect(*args,**kwargs):
        # Actual structure aggregation stays H1; no M1 detection frame added.
        seen.append(args)
        return SimpleNamespace(setups=setups,events=(),support=())
    monkeypatch.setattr(engine,'find_stories',lambda *args:SimpleNamespace(stories=(story,),events=(),support=()))
    monkeypatch.setattr(engine,'detect_setups',detect)
    calls=[]
    original=engine.simulate
    def simulate(orders,bars,*args,**kwargs):
        calls.append((tuple(bars),args[2]))
        return original(orders,bars,*args,**kwargs)
    monkeypatch.setattr(engine,'simulate',simulate)
    monkeypatch.setattr(engine,'jsonable',lambda x:x)
    result=engine.run(detection,as_of=T+timedelta(hours=3),scan_start=T,
        costs=Costs(),policy=StrategyPolicy(entry_tfs=('H1',),origin_tfs=('D',)),
        max_open_orders=1,execution_feed=spec)
    assert tuple(result['setups'])==setups
    assert seen and 'M1' not in seen[0][0]
    assert all(b.source_id!='fine' for bars in seen[0][0].values() for b in bars)
    assert result['selection']['rejected']==[{'setup_id':'s1','reason':'EXPOSURE_CAP'}]
    assert calls and all(b.tf=='M1' and b.available_at<=at for bars,at in calls for b in bars)
    assert len(calls[-1][0])==180-int(missing)
    if missing:
        assert result['status']=='PARTIAL_UNVALIDATED'
        assert result['observations'][0]['censor_reason']=='MISSING_ACTIVE_DATA'
    else:
        assert result['execution_input']['rollup_status']=='EXACT_OHLC_MATCH'


def test_late_internal_fine_bars_cannot_rewrite_execution(tmp_path):
    import csv
    spec,detection,base=feeds(tmp_path)
    with open(spec['path']) as stream:
        rows=list(csv.DictReader(stream))
    for i,row in enumerate(rows):
        row['available_at']=(T+timedelta(minutes=50 if i==20 else i+1)).isoformat()
    with open(spec['path'],'w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=tuple(rows[0]))
        writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match='nonmonotone execution publication'):
        prepare_execution_feed(spec,detection,base,T,T+timedelta(hours=3))

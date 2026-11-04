"""Validated quote paths and publication-aware no-touch range proofs."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import gzip
import json
from types import SimpleNamespace
import pytest
from bishop.v2.refinement_evidence import load_refinement_evidence
from bishop.v2.simulation import Costs
from bishop.v2.types import Bar, Clock, Instrument, Order

T=datetime(2026,1,1,tzinfo=timezone.utc)
INST=Instrument('X','0.00001','0.0001',calendar_id='24x7_utc_v1',anchor_id='utc_epoch_v1',source_id='fine')


def make(tmp_path, rows=None, *, ask_complete=True, corrupt=False):
    rows=rows or [(1000,80),(2000,100),(3000,79)]
    first=int(T.timestamp()*1000)
    actual=[(first+at,p) for at,p in rows]
    records=[]
    for quote in ('BID','ASK'):
        descending=sorted(actual,key=lambda r:r[0],reverse=True)
        encoded=[];prev_at=None;prev_p=None
        for at,p in descending:
            encoded.append(dict(timestamp=at if prev_at is None else at-prev_at,
                                tick=p if prev_p is None else p-prev_p))
            prev_at,prev_p=at,p
        complete=quote=='BID' or ask_complete
        page=dict(quote=quote,from_ms=first,to_ms=first+59999,
                  has_more=not complete,protocol_ticks=encoded)
        doc=dict(quote=quote,from_ms=first,to_exclusive_ms=first+60000,complete=complete,
                 source_environment='demo',symbol_metadata=dict(name='X',symbol_id=8),
                 pages=[page],ticks=sorted(actual,key=lambda row:row[0]) if complete else [])
        raw=gzip.compress(json.dumps(doc).encode(),mtime=0);name=quote+'.gz';(tmp_path/name).write_bytes(raw)
        records.append(dict(path='ignored/prefix/'+name,quote=quote,from_ms=first,
                            to_exclusive_ms=first+60000,complete=complete,
                            rows=len(actual) if complete else 0,
                            sha256='wrong' if corrupt and quote=='BID' else sha256(raw).hexdigest()))
    (tmp_path/'status.json').write_text(json.dumps(dict(status='RAW_QUOTE_AUDIT_COLLECTED',records=records)))
    finebar=Bar('X','M1',T,T+timedelta(minutes=1),actual[0][1],max(p for _,p in actual),
                min(p for _,p in actual),actual[-1][1],source_id='fine')
    coarse=Bar('X','H1',T,T+timedelta(hours=1),100,105,75,100,source_id='coarse')
    feed=dict(instrument=INST,bars=(finebar,),manifest={'broker_symbol':'X'},hashes={'test':'frozen'})
    evidence=load_refinement_evidence(tmp_path,(coarse,),feed)
    return evidence,finebar,coarse,feed


def order(side='SELL',kind='LIMIT'):
    return Order(id='o',setup_id='s',instrument='X',tf='M1',model='test',side=side,
                 kind=kind,clock=Clock(T,T,T),entry_ticks=100,
                 stop_ticks=110 if side=='SELL' else 70,
                 target_ticks=80 if side=='SELL' else 120)


def prove(evidence,o,state='PENDING',at=None,stop=None,target=None):
    return evidence.prove_gap(o,state,T+timedelta(minutes=20),T+timedelta(minutes=21),
        o.stop_ticks if stop is None else stop,o.target_ticks if target is None else target,
        0,at or T+timedelta(hours=1),'24x7_utc_v1','M1')


def test_exact_ticks_ignore_target_before_entry_and_prove_later_target(tmp_path):
    evidence,bar,_,_=make(tmp_path)
    assert evidence.resolve_limit_target(order(),bar,Costs())=='TARGET_AFTER_ENTRY'
    assert evidence.audit['comparable_m1_bars']==1
    evidence.audit['comparable_m1_bars']=999
    assert evidence.audit['comparable_m1_bars']==1
    with pytest.raises(TypeError):evidence._ticks_by_bar['x']=()


def test_same_ms_entry_target_order_is_not_inferred(tmp_path):
    evidence,bar,_,_=make(tmp_path,[(1000,90),(2000,100),(2000,79),(3000,95)])
    assert evidence.resolve_limit_target(order(),bar,Costs()) is None


def test_filled_without_later_target_must_keep_exposure(tmp_path):
    evidence,bar,_,_=make(tmp_path,[(1000,80),(2000,100),(3000,90)])
    assert evidence.resolve_limit_target(order(),bar,Costs())=='FILLED_WITHOUT_EXIT_IN_MINUTE'


def test_incomplete_ask_window_cannot_supply_quote_proof(tmp_path):
    evidence,bar,_,_=make(tmp_path,ask_complete=False)
    assert evidence.resolve_limit_target(order(),bar,Costs()) is None


def test_wrong_compressed_hash_is_rejected(tmp_path):
    with pytest.raises(ValueError,match='hash mismatch'):make(tmp_path,corrupt=True)


def test_ic_source_environment_mismatch_rejected(tmp_path):
    evidence,bar,coarse,feed=make(tmp_path)
    feed['instrument']=replace(INST,venue='ICMARKETS')
    feed['manifest'].update(source_id='not_the_expected_environment',base_tf='M1',symbol_metadata={'symbol_id':8})
    with pytest.raises(ValueError,match='environment'):load_refinement_evidence(tmp_path,(coarse,),feed)


def test_coarse_no_touch_proof_requires_publication_and_strict_bounds(tmp_path):
    evidence,_,coarse,_=make(tmp_path)
    untouched=replace(order(),entry_ticks=106)
    assert prove(evidence,untouched,at=T+timedelta(minutes=30)) is None
    ready,refs=prove(evidence,untouched)
    assert ready==coarse.available_at and refs==(coarse.id,)
    assert prove(evidence,replace(untouched,entry_ticks=105)) is None
    assert prove(evidence,replace(untouched,kind='MARKET')) is None
    # BUY entry below the entire coarse range remains unfilled; equality does not.
    assert prove(evidence,replace(order('BUY'),entry_ticks=74)) is not None
    assert prove(evidence,replace(order('BUY'),entry_ticks=75)) is None


def test_filled_no_touch_proof_requires_both_exit_levels_outside_range(tmp_path):
    evidence,_,_,_=make(tmp_path)
    assert prove(evidence,order(),'FILLED',stop=110,target=70) is not None
    assert prove(evidence,order(),'FILLED',stop=105,target=70) is None
    assert prove(evidence,order(),'FILLED',stop=110,target=75) is None
    assert prove(evidence,order('BUY'),'FILLED',stop=70,target=110) is not None
    assert prove(evidence,order('BUY'),'FILLED',stop=75,target=110) is None


def test_quote_ohlc_mismatch_and_publication_correction_cannot_reuse_proof(tmp_path):
    evidence,bar,coarse,feed=make(tmp_path)
    assert evidence.resolve_limit_target(order(),replace(bar,available_at=T+timedelta(minutes=2)),Costs()) is None
    feed['bars']=(replace(bar,high_ticks=101),)
    changed=load_refinement_evidence(tmp_path,(coarse,),feed)
    assert changed.resolve_limit_target(order(),feed['bars'][0],Costs()) is None
    assert changed.audit['uncomparable_m1_bars']==1

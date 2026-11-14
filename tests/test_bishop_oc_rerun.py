from dataclasses import replace
from datetime import timedelta
import pytest
from bishop.v2.entries import three_candle_oc
from bishop.v2.types import Bar,StrategyPolicy,Clock
from tests.test_bishop_capacity_replay import T,I,bar,setup,order
from slk import bishop_oc_replay as Y


def pattern(side='BUY'):
    rows=[(110,112,104,105),(105,107,98,100),(100,108,99,107)]
    if side=='SELL':rows=[(300-o,300-l,300-h,300-c) for o,h,l,c in rows]
    return tuple(Bar('X','H1',T+timedelta(hours=i),T+timedelta(hours=i+1),*r,source_id='test') for i,r in enumerate(rows))

@pytest.mark.parametrize('side',['BUY','SELL'])
def test_third_close_crosses_oc_not_first_open_or_wick(side):
    bars=pattern(side);got=three_candle_oc(bars,side)
    assert got['price_ticks']==(105 if side=='BUY' else 195)
    assert got['bar_ids']==tuple(b.id for b in bars)
    assert got['confirmation_closed_at']==bars[-1].end.isoformat()

@pytest.mark.parametrize('bad_close',[100,104,105])
def test_wick_only_or_equal_close_is_not_engulfing(bad_close):
    bars=list(pattern());bars[-1]=replace(bars[-1],close_ticks=bad_close)
    assert three_candle_oc(bars,'BUY') is None


def test_exact_triplet_same_segment_completed_required():
    p,a,b=pattern()
    assert three_candle_oc((replace(p,open_ticks=104,close_ticks=110),a,b),'BUY') is None
    assert three_candle_oc((p,a,replace(b,complete=False)),'BUY') is None
    assert three_candle_oc((p,a,replace(b,segment_id='other')),'BUY') is None
    assert three_candle_oc((p,a,replace(b,start=b.start+timedelta(minutes=1))),'BUY') is None
    assert three_candle_oc((a,b),'BUY') is None


def test_first_close_policy_records_quote_gap_without_moving_reference():
    p,a,b=pattern();a=replace(a,open_ticks=106)
    assert three_candle_oc((p,a,b),'BUY',gap_policy='exact') is None
    got=three_candle_oc((p,a,b),'BUY',gap_policy='first_close')
    assert got['price_ticks']==105 and got['gap_ticks']==1 and got['second_open_ticks']==106


def test_detector_uses_corrected_rule_h1_h2_and_physical_prefix(monkeypatch):
    import bishop.v2.engine as engine
    def run(feed,**kw):
        assert kw['policy'].entry_tfs==('H1','H2')
        assert kw['engulfing_rule']=='three_candle_oc' and kw['oc_gap_policy']=='first_close'
        assert all(b.available_at<=kw['as_of'] for b in feed['bars'])
        return {'passed':True}
    monkeypatch.setattr(engine,'run',run)
    assert Y.detect({'instrument':I,'bars':(bar(0),bar(1)),'manifest':{}},T+timedelta(hours=1))[0]=={'passed':True}


def test_h1_h2_same_batch_admits_one_and_never_replaces_active():
    stories=[{'id':'story','details':{}}];policy=StrategyPolicy(entry_tfs=('H1','H2'))
    a=setup('h1');b=replace(setup('h2'),tf='H2',model='confirmation_standing_extreme')
    selected,why=Y.select([b,a],stories,policy,'standalone')
    assert len(selected)==1 and selected[0][0].tf=='H1'
    assert why['SINGLE_POSITION_OR_PENDING']==1
    assert not Y.select([a,b],stories,policy,'standalone',active=1)[0]


def test_rr_family_stays_reserved_until_every_variant_flat():
    book={}
    for rr in (1,2,3):
        o=replace(order(),id=f'o{rr}',target_ticks=100+5*rr)
        Y.add_order(book,o,setup(),f'recognition_{rr}R',source='same')
        book[o.id]['observation']={'outcome':'WIN' if rr<3 else 'OPEN','net_r':rr if rr<3 else None}
    assert Y.family_occupied(book,(),T,'recognition')==1
    assert Y.family_occupied(book,(),T,'standalone')==0
    book['o3']['observation']={'outcome':'LOSS','net_r':-1}
    assert Y.family_occupied(book,(),T,'recognition')==0


def test_unknown_capacity_release_does_not_invent_result():
    from tests.test_bishop_capacity import row,bar as capacity_bar
    r=row();r['mode']='recognition_3R';book={'o':r}
    assert Y.family_occupied(book,(),r['order'].available_at,'recognition')==1
    before=dict(r['observation'])
    at=r['order'].available_at+timedelta(hours=3)
    assert Y.family_occupied(book,(capacity_bar(2,80,120),),at,'recognition')==0
    assert r['observation']==before


def test_timeframe_matches_are_measured_not_assumed():
    state=Y.new_state();a=replace(setup('h1'),details={'three_candle_oc':{'price_ticks':100}})
    b=replace(setup('h2'),tf='H2',model='confirmation_standing_extreme')
    Y.record_equivalences(state,[a,b],T,'base')
    assert len(state['cross_tf_matches'])==1
    Y.record_equivalences(state,[a,replace(b,entry_ticks=101)],T,'base')
    assert len(state['cross_tf_matches'])==1


def test_close_above_junction_is_valid_even_if_third_open_gaps_above():
    p,a,b=pattern();b=replace(b,open_ticks=106)
    assert three_candle_oc((p,a,b),'BUY')['price_ticks']==105


def test_review_bundle_uses_new_outcomes_and_marks_incomplete(tmp_path,monkeypatch):
    from slk.bishop_oc_review_bundle import build_bundle
    from bishop.v2.types import jsonable
    inputs=tmp_path/'inputs';results=tmp_path/'results';out=tmp_path/'out'
    Y.dump(inputs/'manifest.json',{'pairs':['X','Y'],'end':(T+timedelta(hours=1)).isoformat()})
    Y.dump(inputs/'X.json.gz',{'instrument':I,'bars':[bar(0)],'manifest':{}})
    state=Y.new_state();state['audit']=[{'at':(T+timedelta(hours=1)).isoformat()}]
    s=replace(setup(),model='confirmation_engulfed_oc',details={'three_candle_oc':{'price_ticks':100}})
    o=replace(order(),model=s.model)
    Y.add_order(state['book'],o,s,'standalone')
    Y.dump(results/'year-12-X/checkpoint.json.gz',state)
    got=build_bundle(inputs,results,out)
    assert got=={'entries':1,'incomplete':['Y']}
    saved=Y.load(out/'index.json.gz')
    assert saved['status']=='PARTIAL'
    assert saved['entries'][0]['targets'][0]['result']['outcome']=='OPEN'
    assert saved['entries'][0]['confirmation']=='engulfing'

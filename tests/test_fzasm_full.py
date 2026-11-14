from datetime import datetime,timedelta,timezone
from dataclasses import replace
import pandas as pd
import pytest
from fzasm.types import Candle, BiasDirection as B, MapType as M, LevelType as L, KeyLevel, DailyMapResult
from fzasm.full_context import active_levels,map_candidates,choose_map
from fzasm.full_model import FullASMEngine
from fzasm.full_replay import FullOutcome,replay_full
from test_fzasm_repaired import setup,bar,AT

BASE=datetime(2026,1,1,tzinfo=timezone.utc)

def candles(rows,tf='D1',start=BASE):
    delta=timedelta(days=1) if tf=='D1' else timedelta(hours=int(tf[1:]))
    return [Candle(start+i*delta,*r,timeframe=tf) for i,r in enumerate(rows)]


def test_daily_range_map_has_real_target_and_explicit_knowledge_time():
    bars=candles([(105,110,100,104),(104,109,99,106)])
    result=map_candidates(bars)
    m=next(x for x in result if x.map_type==M.MAP_2_CANDLE_RANGE_CRT)
    assert (m.origin_level,m.target_level,m.timestamp)==(99,110,bars[-1].available_at)
    assert choose_map(result,106)[0]==m
    assert m not in map_candidates(bars+[Candle(bars[-1].available_at,106,111,103,108,timeframe='D1')])


def test_double_sided_sweep_does_not_infer_direction_from_color():
    assert map_candidates(candles([(105,110,100,104),(104,111,99,106)]))==[]


def test_conflicting_maps_abstain_instead_of_hardcoded_priority():
    long=DailyMapResult(M.MAP_2_CANDLE_RANGE_CRT,B.BULLISH,90,120,105,0,'x',BASE)
    short=replace(long,bias=B.BEARISH,origin_level=130,target_level=80)
    assert choose_map([long,short],100)==(None,'CONFLICTING_DAILY_MAPS')
    assert choose_map([long,replace(long,target_level=110)],100)[0].target_level==110


def test_structural_break_uses_body_pivot_not_wick():
    bars=candles([(100,106,98,104),(104,120,100,110),(108,109,100,102),
                  (102,112,101,111)])
    result=[x for x in map_candidates(bars) if x.map_type==M.MAP_1_STRUCTURAL_RANGE]
    assert len(result)==1
    assert bars[-1].close<bars[1].high  # Did not break the wick120.
    assert result[0].target_level==120  # Existing high, not invented range projection.
    assert result[0].timestamp==bars[-1].available_at


def test_map3_tracks_opposing_run_boundary():
    bars=candles([(109,110,103,104),(104,105,100,101),(101,106,99,105)])
    m=next(x for x in map_candidates(bars) if x.map_type==M.MAP_3_CONSECUTIVE_LEG_SWEEP)
    assert m.bias==B.BULLISH and m.target_level==110 and m.origin_level==99


def test_levels_need_closed_fvg_and_terminal_invalidation():
    bars=candles([(105,106,100,101),(101,110,101,109),(109,112,108,111)],'H4')
    assert not [p for p in active_levels(bars[:2]) if p.level_type==L.ORDER_BLOCK]
    ob=next(p for p in active_levels(bars) if p.level_type==L.ORDER_BLOCK)
    assert ob.timestamp==bars[-1].available_at
    broken=bars+[Candle(bars[-1].available_at,111,112,98,99,timeframe='H4')]
    levels=active_levels(broken)
    assert not any(p.level_type==L.ORDER_BLOCK for p in levels)
    bb=next(p for p in levels if p.level_type==L.BREAKER_BLOCK)
    assert bb.direction==B.BEARISH and bb.timestamp==broken[-1].available_at
    twice=broken+[Candle(broken[-1].available_at,99,110,98,109,timeframe='H4')]
    assert not any(p.level_type==L.BREAKER_BLOCK for p in active_levels(twice))


def context_case(monkeypatch):
    import fzasm.full_model as mod
    start=BASE.replace(hour=0)
    hourly=candles([(105,110,100,104),(104,109,99,108)],'H1',start)
    dm=DailyMapResult(M.MAP_2_CANDLE_RANGE_CRT,B.BULLISH,90,130,110,0,'test',start)
    level=KeyLevel(L.OPEN_CLOSE,B.BULLISH,100,100,start,'H4',metadata={'rule':'test'})
    monkeypatch.setattr(mod,'map_candidates',lambda *a:[dm])
    monkeypatch.setattr(mod,'active_levels',lambda *a:[level])
    return hourly,dm,level


def test_full_engine_entry_freezes_context_and_no_duplicate(monkeypatch):
    h,dm,level=context_case(monkeypatch)
    e=FullASMEngine(extra_pairs={'EURUSD'},entry_policy='h1_av')
    now=h[-1].available_at
    got=e.scan_asset('EURUSD',{'H1':h},now)
    assert got and got.entry_price==104 and got.take_profit_2==130
    assert got.stop_loss==pytest.approx(99-.0003)
    assert not got.daily_map.entry_only
    assert got.entry_evidence['teacher_validated'] is False
    assert e.scan_asset('EURUSD',{'H1':h},now) is None


def test_future_candles_do_not_change_the_decision(monkeypatch):
    h,_,_=context_case(monkeypatch)
    now=h[-1].available_at
    future=Candle(now,108,900,1,500,timeframe='H1')
    def run(bars):
        return FullASMEngine(extra_pairs={'EURUSD'},entry_policy='h1_av').scan_asset('EURUSD',{'H1':bars},now)
    assert run(h)==run(h+[future])


def test_unfinished_sweep_cannot_create_order(monkeypatch):
    h,_,_=context_case(monkeypatch)
    assert FullASMEngine(extra_pairs={'EURUSD'},entry_policy='h1_av').scan_asset('EURUSD',{'H1':h},h[-1].available_at-timedelta(minutes=1)) is None


def test_itf_level_must_preexist_sweep(monkeypatch):
    h,_,level=context_case(monkeypatch)
    import fzasm.full_model as mod
    # Detector contract: the engine must only pass pre-sweep closed candles.
    supplied=[]
    def levels(bars,tolerance):
        supplied.extend(bars)
        return []
    monkeypatch.setattr(mod,'active_levels',levels)
    h4=Candle(h[-1].timestamp,104,109,99,108,timeframe='H4')
    e=FullASMEngine(extra_pairs={'EURUSD'},entry_policy='h1_av')
    assert e.scan_asset('EURUSD',{'H1':h,'H4':[h4]},h[-1].available_at) is None
    assert supplied==[]


def test_structural_exit_is_full_target_not_unsupported_partial():
    s=setup();t=FullOutcome(s,0)
    t.evaluate_bar(bar(101,102,99,101),0)
    t.evaluate_bar(bar(105,111,104,110,AT+timedelta(minutes=1)),1)
    assert t.status['structural_result_r']=='OPEN'
    t.evaluate_bar(bar(110,121,105,120,AT+timedelta(minutes=2)),2)
    assert t.structural_result_r==2
    assert t.r1_result_r==1 and t.r2_result_r==2


def test_research_window_is_bounded(tmp_path):
    with pytest.raises(ValueError,match='31 days'):
        replay_full('EURUSD',pd.DataFrame(),[],BASE,BASE+timedelta(days=40),tmp_path)


def test_daily_confluence_and_sponsored_rejection_maps():
    bars=candles([(105,108,99,100),(100,110,100,108),(108,109,101,104),(104,108,100,106)])
    assert any(m.map_type==M.MAP_4_CRT_POI_CONFLUENCE for m in map_candidates(bars))
    for low,kind in [(104,M.MAP_5A_REJECTION),(103,M.MAP_5B_SWEEP_INVALIDATION)]:
        following=Candle(bars[-1].available_at,106,108,low,107,timeframe='D1')
        candidates=map_candidates(bars+[following])
        rejection=[m for m in candidates if m.map_type==kind]
        assert rejection and all(m.target_level==109 for m in rejection)


def test_h2_fallback_reaches_lower_timeframe_entry_path(monkeypatch):
    h,dm,level=context_case(monkeypatch)
    e=FullASMEngine(extra_pairs={'EURUSD'},entry_policy='auto')
    h2=candles([(105,110,100,104),(104,109,99,108)],'H2',BASE-timedelta(hours=2))
    # Latest H1 is not a sweep; H2 is. An entry evaluator must see H2.
    nonsweep=candles([(105,110,100,104),(104,109,101,108)],'H1')
    seen=[]
    monkeypatch.setattr(e,'_entry',lambda symbol,closed,sweep,daily,now:seen.append(sweep.sweep_candle.timeframe))
    e.scan_asset('EURUSD',{'H1':nonsweep,'H2':h2},h2[-1].available_at)
    assert seen==['H2']


def test_same_clock_route_precedence_and_m10_fallback(monkeypatch):
    from fzasm.entry import EntryModelEvaluator as E
    h,dm,_=context_case(monkeypatch);sweep=setup().h1_sweep
    now=BASE.replace(hour=2)
    bars={tf:[Candle(now-timedelta(minutes=n),100,102,99,101,timeframe=tf)] for tf,n in [('M5',5),('M10',10),('M15',15)]}
    calls=[];sentinel=object()
    def choose(symbol,candles,sweep,daily,route,**kwargs):
        calls.append((candles[-1].timeframe,route))
        return sentinel if candles[-1].timeframe=='M10' and route=='fvg_av_overlap' else None
    monkeypatch.setattr(E,'evaluate_swing_retest',choose)
    monkeypatch.setattr(E,'evaluate_h1_av_m5',lambda *args:None)
    result=FullASMEngine(entry_policy='auto')._entry('EURUSD',bars,sweep,dm,now)
    assert result is sentinel
    assert calls==[('M5','fvg_av_overlap'),('M5','order_block'),('M10','fvg_av_overlap')]


def test_replay_writes_reconcilable_targets_without_future_fills(tmp_path,monkeypatch):
    import fzasm.full_replay as replay_module
    start=pd.Timestamp(AT);end=start+pd.Timedelta(minutes=20)
    index=pd.date_range(start-pd.Timedelta(days=1),end-pd.Timedelta(minutes=1),freq='min')
    df=pd.DataFrame(dict(open=101.,high=102.,low=99.,close=101.),index=index)
    class Engine:
        VERSION='fixture'
        diagnostics={}
        last_review={}
        def __init__(self,**kwargs):pass
        def scan_asset(self,symbol,closed,now):
            return replace(setup(),timestamp=now,take_profit_1=120,take_profit_2=120) if now==start+pd.Timedelta(minutes=5) else None
    monkeypatch.setattr(replay_module,'FullASMEngine',Engine)
    daily=[Candle(start-pd.Timedelta(days=2),100,110,90,105,timeframe='D1')]
    trades,manifest=replay_full('EURUSD',df,daily,start,end,tmp_path)
    assert len(trades)==1 and trades[0].filled_at==start+pd.Timedelta(minutes=5)
    table=pd.read_csv(tmp_path/'trades.csv')
    assert len(table)==6 and table.signal_id.nunique()==1
    assert set(table[table.target!='asian_result_r'].status)=={'UNKNOWN'}
    assert table.gross_r.isna().all()


def test_map_rules_are_price_reflection_symmetric():
    bars=candles([(105,108,99,100),(100,110,100,108),(108,109,101,104),(104,108,100,106),(106,108,103,107)])
    reflected=[replace(c,open=200-c.open,high=200-c.low,low=200-c.high,close=200-c.close) for c in bars]
    original=map_candidates(bars)
    inverse=map_candidates(reflected)
    for m in original:
        assert any(other.map_type==m.map_type and other.bias!=m.bias and other.target_level==200-m.target_level
                   and other.origin_level==200-m.origin_level and other.timestamp==m.timestamp for other in inverse)


def test_full_replay_rejects_invalid_ohlc_and_empty_period(tmp_path):
    start=pd.Timestamp(BASE);end=start+pd.Timedelta(hours=1)
    index=pd.date_range(start-pd.Timedelta(hours=1),end,freq='min')
    df=pd.DataFrame(dict(open=100.,high=101.,low=99.,close=100.),index=index)
    with pytest.raises(ValueError,match='No M1 data inside'):
        replay_full('EURUSD',df[df.index<start],[],start,end,tmp_path)
    df.iloc[-2,df.columns.get_loc('high')]=90
    with pytest.raises(ValueError,match='Invalid M1 OHLC'):
        replay_full('EURUSD',df,[],start,end,tmp_path)


def test_decision_clock_cannot_silently_shift_session_timezone():
    with pytest.raises(ValueError,match='UTC decision clock'):
        FullASMEngine().scan_asset('EURUSD',{},BASE.astimezone(timezone(timedelta(hours=1))))

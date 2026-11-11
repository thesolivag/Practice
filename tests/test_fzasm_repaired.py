from datetime import datetime, timedelta, timezone
from dataclasses import replace
import pandas as pd
import pytest
from fzasm.types import *
from fzasm.entry import EntryModelEvaluator
from fzasm.engine import FZASMEngine
from fzasm.execution import TradeOutcome
from fzasm.data import resample_ohlc, df_to_candles, load_minute_df
from fzasm.backtest import backtest_pair, compute_metrics

AT = datetime(2025,1,6,1,tzinfo=timezone.utc)
def bar(o,h,l,c,at=AT,tf='M1'):
    return Candle(at,o,h,l,c,timeframe=tf)
def setup():
    sweep_bar = bar(100,110,90,105,AT-timedelta(hours=1),'H1')
    sweep = HourlySweepResult(True,BiasDirection.BULLISH,sweep_bar,sweep_bar,90)
    bias = DailyMapResult(MapType.MAP_2_CANDLE_RANGE_CRT,BiasDirection.BULLISH,90,120,110,.8,'test',AT)
    return TradeSetup('EURUSD',AT,BiasDirection.BULLISH,EntryModelType.MODEL_A_CHOCH_RETEST,100,90,110,120,2,bias,sweep)

def open_trade():
    t=TradeOutcome(setup(),0)
    # Fill, with no target/stop interaction.
    t.evaluate_bar(bar(101,102,99,101),0)
    assert t.status['r1_result_r']=='OPEN'
    return t

@pytest.mark.parametrize('tf,minutes',[('M5',5),('M10',10),('M15',15)])
def test_lower_tf_shift_places_pending_retest_not_close_entry(tf,minutes):
    s=setup()
    prices=[(102,104,101,103),(103,105,102,104),(104,105,101,102),(102,106,102,105),(106,109,106,108)]
    candles=[bar(*ohlc,AT+timedelta(minutes=i*minutes),tf) for i,ohlc in enumerate(prices)]
    got=EntryModelEvaluator.evaluate_entry('EURUSD',candles,s.h1_sweep,s.daily_map)
    assert got and got.timeframe==tf
    assert got.timestamp==candles[-1].available_at
    assert got.entry_price==106 and got.entry_price!=candles[-1].close
    assert got.stop_loss<90
    assert TradeOutcome(got,0).status['r1_result_r']=='PENDING'
    # Future execution price never feeds into the confirmation function.
    bad=replace(s.daily_map,target_level=95)
    assert EntryModelEvaluator.evaluate_entry('EURUSD',candles,s.h1_sweep,bad) is None
    early=[replace(c,timestamp=c.timestamp-timedelta(days=1)) for c in candles]
    assert EntryModelEvaluator.evaluate_entry('EURUSD',early,s.h1_sweep,s.daily_map) is None


def test_inducement_remains_pending_at_untouched_level():
    s=setup();poi=KeyLevel(LevelType.ORDER_BLOCK,s.bias,100,90,AT-timedelta(days=1),'H4')
    prices=[(104,108,103,105),(105,108,102,104),(104,107,102,103),(103,105,101,102),(102,104,101.5,103)]
    candles=[bar(*v,AT+timedelta(minutes=i*5),'M5') for i,v in enumerate(prices)]
    got=EntryModelEvaluator.evaluate_entry('EURUSD',candles,s.h1_sweep,s.daily_map,poi)
    assert got and got.entry_model==EntryModelType.MODEL_B_INDUCEMENT_LIMIT
    assert got.entry_price==100


def test_missing_lower_tf_is_no_trade():
    s=setup()
    assert EntryModelEvaluator.evaluate_entry('EURUSD',[],s.h1_sweep,s.daily_map) is None


def test_future_h4_prices_invisible_and_partial_bins_rejected():
    idx=pd.date_range('2025-01-06',periods=240,freq='min',tz='UTC')
    df=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.},index=idx)
    df.loc[idx[180],'high']=999
    h4=df_to_candles(resample_ohlc(df,'4h'),TimeFrame.H4)
    assert h4[0].high==999 and h4[0].available_at.hour==4
    assert not [c for c in h4 if c.available_at<=AT]
    assert resample_ohlc(df.iloc[:-1],'4h').empty
    assert resample_ohlc(df.drop(idx[90]),'4h').empty


def test_daily_dst_availability_uses_actual_bin_close():
    idx=pd.date_range('2025-03-29',periods=3*1440,freq='min',tz='UTC')
    df=pd.DataFrame({'open':1.,'high':2.,'low':0.,'close':1.},index=idx)
    bars=df_to_candles(resample_ohlc(df,'1D',calendar_timezone='Europe/Athens'),TimeFrame.D1)
    assert any(c.available_at-c.timestamp==timedelta(hours=23) for c in bars)


def test_unfilled_target_never_counts_as_profit():
    t=TradeOutcome(setup(),0);t.evaluate_bar(bar(125,130,121,128),0)
    assert all(getattr(t,a) is None for a in t.attrs)
    assert t.status['r1_result_r']=='PENDING'


def test_actual_fill_then_target():
    t=open_trade();t.evaluate_bar(bar(101,111,100.5,110,AT+timedelta(minutes=1)),1)
    assert t.r1_result_r==1


def test_partial_targets_weight_both_halves_when_be_not_touched():
    t=open_trade();t.evaluate_bar(bar(105,125,104,123,AT+timedelta(minutes=1)),1)
    assert t.fz_result_r==1.5


def test_partial_and_be_same_bar_is_unknown():
    t=open_trade();t.evaluate_bar(bar(105,125,99,123,AT+timedelta(minutes=1)),1)
    assert t.fz_result_r is None and t.status['fz_result_r']=='UNKNOWN'


def test_later_be_target_collision_is_unknown():
    t=open_trade();t.evaluate_bar(bar(105,111,104,110,AT+timedelta(minutes=1)),1)
    assert t.fz_tp1_hit
    t.evaluate_bar(bar(110,125,99,110,AT+timedelta(minutes=2)),2)
    assert t.status['fz_result_r']=='UNKNOWN'


def test_fixed_stop_target_collision_is_unknown():
    t=open_trade();t.evaluate_bar(bar(105,115,85,100,AT+timedelta(minutes=1)),1)
    assert t.r1_result_r is None and t.status['r1_result_r']=='UNKNOWN'


def test_timeout_marks_remaining_exposure_to_market():
    t=open_trade();t.evaluate_bar(bar(101,106,100.5,105,AT+timedelta(minutes=1)),1,max_bars=0)
    assert t.r2_result_r==.5


def test_gap_and_end_of_data_never_flatten_unknowns():
    t=open_trade();t.evaluate_bar(bar(101,106,100.5,105,AT+timedelta(minutes=5)),5)
    assert t.status['r1_result_r']=='UNKNOWN' and t.reasons['r1_result_r']=='DATA_GAP'
    t=open_trade();t.end_of_data(AT+timedelta(minutes=1))
    assert t.r1_result_r is None


def test_before_order_bar_ignored():
    t=TradeOutcome(setup(),0);t.evaluate_bar(bar(100,130,80,120,AT-timedelta(minutes=1)),0)
    assert all(v=='PENDING' for v in t.status.values())


def test_real_minutes_required(tmp_path):
    with pytest.raises(FileNotFoundError,match='Real M1'):
        load_minute_df('EURUSD',2025,2025,str(tmp_path))


def test_runner_future_perturbation_cannot_change_past_inputs(monkeypatch):
    import fzasm.backtest as bt
    idx=pd.date_range('2025-01-06',periods=360,freq='min',tz='UTC')
    df=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.},index=idx)
    class Spy:
        confirmation_tf='M5'
        def __init__(self): self.seen=[]
        def scan_asset(self,pair,bars,current_time):
            assert all(c.available_at<=current_time for seq in bars.values() for c in seq)
            if current_time<=AT+timedelta(hours=1):
                self.seen.append((current_time,repr(bars)))
    monkeypatch.setattr(bt,'load_minute_df',lambda *a:df)
    a=Spy();backtest_pair('EURUSD',2025,2025,a)
    df.loc[idx[180]:,'high']=999
    b=Spy();backtest_pair('EURUSD',2025,2025,b)
    assert a.seen==b.seen and a.seen


def test_engine_excludes_unfinished_inputs_and_freezes_context(monkeypatch):
    s=setup();engine=FZASMEngine(extra_pairs={'EURUSD'},confirmation_tf='M5')
    calls=[]
    def context(symbol,bars,now):
        calls.append(bars)
        return s.h1_sweep,s.daily_map,None
    monkeypatch.setattr(engine,'_build_context',context)
    monkeypatch.setattr(EntryModelEvaluator,'evaluate_entry',lambda *a:None)
    bars={'H4':[bar(100,999,90,100,AT,'H4')], 'M5':[bar(100,104,99,102,AT,'M5')]}
    engine.scan_asset('EURUSD',bars,AT+timedelta(minutes=5))
    engine.scan_asset('EURUSD',bars,AT+timedelta(minutes=10))
    assert len(calls)==1 and calls[0]['H4']==[]

@pytest.mark.parametrize('direction',[BiasDirection.BULLISH,BiasDirection.BEARISH])
def test_mirrored_limit_fill_and_stop(direction):
    s=setup()
    if direction==BiasDirection.BEARISH:
        s=replace(s,bias=direction,stop_loss=110,take_profit_1=90,take_profit_2=80)
    t=TradeOutcome(s,0)
    first=bar(101,102,99,101) if direction==BiasDirection.BULLISH else bar(99,101,98,99)
    t.evaluate_bar(first,0)
    stopbar=bar(99,100,89,90,AT+timedelta(minutes=1)) if direction==BiasDirection.BULLISH else bar(101,111,100,110,AT+timedelta(minutes=1))
    t.evaluate_bar(stopbar,1)
    assert all(getattr(t,a)==-1 for a in t.attrs)


def test_partial_timeout_values_remaining_half():
    t=open_trade()
    t.evaluate_bar(bar(105,111,104,110,AT+timedelta(minutes=1)),1)
    t.evaluate_bar(bar(110,112,104,105,AT+timedelta(minutes=2)),2,max_bars=0)
    assert t.fz_result_r==.75


def test_pending_orders_expire_without_pnl():
    t=TradeOutcome(replace(setup(),timestamp=AT.replace(hour=5,minute=59)),0)
    t.evaluate_bar(bar(105,106,104,105,AT.replace(hour=5,minute=59)),0)
    t.evaluate_bar(bar(105,106,104,105,AT.replace(hour=6)),1)
    assert all(t.status[a]=='UNFILLED' and getattr(t,a) is None for a in t.attrs)


def test_minute_downloader_uses_small_requests_and_month_checkpoints(tmp_path):
    from fzasm.minute_cache import prepare
    class Fake:
        calls=0
        def symbol(self,pair): return {'pip_position':4,'digits':5}
        def trendbar_rows(self,pair,period,lo,hi):
            assert period=='M1' and 0<hi-lo<=4*3600
            self.calls+=1
            return [(lo,100,101,99,100,1)]
    c=Fake();prepare('EURUSD',2025,str(tmp_path),c)
    assert c.calls>0
    c.calls=0;prepare('EURUSD',2025,str(tmp_path),c)
    assert c.calls==0
    assert (tmp_path/'EURUSD_M1.npz').exists()


def test_report_separates_unknowns_and_same_setup_cohorts(tmp_path):
    from fzasm.backtest import generate_report
    t=open_trade();t.end_of_data(AT+timedelta(minutes=1))
    report=generate_report({'EURUSD':[t]},2025,str(tmp_path))
    rows=pd.read_csv(tmp_path/'fzasm_trades.csv')
    assert rows.r1_result_r.isna().all()
    assert rows.r1_result_r_status.iloc[0]=='UNKNOWN'
    assert 'Monthly results' in report and 'Unknown' in report


def test_sweep_cannot_bridge_missing_hour():
    from fzasm.sessions import HourlySweepDetector
    previous=bar(100,110,90,105,AT,'H1')
    current=bar(105,109,89,100,AT+timedelta(hours=2),'H1')
    assert HourlySweepDetector.detect_h1_sweep([previous,current]) is None

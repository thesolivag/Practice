from bishop.v2.types import Instrument
from slk.bishop_session_costs import session,adjusted

def test_dst_rollover_and_half_open_windows():
    for lo,hi in [('2026-01-05T22:00:00Z','2026-01-05T23:00:00Z'),('2026-07-06T21:00:00Z','2026-07-06T22:00:00Z')]:
        assert session({'fill_window':{'start':lo,'end':hi}})=='ROLLOVER_17_NY'
    assert session({'fill_window':{'start':'2026-07-06T20:00:00Z','end':'2026-07-06T21:00:00Z'}})=='ADJACENT_16_OR_18_NY'
    assert session({})=='NO_PROVEN_FILL_WINDOW'

def test_cost_uses_actual_initial_risk_and_unknown_not_zero():
    inst=Instrument('EURUSD','.00001','.0001')
    row={'observation':{'outcome':'WIN','fill_ticks':'100000','initial_stop_ticks':99900,'net_r':'2'}}
    assert adjusted(row,inst,1)==1.9
    assert adjusted(row,inst,20)==0
    row['observation']['outcome']='CENSORED';assert adjusted(row,inst,1) is None

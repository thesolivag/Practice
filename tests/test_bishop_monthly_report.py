import copy
import pytest
from slk.bishop_monthly_report import aggregate,amend,metric

def row(at='2026-01-31T23:00:00+00:00',closed='2026-02-01T01:00:00+00:00',outcome='WIN',r='2'):
    return {'mode':'test','order':{'clock':{'available_at':at}},'closed_at':closed,
        'observation':{'outcome':outcome,'net_r':r,'fill_window':{'start':at,'end':at}}}

def test_entry_month_and_exit_month_are_distinct():
    m,h,roll=aggregate([row()],['2026-01','2026-02'])
    assert m[0]['orders_created']==1 and m[0]['realized_gross_R']==0
    assert m[1]['orders_created']==0 and m[1]['realized_gross_R']==2
    assert m[1]['cumulative_gross_R']==2


def test_ny_rollover_tracks_dst():
    a=row(at='2026-01-05T22:00:00+00:00');b=row(at='2026-07-06T21:00:00+00:00')
    m,h,roll=aggregate([a,b],['2026-01','2026-02','2026-07'])
    assert next(x for x in h if x['submission_hour_NY']==17)['orders']==2
    assert next(x for x in roll if x['fill_window_start_hour_NY']==17)['orders']==2


def test_unknowns_never_become_zero_profit_wins():
    x=metric([row(),row(outcome='CENSORED',r=None),row(outcome='OPEN',r=None)])
    assert x['gross_R']==2 and x['wins']==1 and x['unknown']==1 and x['open']==1
    assert x['win_rate']==100


def test_correction_uses_terminal_event_and_preserves_original():
    a=row(outcome='CENSORED',r=None);before=copy.deepcopy(a)
    change={'order':copy.deepcopy(a['order']),'after':{'outcome':'LOSS','net_r':'-1'},
        'events':[{'kind':'POSITION_STOPPED','clock':{'available_at':'2026-02-02T00:01:00+00:00'},'details':{'remaining':'0'}}]}
    b=amend(a,change,stop=True)
    assert a==before and b['closed_at']=='2026-02-02T00:01:00+00:00'
    with pytest.raises(ValueError,match='resolved'):amend(b,change,stop=True)
    change['order']['clock']['available_at']='2026-02-01T00:00:00+00:00'
    with pytest.raises(ValueError,match='differs'):amend(a,change,stop=True)

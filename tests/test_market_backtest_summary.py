from reports.backtest_bishop_market import settled_summary


def test_unresolved_orders_do_not_become_wins_or_zero_r_closed_trades():
    rows=[dict(id='win',outcome='WIN',net_r='2',fill_ticks='10'),
          dict(id='loss',outcome='LOSS',net_r='-1',fill_ticks='10'),
          dict(id='unknown',outcome='OPEN',net_r=None,fill_ticks='10',censor_reason='UNRESOLVED_INTRABAR_SEQUENCE'),
          dict(id='expired',outcome='EXPIRED',net_r=None,fill_ticks=None)]
    result=settled_summary(rows,[])
    assert result['settled']==2 and result['censored']==1
    assert result['settled_net_r']=='1' and result['resolved_win_rate']==0.5
    assert result['orders']==4 and result['filled']==3


def test_drawdown_uses_close_times_not_order_creation_order():
    rows=[dict(id='loss',outcome='LOSS',net_r='-1',fill_ticks='10'),
          dict(id='win',outcome='WIN',net_r='2',fill_ticks='10')]
    events=[dict(kind='POSITION_TARGET',reference_id='win',clock={'available_at':'2026-06-01T12:00:00Z'}),
            dict(kind='POSITION_STOPPED',reference_id='loss',clock={'available_at':'2026-06-02T12:00:00Z'})]
    assert settled_summary(rows,events)['settled_close_boundary_drawdown_r']=='1'


def test_simultaneous_closes_do_not_invent_an_intrabar_path():
    rows=[dict(id='a-loss',outcome='LOSS',net_r='-1'),
          dict(id='z-win',outcome='WIN',net_r='2')]
    events=[dict(kind='POSITION_STOPPED',reference_id=o['id'],
                 clock={'available_at':'2026-06-01T12:00:00Z'}) for o in rows]
    assert settled_summary(rows,events)['settled_close_boundary_drawdown_r']=='0'
    assert settled_summary(rows,[])['settled_close_boundary_drawdown_r'] is None

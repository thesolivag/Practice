"""Native broker boundaries are compared independently from source trade outcomes."""
from types import SimpleNamespace
from datetime import timedelta
import pytest
from reports.audit_native_candle_alignment import compare_rows,collect_native,START,END,supported_periods


def row(start='2026-07-09T00:00:00+00:00',end='2026-07-09T04:00:00+00:00',**values):
    return dict(start=start,end=end,**dict(open='60.001',high='60.010',low='59.990',close='60.005',**values))


def test_matching_prices_do_not_mask_different_candle_boundaries():
    native=row();rebuilt=row(start='2026-07-09T01:00:00+00:00',end='2026-07-09T05:00:00+00:00')
    result=compare_rows([native],[rebuilt])
    assert result['equal_boundary_count']==0 and result['exact_ohlc_count']==0
    assert len(result['native_only_boundaries'])==len(result['rebuilt_only_boundaries'])==1


def test_equal_boundaries_expose_exact_single_tick_price_change():
    a=row();b={**a,'high':'60.011'}
    result=compare_rows([a],[b])
    assert result['equal_boundary_count']==1 and result['exact_ohlc_count']==0
    assert result['differences'][0]['native_minus_rebuilt']['high']=='-0.001'
    assert compare_rows([a],[a])['exact_ohlc_count']==1
    with pytest.raises(ValueError,match='duplicate'):
        compare_rows([a,a],[a])


def test_installed_protocol_does_not_claim_native_h2():
    assert 'H1' in supported_periods() and 'H4' in supported_periods()
    assert 'H2' not in supported_periods()


def test_collection_is_one_bounded_request_and_excludes_forming_bar():
    def tb(at,lo=6000000):
        return SimpleNamespace(utcTimestampInMinutes=int(at.timestamp()/60),low=lo,
                               deltaOpen=100,deltaHigh=200,deltaClose=100,volume=5)
    seen=[]
    class Client:
        account_id=123
        def _hist_request(self,msg):
            seen.append(msg)
            return SimpleNamespace(trendbar=[tb(START),tb(END.replace(minute=0)-timedelta(hours=1))])
    result=collect_native(Client(),dict(symbol_id=7,digits=3),'H4')
    assert len(seen)==1
    assert seen[0].fromTimestamp==int(START.timestamp()*1000)
    assert seen[0].toTimestamp==int(END.timestamp()*1000)
    assert len(result['closed'])==1 and result['excluded_forming_count']==1
    assert result['closed'][0]['open']=='60.001'
    assert result['raw'][0]['protocol']['low']==6000000
    with pytest.raises(ValueError,match='unsupported'):
        collect_native(Client(),dict(symbol_id=7,digits=3),'H2')

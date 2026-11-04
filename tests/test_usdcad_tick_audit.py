"""Pure quote decoding, pagination and sequence proofs; no remote requests."""
from types import SimpleNamespace
import pytest
from reports.collect_usdcad_ticks import decode_page, collect_window, QuoteAuditClient
from reports.analyze_usdcad_ticks import target_sequence
from ctrader.framing import oa


def test_decode_keeps_integer_prices_zero_delta_and_protocol_ties():
    assert decode_page([dict(timestamp=1000,tick=123456),dict(timestamp=-10,tick=-6),dict(timestamp=0,tick=5)])==[(1000,123456),(990,123450),(990,123455)]
    with pytest.raises(ValueError,match='positive'):
        decode_page([dict(timestamp=1000,tick=10),dict(timestamp=10,tick=11)])


def test_has_more_bisection_never_drops_same_ms_quotes():
    class Fake:
        account_id=1
        def _hist_request(self,msg):
            lo,hi=msg.fromTimestamp,msg.toTimestamp
            rows=[(2,10),(2,11),(8,12)]
            chosen=[(t,p) for t,p in rows if lo<=t<=hi]
            if lo==0 and hi==9:chosen=[(8,12)];more=True
            else:more=False
            chosen=sorted(chosen,key=lambda t:t[0],reverse=True)
            prev=None;previous_price=None;encoded=[]
            for at,price in chosen:
                encoded.append(SimpleNamespace(timestamp=at if prev is None else at-prev,tick=price if previous_price is None else price-previous_price));prev=at;previous_price=price
            return SimpleNamespace(tickData=encoded,hasMore=more)
    rows,complete=collect_window(Fake(),9,'BID',0,9,[],[10])
    assert complete and sorted(rows)==[(2,10),(2,11),(8,12)]


def test_saturated_single_ms_stays_incomplete():
    class Fake:
        account_id=1
        def _hist_request(self,msg):return SimpleNamespace(tickData=[SimpleNamespace(timestamp=2,tick=10)],hasMore=True)
    assert collect_window(Fake(),9,'BID',2,2,[],[1])==([],False)


def test_quote_client_still_blocks_orders_refresh_and_settings_writes():
    client=QuoteAuditClient(settings=SimpleNamespace(get=lambda *a:None))
    with pytest.raises(RuntimeError):client.request(oa.ProtoOANewOrderReq())
    with pytest.raises(RuntimeError):client._refresh()
    with pytest.raises(RuntimeError):client.settings.set('x','y')


@pytest.mark.parametrize('rows,status',[
    ([(1,80),(2,100),(3,79)],'TARGET_AFTER_ENTRY'),
    ([(1,80),(2,100),(2,79)],'UNRESOLVED_SAME_MS_ORDERING'),
    ([(1,80),(2,100),(3,90)],'FILLED_WITHOUT_EXIT_IN_MINUTE'),
    ([(1,80),(2,90)],'NO_ENTRY_IN_MINUTE'),
])
def test_target_before_fill_is_not_counted_and_ties_stay_unknown(rows,status):
    assert target_sequence(dict(side='SELL',entry_ticks=100,stop_ticks=110,target_ticks=80),rows)['status']==status

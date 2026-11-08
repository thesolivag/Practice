from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import pytest
from bishop.v2.types import Instrument,Bar,Order,Clock,jsonable
from bishop.v2.simulation import simulate,Costs
from slk.bishop_unknown_jobs import refine,validate_minutes,collect
from slk import bishop_year_replay as Y

T=datetime(2026,1,5,tzinfo=timezone.utc)
I=Instrument('TEST','1','1','24x7_utc_v1',price_basis='BID',venue='ctrader')

def bar(at,o,h,l,c,tf='H1'):
    end=at+timedelta(minutes=1 if tf=='M1' else 60)
    return Bar('TEST',tf,at,end,o,h,l,c,end,I.source_id)

def fixture(path):
    # Fill minute is unambiguous. A later minute reaches TP or SL.
    minute=[bar(T,105,106,99,102,'M1')]
    for n in range(1,60):
        o,h,l,c=path[n-1] if n-1<len(path) else (105,105,105,105)
        minute.append(bar(T+timedelta(minutes=n),o,h,l,c,'M1'))
    coarse=bar(T,105,max(b.high_ticks for b in minute),min(b.low_ticks for b in minute),minute[-1].close_ticks)
    order=Order(id='order',setup_id='setup',instrument='TEST',tf='H1',model='confirmation_bo',side='BUY',kind='LIMIT',clock=Clock(T,T,T),entry_ticks=100,stop_ticks=90,target_ticks=110)
    end=T+timedelta(hours=1)
    obs=jsonable(simulate((order,),(coarse,),I,Costs(),end)['observations'][0])
    assert obs['outcome']=='CENSORED'
    row={'order':jsonable(order),'actions':[],'mode':'standalone','observation':obs}
    return row,{'instrument':I,'bars':(coarse,)},end,tuple(minute)

@pytest.mark.parametrize('path,outcome',[
    ([(102,111,101,110),(105,106,89,95)],'WIN'),
    ([(102,104,89,95),(105,111,104,110)],'LOSS'),
])
def test_minute_order_decides_first_exit_without_mutating_signal(path,outcome):
    row,feed,end,minute=fixture(path);before=deepcopy(row)
    result=refine(row,feed,end,lambda h:minute)
    assert result['status']=='RESOLVED'
    assert result['observation']['outcome']==outcome
    assert row==before and result['order']==before['order']
    assert result['actions']==before['actions']


def test_same_minute_collision_stays_unknown():
    row,feed,end,minute=fixture([(102,111,89,105)])
    result=refine(row,feed,end,lambda h:minute)
    assert result['reason']=='STILL_AMBIGUOUS_WITHIN_ONE_MINUTE'
    assert result['observation']==row['observation']


def test_strict_minutes_require_coverage_and_matching_original_prices():
    row,feed,end,minute=fixture([(102,111,101,110)])
    rows=[(int(b.start.timestamp()),b.open_ticks,b.high_ticks,b.low_ticks,b.close_ticks) for b in minute]
    assert len(validate_minutes(feed['bars'][0],rows,I))==60
    with pytest.raises(ValueError,match='MISSING_OR_DUPLICATE'):
        validate_minutes(feed['bars'][0],rows[:-1],I)
    altered=list(rows);altered[1]=(*altered[1][:2],120,*altered[1][3:])
    with pytest.raises(ValueError,match='M1_H1_PRICE_MISMATCH'):
        validate_minutes(feed['bars'][0],altered,I)
    with pytest.raises(ValueError,match='MISSING_OR_DUPLICATE'):
        validate_minutes(feed['bars'][0],rows+[rows[0]],I)


def test_original_reproduction_required_and_future_candles_ignored():
    row,feed,end,minute=fixture([(102,111,101,110)])
    feed['bars']+=(bar(end,105,1000,1,105),)
    assert refine(row,feed,end,lambda h:minute)['observation']['outcome']=='WIN'
    row['observation']['fill_ticks']='101'
    assert refine(row,feed,end,lambda h:minute)['reason']=='ORIGINAL_EXECUTION_NOT_REPRODUCED'


def test_download_failure_preserves_unknown_and_redacts_exception():
    row,feed,end,minute=fixture([(102,111,101,110)])
    def unavailable(h):raise RuntimeError('sensitive connection details')
    result=refine(row,feed,end,unavailable)
    assert result['reason']=='BROKER_FETCH_UNAVAILABLE'
    assert 'sensitive' not in str(result)


def test_report_keeps_original_results_and_missing_markets(tmp_path):
    Y.dump(tmp_path/'original-report/REPORT.json',{'completed':['A','B'],
        'matched_comparison_markets':['A','B'],'combined_matched_markets':{'standalone':{'total_R':4}}})
    Y.dump(tmp_path/'unknown-A/summary.json',{'pair':'A','reasons':{},'models':{'standalone':{
        'original_unknown':2,'new_outcomes':{'WIN':1,'CENSORED':1},'resolved_gross_R':1}}})
    collect(tmp_path,tmp_path/'out');r=Y.load(tmp_path/'out/REPORT.json')
    assert r['status']=='PARTIAL' and r['missing_markets']==['B']
    assert r['original_matched_results']['standalone']['total_R']==4
    assert r['unknown_refinement']['standalone']['new_outcomes']['CENSORED']==1


def test_missing_later_pending_management_is_not_invented():
    row,feed,end,minute=fixture([(102,111,101,110)])
    # Exercise the fail-closed branch: a refinement that does not prove a fill
    # must not turn the absence of recorded later cancellations into a trade.
    flat=tuple(bar(T+timedelta(minutes=n),105,106,104,105,'M1') for n in range(60))
    result=refine(row,feed,end,lambda h:flat)
    assert result['reason']=='PENDING_MANAGEMENT_AFTER_ORIGINAL_CENSOR_UNAVAILABLE'
    assert result['observation']==row['observation']


def test_hour_budget_cannot_guess_a_result():
    row,feed,end,minute=fixture([(102,111,101,110)])
    result=refine(row,feed,end,lambda h:minute,max_hours=0)
    assert result['reason']=='REFINEMENT_HOUR_BUDGET'
    assert result['status']=='UNRESOLVED'

from datetime import datetime,timedelta,timezone
from types import SimpleNamespace as NS
from slk.bishop_paper import confirmed_web_biases,web_bias_gate
from bishop.v2.types import Event,Clock
T=datetime(2026,11,5,tzinfo=timezone.utc)

def bias(**kw):
    return dict(id=1,pair='EURUSD',story='D',side='BUY',status='CONFIRMED',confirm_time=T,no_trade=0,target=1.2,**kw)

def test_latest_ended_does_not_resurrect_old_confirmed_and_preferences_apply():
    vals={'stories':['D','W'],'avoid_pairs':[]}
    old=bias();new={**old,'id':2,'status':'INVALIDATED'}
    assert confirmed_web_biases([new,old],vals,T)==[]
    assert confirmed_web_biases([old],{**vals,'avoid_pairs':['EURUSD']},T)==[]
    assert confirmed_web_biases([old],vals,T-timedelta(seconds=1))==[]
    assert confirmed_web_biases([old],vals,T)[0]['id']==1

def fixture():
    setup=NS(id='setup',instrument='EURUSD',side='BUY',available_at=T+timedelta(hours=8),evidence_ids=('h4',))
    event=Event(id='h4',kind='BOS',instrument='EURUSD',tf='H4',side='BUY',clock=Clock(T+timedelta(hours=4),T+timedelta(hours=4),T+timedelta(hours=4)))
    b={'id':1,'pair':'EURUSD','side':'BUY','timeframe':'D','confirmed_at':T.isoformat()}
    return setup,event,b

def test_requires_confirmed_same_side_bias_then_linked_h4():
    s,e,b=fixture();proofs={};st={'H4':NS(events=(e,))}
    assert web_bias_gate([],proofs)(s,st)=='WEB_BIAS_MISSING_OR_NOT_YET_CONFIRMED'
    assert web_bias_gate([{**b,'side':'SELL'}],proofs)(s,st)=='WEB_BIAS_DIRECTION_CONFLICT'
    assert web_bias_gate([{**b,'confirmed_at':(T+timedelta(hours=5)).isoformat()}],proofs)(s,st)=='WEB_BIAS_REQUIRES_SUBSEQUENT_H4_SEQUENCE'
    assert web_bias_gate([b],proofs)(s,{'H4':NS(events=())})=='WEB_BIAS_REQUIRES_SUBSEQUENT_H4_SEQUENCE'
    assert web_bias_gate([b],proofs)(s,st) is None
    assert proofs['setup']['bias']['id']==1 and proofs['setup']['h4_sponsor']['id']=='h4'
    assert web_bias_gate([b,{**b,'id':2,'side':'SELL','timeframe':'W'}],{})(s,st)=='WEB_BIAS_DIRECTION_CONFLICT'

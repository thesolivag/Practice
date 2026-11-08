from datetime import datetime,timedelta,timezone
import pytest
from bishop.v2.types import Instrument,Bar,Order,Clock
from bishop.v2.simulation import Costs,simulate as original
from bishop.v2.research_stop_simulation import simulate
T=datetime(2026,1,5,tzinfo=timezone.utc)
I=Instrument('TEST','1','1','24x7_utc_v1')

def case(side='BUY',tf='M1',op=105,hi=106,lo=89,cl=95,costs=None):
    if side=='SELL':op,hi,lo,cl=200-op,200-lo,200-hi,200-cl
    end=T+timedelta(minutes=1 if tf=='M1' else 60)
    o=Order(id='o',setup_id='s',instrument='TEST',tf='H1',model='confirmation_bo',side=side,kind='LIMIT',clock=Clock(T,T,T),entry_ticks=100,stop_ticks=90 if side=='BUY' else 110,target_ticks=110 if side=='BUY' else 90)
    b=Bar('TEST',tf,T,end,op,hi,lo,cl,end,I.source_id)
    args=((o,),(b,),I,{k:str(getattr(costs or Costs(),k)) for k in Costs.__dataclass_fields__},end)
    return original(*args)['observations'][0],simulate(*args)['observations'][0]

@pytest.mark.parametrize('side',['BUY','SELL'])
@pytest.mark.parametrize('op',[105,99])
def test_proven_adverse_stop(side,op):
    old,new=case(side=side,op=op)
    assert old['outcome']=='CENSORED'
    assert new['outcome']=='LOSS' and new['net_r']=='-1'

@pytest.mark.parametrize('kwargs',[{'hi':111},{'op':89},{'op':90},{'tf':'H1'},{'costs':Costs(spread_ticks=1)}])
@pytest.mark.parametrize('side',['BUY','SELL'])
def test_ambiguous_or_out_of_scope_stays_unknown(kwargs,side):
    old,new=case(side=side,**kwargs)
    assert old['outcome']==new['outcome']=='CENSORED'

def test_entry_target_ordering_not_assumed():
    old,new=case(hi=111,lo=99,cl=102)
    assert old['outcome']==new['outcome']=='CENSORED'

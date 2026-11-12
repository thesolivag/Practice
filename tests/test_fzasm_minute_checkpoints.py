import numpy as np
import pytest
from fzasm.minute_cache import prepare

class Client:
 def __init__(self,fail_call=None):self.calls=[];self.fail_call=fail_call
 def symbol(self,pair):return {'pip_position':4,'digits':5}
 def trendbar_rows(self,pair,tf,lo,hi):
  self.calls.append((lo,hi))
  if len(self.calls)==self.fail_call:raise RuntimeError('temporary provider outage')
  return [[t,1.,1.1,.9,1.] for t in range(lo,hi,60)]


def test_four_hour_checkpoint_resumes_and_respects_fixed_cutoff(tmp_path):
 c=Client(fail_call=2)
 with pytest.raises(RuntimeError):prepare('EURUSD',2026,tmp_path,c,as_of='2026-01-01T08:00:00Z')
 assert len(list((tmp_path/'chunks/EURUSD').glob('*.npz')))==1
 retry=Client();prepare('EURUSD',2026,tmp_path,retry,as_of='2026-01-01T08:00:00Z')
 assert len(retry.calls)==1 and retry.calls[0]==c.calls[1]
 with np.load(tmp_path/'EURUSD_M1.npz') as z:
  assert len(z['time'])==480 and max(z['time'])==retry.calls[-1][1]-60


def test_empty_responses_are_not_permanent_checkpoints(tmp_path):
 c=Client();c.trendbar_rows=lambda *args:[]
 with pytest.raises(RuntimeError,match='No M1'):prepare('EURUSD',2026,tmp_path,c,as_of='2026-01-01T04:00:00Z')
 assert not list((tmp_path/'chunks/EURUSD').glob('*.npz'))


def test_month_with_empty_window_is_not_marked_complete(tmp_path):
 c=Client()
 original=c.trendbar_rows
 def data(pair,tf,lo,hi):
  rows=original(pair,tf,lo,hi)
  return [] if len(c.calls)==1 else rows
 c.trendbar_rows=data
 prepare('EURUSD',2026,tmp_path,c,as_of='2026-02-01T00:00:00Z')
 with np.load(tmp_path/'EURUSD_M1_2026_01.npz') as z:assert not bool(z['complete'])
 retry=Client();prepare('EURUSD',2026,tmp_path,retry,as_of='2026-02-01T00:00:00Z')
 assert len(retry.calls)==1 and retry.calls[0]==c.calls[0]
 with np.load(tmp_path/'EURUSD_M1_2026_01.npz') as z:assert bool(z['complete'])

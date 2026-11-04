import pytest
from slk.jobs import feed_lock


@pytest.mark.parametrize('available',[0,1])
def test_advisory_lock_released_and_connection_closed_on_failure(available):
    events=[]
    class Connection:
        def cursor(self):return self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,args):events.append(sql)
        def fetchone(self):return {'ok':available}
        def close(self):events.append('close')
    class DB:
        def connect(self):return Connection()
    with pytest.raises(RuntimeError):
        with feed_lock(DB(),0) as acquired:
            assert acquired==bool(available)
            raise RuntimeError('worker failed')
    assert events[-1]=='close'
    assert any('RELEASE_LOCK' in sql for sql in events)==bool(available)

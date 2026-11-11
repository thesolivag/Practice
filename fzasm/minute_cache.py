"""Explicit read-only historical cTrader M1 preparation for GitHub research runs.

Requests at most four hours (240 bars) at once. Completed months are checkpointed;
no H1 interpolation or provider mixing. Never sends broker orders.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd


def prepare(pair, year, root='data/store', client=None):
    from . import instruments
    root = Path(root); root.mkdir(parents=True,exist_ok=True)
    own = client is None
    if own:
        from slk.store import _open_client
        client = _open_client()
    try:
        info = client.symbol(pair)
        instruments.register(pair,info.get('pip_position'),info.get('digits'))
        months=[]
        end_year = min(pd.Timestamp(year=year+1,month=1,day=1,tz='UTC'),pd.Timestamp.now(tz='UTC').floor('min'))
        for month in range(1,13):
            start=pd.Timestamp(year=year,month=month,day=1,tz='UTC')
            if start>=end_year:
                break
            end=min(start+pd.offsets.MonthBegin(1),end_year)
            path=root/f'{pair}_M1_{year}_{month:02}.npz'
            cached = False
            if path.exists():
                with np.load(path) as z:
                    if 'complete' in z and bool(z['complete']):
                        rows=z['rows']
                        cached=True
            if not cached:
                rows=[]
                for lo in pd.date_range(start,end,freq='4h',inclusive='left'):
                    hi=min(lo+pd.Timedelta(hours=4),end)
                    # Only skip windows wholly inside the NY FX weekend.
                    hours=pd.date_range(lo,hi,freq='h',inclusive='left').tz_convert('America/New_York')
                    closed=[d.dayofweek==5 or (d.dayofweek==4 and d.hour>=17) or (d.dayofweek==6 and d.hour<17) for d in hours]
                    if hours.size and all(closed):
                        continue
                    batch=client.trendbar_rows(pair,'M1',int(lo.timestamp()),int(hi.timestamp()))
                    rows.extend(r[:5] for r in batch if lo.timestamp()<=r[0]<hi.timestamp() and r[0]%60==0)
                rows=np.asarray(rows,dtype=float).reshape(-1,5)
                if not len(rows):
                    raise RuntimeError(f'No M1 bars for {pair} {year}-{month:02}; refusing an empty-month success')
                np.savez_compressed(path,rows=rows,complete=(end==start+pd.offsets.MonthBegin(1)))
            months.append(rows)
        if not months:
            raise ValueError('Requested period has no historical data')
        rows=np.concatenate(months)
        rows=rows[np.argsort(rows[:,0])]
        if len(np.unique(rows[:,0]))!=len(rows):
            raise ValueError('Duplicate M1 timestamps')
        np.savez_compressed(root/f'{pair}_M1.npz',time=rows[:,0].astype('int64'),
                            **{k:rows[:,i+1] for i,k in enumerate(('open','high','low','close'))})
        (root/f'{pair}_M1.metadata.json').write_text(json.dumps({
            'source':'ctrader','price_side':'bid','year':year,'pip_position':info.get('pip_position'),
            'digits':info.get('digits'),'generated_at':pd.Timestamp.now(tz='UTC').isoformat()},indent=2))
    finally:
        if own:
            client.close()

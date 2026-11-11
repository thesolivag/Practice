"""Read-only bounded market-data collection for the user NZDJPY chart audit."""
from pathlib import Path
import base64,gzip,hashlib,json
import pandas as pd
from slk.store import _open_client
out=Path('reports/nzdjpy-reference');out.mkdir(parents=True,exist_ok=True)
start=pd.Timestamp('2026-11-10T00:00:00Z');end=pd.Timestamp('2026-11-11T10:00:00Z')
client=_open_client()
try:
 info=client.symbol('NZDJPY');rows=[]
 for lo in pd.date_range(start,end,freq='4h',inclusive='left'):
  hi=min(lo+pd.Timedelta(hours=4),end)
  rows.extend(r[:5] for r in client.trendbar_rows('NZDJPY','M1',int(lo.timestamp()),int(hi.timestamp())) if lo.timestamp()<=r[0]<hi.timestamp())
finally:
 client.close()
df=pd.DataFrame(rows,columns=['time','open','high','low','close']).sort_values('time')
if df.empty or df.time.duplicated().any():raise RuntimeError('Empty or duplicate market data')
df['time']=pd.to_datetime(df.time,unit='s',utc=True)
raw=df.to_csv(index=False).encode();(out/'NZDJPY_M1.csv').write_bytes(raw)
meta={'symbol':'NZDJPY','provider':'IC Markets cTrader','price_side':'bid','reference_provider':'FOREX.com','requested_start':str(start),'requested_end':str(end),'rows':len(df),'sha256':hashlib.sha256(raw).hexdigest(),'pip_position':info.get('pip_position'),'digits':info.get('digits'),'utc':True}
(out/'metadata.json').write_text(json.dumps(meta,indent=2))
print('REFERENCE_METADATA='+json.dumps(meta))
# Market prices only, compressed for connector retrieval; never credentials.
b64=base64.b64encode(gzip.compress(raw)).decode()
for i in range(0,len(b64),3000):print('REFERENCE_DATA='+b64[i:i+3000])

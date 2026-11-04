"""Read-only broker candle-boundary comparison; prints public market timestamps only."""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd
from ctrader.client import CTraderClient
from ctrader import tokens
from slk import candles, db, jobs


def main():
    now=datetime.now(timezone.utc)
    report={'checked_at':now.isoformat(),'symbols':{}}
    with jobs.feed_lock(db,0,name='slk_personal_feed') as acquired:
        if not acquired:raise RuntimeError('Broker feed busy; retry audit later')
        with CTraderClient(settings=tokens.default_settings(strict=True)) as client:
            client.timeout=12
            client.get_symbols(['EURUSD','XAUUSD','XAGUSD'])
            for pair in ['EURUSD','XAUUSD','XAGUSD']:
                bars=client.trendbar_rows(pair,'H4',now-timedelta(days=10),now)
                dates={}
                for row in bars:
                    opened=datetime.fromtimestamp(row[0],timezone.utc)
                    if opened+timedelta(hours=4)>now:continue
                    with candles.market(pair):
                        wall=candles.wall_time(pd.DatetimeIndex([opened]))[0]
                    bucket=(wall.floor('4h')-pd.Timedelta(hours=7)).tz_localize('America/New_York').tz_convert('UTC')
                    wat=opened.astimezone(ZoneInfo('Africa/Lagos'))
                    dates.setdefault(wat.date().isoformat(),[]).append({'broker_open_wat':wat.strftime('%H:%M'), 'broker_open_utc':opened.isoformat(),'current_bucket_open_wat':bucket.tz_convert('Africa/Lagos').strftime('%H:%M'),'aligned':opened.timestamp()==bucket.timestamp()})
                report['symbols'][pair]={'broker_symbol':client.symbol(pair)['name'],'days':dates}
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

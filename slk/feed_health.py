"""Read-only cached/broker candle freshness report. No alerts or orders."""
import json
from datetime import datetime,timedelta,timezone


def describe(pair,source,frame,now):
    closed=frame[frame.index+timedelta(hours=1)<=now]
    last=None if closed.empty else closed.index[-1]
    monday=now-timedelta(days=now.weekday())
    monday=monday.replace(hour=0,minute=0,second=0,microsecond=0)
    return {'pair':pair,'source':source,'closed_h1_count':len(closed),
            'latest_h1_open':None if last is None else last.isoformat(),
            'latest_h1_close':None if last is None else (last+timedelta(hours=1)).isoformat(),
            'lag_hours':None if last is None else round((now-last-timedelta(hours=1)).total_seconds()/3600,2),
            'bars_since_monday_utc':int((closed.index>=monday).sum())}


def main():
    from . import db,store,settings
    from ctrader.client import CTraderClient
    now=datetime.now(timezone.utc)
    pairs=('EURUSD','GBPUSD','USDJPY')
    print(json.dumps({'as_of_utc':now.isoformat(),'purpose':'freshness only; no orders or Telegram calls'}),flush=True)
    vals=settings.load(db.get_settings())
    print(json.dumps({'watchlist_size':len(vals['pairs']),
                     'selected_probes':{pair:pair in vals['pairs'] for pair in pairs},
                     'alert_settings':{k:vals[k] for k in ('alert_entry','early_breakout_alert','daily_summary','alert_tapped','alert_breakout','alert_confirmed','alert_continuation') if k in vals}}),flush=True)
    for pair in pairs:
        cached=store.Pair(pair)
        print(json.dumps(describe(pair,'cached:'+str(cached.src),cached.frame(),now)),flush=True)
    with CTraderClient() as client:
        for pair in pairs:
            try:
                frame=client.get_trendbars(pair,'H1',now-timedelta(days=6),now)
                print(json.dumps(describe(pair,'direct:ctrader',frame,now)),flush=True)
            except Exception as exc:
                # Avoid broker exception text that can include auth/account details.
                print(json.dumps({'pair':pair,'source':'direct:ctrader','error_type':type(exc).__name__}),flush=True)


if __name__=='__main__':main()

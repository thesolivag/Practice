"""
FZ-ASM Historical Data Loader and Resampler.
Supports local CSV cache, IC Markets cTrader Open API, and Dukascopy.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
import numpy as np
import pandas as pd

from .types import Candle, TimeFrame


def load_candles_df(pair: str, start_year: int, end_year: int, cache_dir: str = "data") -> pd.DataFrame:
    """
    Loads hourly OHLC dataframe for `pair` between `start_year` and `end_year`.
    Checks:
      1. data/store/{pair}_H1.npz
      2. data/examples/{pair}_H1.csv.gz
      3. data/debug/{pair}_H1_ctrader.csv.gz
      4. data/{pair}_H1.csv.gz
      5. cTrader Open API via slk.store (if credentials present)
    """
    clean_pair = pair.upper().replace("/", "").replace("_", "").replace("-", "").strip()

    # 1. Check local files first
    candidates = [
        os.path.join(cache_dir, "store", f"{clean_pair}_H1.npz"),
        os.path.join(cache_dir, "examples", f"{clean_pair}_H1.csv.gz"),
        os.path.join(cache_dir, "debug", f"{clean_pair}_H1_ctrader.csv.gz"),
        os.path.join(cache_dir, f"{clean_pair}_H1.csv.gz"),
        os.path.join("data", "examples", f"{clean_pair}_H1.csv.gz"),
        os.path.join("data", "debug", f"{clean_pair}_H1_ctrader.csv.gz"),
        os.path.join("data", f"{clean_pair}_H1.csv.gz"),
    ]

    for p in candidates:
        if os.path.exists(p):
            if p.endswith(".npz"):
                try:
                    npz = np.load(p)
                    ts = pd.to_datetime(npz["time"], unit="s", utc=True)
                    df = pd.DataFrame({
                        "open": npz["open"],
                        "high": npz["high"],
                        "low": npz["low"],
                        "close": npz["close"]
                    }, index=ts)
                    mask = (df.index.year >= start_year) & (df.index.year <= end_year)
                    if mask.any():
                        return df[mask].sort_index()
                except Exception as e:
                    print(f"Error loading {p}: {e}")
            else:
                try:
                    df = pd.read_csv(p, index_col=0, parse_dates=True)
                    if df.index.tz is None:
                        df.index = df.index.tz_localize("UTC")
                    else:
                        df.index = df.index.tz_convert("UTC")
                    mask = (df.index.year >= start_year) & (df.index.year <= end_year)
                    if mask.any():
                        return df[mask].sort_index()
                except Exception as e:
                    print(f"Error loading {p}: {e}")

    # 2. Try cTrader / slk.store
    try:
        from slk import store
        df = store.hourly(clean_pair, start_year, end_year)
        if df is not None and not df.empty:
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            return df[(df.index.year >= start_year) & (df.index.year <= end_year)].sort_index()
    except Exception as e:
        print(f"cTrader store fetch for {clean_pair} ({start_year}-{end_year}) gave: {e}")

    raise FileNotFoundError(f"Could not load historical candles for {clean_pair} ({start_year}-{end_year}).")


def df_to_candles(df: pd.DataFrame, timeframe: TimeFrame) -> List[Candle]:
    """Converts a pandas OHLC DataFrame to a List[Candle]."""
    candles = []
    for ts, row in df.iterrows():
        candles.append(Candle(
            timestamp=ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            close_time=row.get("close_time"),
            timeframe=timeframe
        ))
    return candles


def resample_ohlc(df: pd.DataFrame, rule: str, source_minutes: int = 1,
                  calendar_timezone: str = "UTC") -> pd.DataFrame:
    """Start-labelled bars; require every source interval. Availability is bar close.

    Anchor in the explicitly configured data-provider timezone, including its DST.
    UTC is an explicit research calendar, not a claim about a broker's daily close.
    """
    if df.index.has_duplicates or not df.index.is_monotonic_increasing:
        raise ValueError("OHLC timestamps must be unique and ordered")
    local = df.tz_convert(calendar_timezone)
    groups = local.resample(rule, label="left", closed="left")
    out = groups.agg({"open":"first", "high":"max", "low":"min", "close":"last"})
    # For DST daily bars, derive each bin's actual duration rather than assume 24h.
    edges = pd.date_range(out.index[0], periods=len(out)+1, freq=rule) if len(out) else []
    expected = pd.Series([(edges[i+1]-edges[i]).total_seconds()/60/source_minutes
                          for i in range(len(out))], index=out.index)
    out["close_time"] = [edges[i+1].tz_convert("UTC") for i in range(len(out))]
    out = out[groups.close.count().eq(expected)].dropna()
    return out.tz_convert("UTC")


def load_minute_df(pair: str, start_year: int, end_year: int, cache_dir: str = "data") -> pd.DataFrame:
    """Load real M1 inputs; never synthesize intrabar prices from H1.

    Input timestamps are UTC bar opens. Missing data is a failed run, not zero trades.
    """
    clean = pair.upper().replace("/", "")
    paths = [os.path.join(cache_dir, "store", f"{clean}_M1.npz"),
             os.path.join(cache_dir, f"{clean}_M1.csv.gz")]
    for path in paths:
        if not os.path.exists(path):
            continue
        if path.endswith("npz"):
            with np.load(path) as z:
                df = pd.DataFrame({k:z[k] for k in ("open","high","low","close")},
                                  index=pd.to_datetime(z["time"], unit="s", utc=True))
        else:
            df = pd.read_csv(path, index_col=0)
            df.index = pd.to_datetime(df.index, utc=True)
        df = df[(df.index.year >= start_year) & (df.index.year <= end_year)].sort_index()
        if df.empty:
            continue
        if df.index.has_duplicates or (df.index.second != 0).any():
            raise ValueError(f"Invalid M1 timestamps: {path}")
        values = df[["open","high","low","close"]]
        if not np.isfinite(values.to_numpy()).all() or (df.low > values.min(axis=1)).any() or (df.high < values.max(axis=1)).any():
            raise ValueError(f"Invalid M1 OHLC: {path}")
        import json
        metadata = os.path.join(cache_dir,"store",f"{clean}_M1.metadata.json")
        if os.path.exists(metadata):
            from . import instruments
            meta = json.loads(open(metadata).read())
            instruments.register(clean,meta.get("pip_position"),meta.get("digits"))
        df.attrs["source"] = path
        return df
    raise FileNotFoundError(f"Real M1 data required for {clean}; provide data/store/{clean}_M1.npz or data/{clean}_M1.csv.gz. H1 fallback is disabled.")

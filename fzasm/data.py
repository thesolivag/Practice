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
            timeframe=timeframe
        ))
    return candles


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resamples an OHLC DataFrame by rule ('2h', '4h', '1D')."""
    resampled = df.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last"
    }).dropna()
    return resampled


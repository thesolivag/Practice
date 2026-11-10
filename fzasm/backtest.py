"""
FZ-ASM Historical Backtest Engine.
Runs multi-timeframe strategy evaluation across historical candles (D1, H4, H2, H1).
Tracks pair-by-pair metrics and independently evaluates:
  1. FZ Target (TP1 at 50% Equilibrium, TP2 at HTF Map Target)
  2. Fixed 1R
  3. Fixed 2R
  4. Fixed 3R
  5. Fixed 4R
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from .types import Candle, TimeFrame, BiasDirection, TradeSetup, EntryModelType
from .engine import FZASMEngine
from .data import load_candles_df, df_to_candles, resample_ohlc
from . import instruments

DEFAULT_PAIRS = [
    # FZ Asian JPY Crosses + Gold
    "USDJPY", "GBPJPY", "EURJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY", "XAUUSD",
    # User-requested Majors
    "EURUSD", "GBPUSD"
]


class TradeOutcome:
    """Tracks independent outcomes for all 5 exit targets on a single trade."""
    def __init__(self, setup: TradeSetup, entry_bar_idx: int):
        self.setup = setup
        self.entry_bar_idx = entry_bar_idx
        self.symbol = setup.symbol
        self.direction = setup.bias
        self.entry_price = setup.entry_price
        self.stop_loss = setup.stop_loss
        self.unit_risk = abs(setup.entry_price - setup.stop_loss)
        
        # Targets
        # Targets
        self.fz_tp1 = setup.take_profit_1
        self.fz_tp2 = setup.take_profit_2
        # FZ Partials & Break-even tracking
        self.fz_tp1_hit: bool = False
        self.fz_tp1_banked: float = 0.0
        self.fz_sl: float = setup.stop_loss
        
        is_long = setup.bias == BiasDirection.BULLISH
        self.tp_1r = setup.entry_price + (1.0 * self.unit_risk if is_long else -1.0 * self.unit_risk)
        self.tp_2r = setup.entry_price + (2.0 * self.unit_risk if is_long else -2.0 * self.unit_risk)
        self.tp_3r = setup.entry_price + (3.0 * self.unit_risk if is_long else -3.0 * self.unit_risk)
        self.tp_4r = setup.entry_price + (4.0 * self.unit_risk if is_long else -4.0 * self.unit_risk)
        
        # Independent target results (R realized)
        self.fz_result_r: Optional[float] = None
        self.r1_result_r: Optional[float] = None
        self.r2_result_r: Optional[float] = None
        self.r3_result_r: Optional[float] = None
        self.r4_result_r: Optional[float] = None
        
        self.exit_time: Optional[datetime] = None
        self.bars_held: int = 0
        self.closed: bool = False

    def is_fully_evaluated(self) -> bool:
        return (
            self.fz_result_r is not None and
            self.r1_result_r is not None and
            self.r2_result_r is not None and
            self.r3_result_r is not None and
            self.r4_result_r is not None
        )

    def evaluate_bar(self, bar: Candle, bar_idx: int, max_bars: int = 120):
        if self.is_fully_evaluated():
            return
            
        self.bars_held += 1
        is_long = self.direction == BiasDirection.BULLISH
        
        # Check Stop Loss hit
        sl_hit = (bar.low <= self.stop_loss) if is_long else (bar.high >= self.stop_loss)
        
        # 1. FZ Target (TP1 = 50% Eq + Break-even, TP2 = HTF Map Target)
        if self.fz_result_r is None:
            tp2_hit = (bar.high >= self.fz_tp2) if is_long else (bar.low <= self.fz_tp2)
            tp1_hit = (bar.high >= self.fz_tp1) if is_long else (bar.low <= self.fz_tp1)
            
            if not self.fz_tp1_hit:
                if sl_hit and (tp1_hit or tp2_hit):
                    self.fz_result_r = -1.0
                elif sl_hit:
                    self.fz_result_r = -1.0
                elif tp2_hit:
                    r_achieved = abs(self.fz_tp2 - self.entry_price) / max(self.unit_risk, 1e-6)
                    self.fz_result_r = round(r_achieved, 2)
                elif tp1_hit:
                    r_tp1 = abs(self.fz_tp1 - self.entry_price) / max(self.unit_risk, 1e-6)
                    self.fz_tp1_banked = r_tp1 * 0.5
                    self.fz_tp1_hit = True
                    self.fz_sl = self.entry_price
            else:
                be_hit = (bar.low <= self.fz_sl) if is_long else (bar.high >= self.fz_sl)
                if tp2_hit:
                    r_tp2 = abs(self.fz_tp2 - self.entry_price) / max(self.unit_risk, 1e-6)
                    self.fz_result_r = round(self.fz_tp1_banked + 0.5 * r_tp2, 2)
                elif be_hit:
                    self.fz_result_r = round(self.fz_tp1_banked, 2)
                
        # 2. Fixed 1R
        if self.r1_result_r is None:
            tp1r_hit = (bar.high >= self.tp_1r) if is_long else (bar.low <= self.tp_1r)
            if sl_hit and tp1r_hit:
                self.r1_result_r = -1.0
            elif sl_hit:
                self.r1_result_r = -1.0
            elif tp1r_hit:
                self.r1_result_r = 1.0

        # 3. Fixed 2R
        if self.r2_result_r is None:
            tp2r_hit = (bar.high >= self.tp_2r) if is_long else (bar.low <= self.tp_2r)
            if sl_hit and tp2r_hit:
                self.r2_result_r = -1.0
            elif sl_hit:
                self.r2_result_r = -1.0
            elif tp2r_hit:
                self.r2_result_r = 2.0

        # 4. Fixed 3R
        if self.r3_result_r is None:
            tp3r_hit = (bar.high >= self.tp_3r) if is_long else (bar.low <= self.tp_3r)
            if sl_hit and tp3r_hit:
                self.r3_result_r = -1.0
            elif sl_hit:
                self.r3_result_r = -1.0
            elif tp3r_hit:
                self.r3_result_r = 3.0

        # 5. Fixed 4R
        if self.r4_result_r is None:
            tp4r_hit = (bar.high >= self.tp_4r) if is_long else (bar.low <= self.tp_4r)
            if sl_hit and tp4r_hit:
                self.r4_result_r = -1.0
            elif sl_hit:
                self.r4_result_r = -1.0
            elif tp4r_hit:
                self.r4_result_r = 4.0

        # Time-stop limit (120 hours / 5 days)
        if self.bars_held >= max_bars:
            if self.fz_result_r is None:
                if self.fz_tp1_hit:
                    self.fz_result_r = round(self.fz_tp1_banked, 2)
                else:
                    curr_r = (bar.close - self.entry_price if is_long else self.entry_price - bar.close) / max(self.unit_risk, 1e-6)
                    self.fz_result_r = round(max(-1.0, curr_r), 2)
            if self.r1_result_r is None: self.r1_result_r = -1.0 if sl_hit else 0.0
            if self.r2_result_r is None: self.r2_result_r = -1.0 if sl_hit else 0.0
            if self.r3_result_r is None: self.r3_result_r = -1.0 if sl_hit else 0.0
            if self.r4_result_r is None: self.r4_result_r = -1.0 if sl_hit else 0.0
            self.exit_time = bar.timestamp
            self.closed = True

        if self.is_fully_evaluated() and not self.closed:
            self.exit_time = bar.timestamp
            self.closed = True


def backtest_pair(pair: str, start_year: int, end_year: int, engine: FZASMEngine) -> List[TradeOutcome]:
    """Runs full-year backtest for one pair."""
    try:
        df_h1 = load_candles_df(pair, start_year, end_year)
    except Exception as e:
        print(f"[{pair}] Skipped: {e}", flush=True)
        return []

    if df_h1.empty or len(df_h1) < 200:
        print(f"[{pair}] Insufficient data: {len(df_h1)} candles", flush=True)
        return []

    print(f"[{pair}] Processing {len(df_h1)} H1 candles ({df_h1.index[0].date()} to {df_h1.index[-1].date()})...", flush=True)

    # Multi-timeframe resampling
    df_h2 = resample_ohlc(df_h1, "2h")
    df_h4 = resample_ohlc(df_h1, "4h")
    df_d1 = resample_ohlc(df_h1, "1D")

    h1_all = df_to_candles(df_h1, TimeFrame.H1)
    h2_all = df_to_candles(df_h2, TimeFrame.H2)
    h4_all = df_to_candles(df_h4, TimeFrame.H4)
    d1_all = df_to_candles(df_d1, TimeFrame.D1)

    # Map timestamps to index for fast lookup
    h1_by_time = {c.timestamp: i for i, c in enumerate(h1_all)}
    
    trades: List[TradeOutcome] = []
    active_trades: List[TradeOutcome] = []

    # Iterate through H1 candles
    for i, candle in enumerate(h1_all):
        # Update existing active trades
        for t in list(active_trades):
            t.evaluate_bar(candle, i)
            if t.closed:
                active_trades.remove(t)

        # We evaluate new trade setups during Asian Session Prime hours:
        # Specifically at 01:00 UTC (1:00 AM WAT) or 02:00 UTC (2:00 AM WAT)
        dt = candle.timestamp
        if dt.hour not in (1, 2):
            continue

        # Slice historical data up to current bar (strictly no lookahead)
        d1_slice = [c for c in d1_all if c.timestamp.date() < dt.date()]
        if len(d1_slice) < 5:
            continue

        h4_slice = [c for c in h4_all if c.timestamp <= dt]
        h2_slice = [c for c in h2_all if c.timestamp <= dt]
        h1_slice = h1_all[max(0, i - 24): i + 1]

        candles_by_tf = {
            "D1": d1_slice,
            "H4": h4_slice,
            "H2": h2_slice,
            "H1": h1_slice
        }

        setup = engine.scan_asset(
            symbol=pair,
            candles_by_tf=candles_by_tf,
            current_time=dt,
            force_session=True
        )

        if setup:
            outcome = TradeOutcome(setup, entry_bar_idx=i)
            trades.append(outcome)
            active_trades.append(outcome)

    # Close remaining trades at end of dataset
    for t in active_trades:
        if not t.closed:
            t.evaluate_bar(h1_all[-1], len(h1_all) - 1, max_bars=0)

    print(f"[{pair}] Completed: {len(trades)} setups generated.", flush=True)
    return trades


def compute_metrics(trades: List[TradeOutcome], target_attr: str) -> Dict[str, Any]:
    """Computes quantitative metrics for a specific target strategy."""
    if not trades:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "net_r": 0.0, "expectancy": 0.0, "profit_factor": 0.0, "max_dd_r": 0.0
        }

    results = [getattr(t, target_attr) for t in trades if getattr(t, target_attr) is not None]
    if not results:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "net_r": 0.0, "expectancy": 0.0, "profit_factor": 0.0, "max_dd_r": 0.0
        }

    n = len(results)
    wins = sum(1 for r in results if r > 0)
    losses = sum(1 for r in results if r < 0)
    win_rate = round(wins / n * 100, 1) if n > 0 else 0.0
    net_r = round(sum(results), 2)
    expectancy = round(net_r / n, 2) if n > 0 else 0.0

    gross_profit = sum(r for r in results if r > 0)
    gross_loss = abs(sum(r for r in results if r < 0))
    pf = round(gross_profit / max(gross_loss, 1e-6), 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    # Max Drawdown in R
    cum = np.cumsum([0.0] + results)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = round(float(np.max(dd)), 2)

    return {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "net_r": net_r,
        "expectancy": expectancy,
        "profit_factor": pf,
        "max_dd_r": max_dd
    }


def generate_report(all_trades: Dict[str, List[TradeOutcome]], year: int, out_dir: str = "reports") -> str:
    """Generates a comprehensive Markdown report and saves trades to CSV."""
    os.makedirs(out_dir, exist_ok=True)
    report_lines = []
    
    report_lines.append(f"# FZ-ASM Full-Year Strategy Backtest Report ({year})")
    report_lines.append(f"**Period:** {year}-01-01 to {year}-12-31  ")
    report_lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ")
    report_lines.append(f"**Scope:** All Asian JPY Crosses + Gold (`XAUUSD`) + Major Pairs (`EURUSD`, `GBPUSD`)  \n")
    report_lines.append("---\n")

    # 1. Executive Summary Table (Target Comparison)
    flat_trades = [t for pair_trades in all_trades.values() for t in pair_trades]
    targets = [
        ("FZ Dynamic Target (TP1 50% Eq + TP2 HTF Target)", "fz_result_r"),
        ("Fixed 1R", "r1_result_r"),
        ("Fixed 2R", "r2_result_r"),
        ("Fixed 3R", "r3_result_r"),
        ("Fixed 4R", "r4_result_r"),
    ]

    report_lines.append("## 1. Overall Target Strategy Performance Comparison")
    report_lines.append("| Strategy Target | Trades | Wins | Losses | Win Rate | Net Return (R) | Expectancy (R) | Profit Factor | Max DD (R) |")
    report_lines.append("|---|---|---|---|---|---|---|---|---|")

    for label, attr in targets:
        m = compute_metrics(flat_trades, attr)
        report_lines.append(
            f"| **{label}** | {m['trades']} | {m['wins']} | {m['losses']} | "
            f"{m['win_rate']}% | **{m['net_r']:+0.1f}R** | {m['expectancy']:+0.2f}R | "
            f"{m['profit_factor']} | {m['max_dd_r']}R |"
        )
    report_lines.append("\n---\n")

    # 2. Pair-by-Pair Breakdown
    report_lines.append("## 2. Pair-by-Pair Detailed Performance")
    report_lines.append("| Pair | Category | Setups | FZ Net R (Win%) | 1R Net R (Win%) | 2R Net R (Win%) | 3R Net R (Win%) | 4R Net R (Win%) |")
    report_lines.append("|---|---|---|---|---|---|---|---|")

    major_fz = {"USDJPY", "GBPJPY", "EURJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY", "XAUUSD"}

    for pair, p_trades in all_trades.items():
        cat = "FZ Core Asian" if pair in major_fz else "User Major"
        fz_m = compute_metrics(p_trades, "fz_result_r")
        r1_m = compute_metrics(p_trades, "r1_result_r")
        r2_m = compute_metrics(p_trades, "r2_result_r")
        r3_m = compute_metrics(p_trades, "r3_result_r")
        r4_m = compute_metrics(p_trades, "r4_result_r")

        report_lines.append(
            f"| **{pair}** | {cat} | {len(p_trades)} | "
            f"**{fz_m['net_r']:+0.1f}R** ({fz_m['win_rate']}%) | "
            f"{r1_m['net_r']:+0.1f}R ({r1_m['win_rate']}%) | "
            f"{r2_m['net_r']:+0.1f}R ({r2_m['win_rate']}%) | "
            f"{r3_m['net_r']:+0.1f}R ({r3_m['win_rate']}%) | "
            f"{r4_m['net_r']:+0.1f}R ({r4_m['win_rate']}%) |"
        )
    report_lines.append("\n---\n")

    # 3. Execution Model Breakdown
    report_lines.append("## 3. Performance by Entry Model")
    report_lines.append("| Entry Model | Setups | FZ Win Rate | FZ Net R | 2R Net R | 3R Net R |")
    report_lines.append("|---|---|---|---|---|---|")
    for model_type in [EntryModelType.MODEL_A_CHOCH_RETEST, EntryModelType.MODEL_B_INDUCEMENT_LIMIT]:
        m_trades = [t for t in flat_trades if t.setup.entry_model == model_type]
        m_fz = compute_metrics(m_trades, "fz_result_r")
        m_r2 = compute_metrics(m_trades, "r2_result_r")
        m_r3 = compute_metrics(m_trades, "r3_result_r")
        report_lines.append(
            f"| **{model_type.value}** | {len(m_trades)} | {m_fz['win_rate']}% | "
            f"{m_fz['net_r']:+0.1f}R | {m_r2['net_r']:+0.1f}R | {m_r3['net_r']:+0.1f}R |"
        )
    report_lines.append("\n---\n")

    # 4. Save Trades to CSV
    csv_rows = []
    for t in flat_trades:
        s = t.setup
        pip_unit = instruments.static(s.symbol)[0]
        risk_pips = round(abs(s.entry_price - s.stop_loss) / max(pip_unit, 1e-6), 1)
        csv_rows.append({
            "timestamp": s.timestamp.isoformat(),
            "symbol": s.symbol,
            "direction": s.bias.value,
            "entry_model": s.entry_model.value,
            "map_type": s.daily_map.map_type.value,
            "entry_price": s.entry_price,
            "stop_loss": s.stop_loss,
            "risk_pips": risk_pips,
            "fz_tp1": t.fz_tp1,
            "fz_tp2": t.fz_tp2,
            "fz_result_r": t.fz_result_r,
            "r1_result_r": t.r1_result_r,
            "r2_result_r": t.r2_result_r,
            "r3_result_r": t.r3_result_r,
            "r4_result_r": t.r4_result_r,
            "bars_held": t.bars_held,
            "exit_time": t.exit_time.isoformat() if t.exit_time else ""
        })

    csv_path = os.path.join(out_dir, "fzasm_trades.csv")
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
    report_lines.append(f"*Complete trade log ({len(flat_trades)} setups) written to `{csv_path}`.*")

    md_content = "\n".join(report_lines)
    md_path = os.path.join(out_dir, "FZ_ASM_BACKTEST_REPORT.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Report written to {md_path}")
    return md_content


def main():
    parser = argparse.ArgumentParser(description="FZ-ASM Full Year Backtest")
    parser.add_argument("--year", type=int, default=2025, help="Backtest year (e.g. 2025)")
    parser.add_argument("--pairs", type=str, default="", help="Comma-separated symbols")
    parser.add_argument("--out", type=str, default="reports", help="Output directory")
    args = parser.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()] if args.pairs else DEFAULT_PAIRS
    print(f"Starting FZ-ASM Backtest for {args.year} across {len(pairs)} pairs: {', '.join(pairs)}")

    engine = FZASMEngine(extra_pairs=set(pairs))
    all_trades: Dict[str, List[TradeOutcome]] = {}

    for pair in pairs:
        trades = backtest_pair(pair, args.year, args.year, engine)
        all_trades[pair] = trades

    md_report = generate_report(all_trades, args.year, args.out)

    # If running in GitHub Actions, append to GITHUB_STEP_SUMMARY
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        try:
            with open(summary_file, "a", encoding="utf-8") as f:
                f.write("\n\n" + md_report)
            print("Successfully appended report to GITHUB_STEP_SUMMARY")
        except Exception as e:
            print(f"Failed to append to GITHUB_STEP_SUMMARY: {e}")


if __name__ == "__main__":
    main()

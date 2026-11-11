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


from .execution import TradeOutcome
from .data import load_minute_df
from bisect import bisect_right


def backtest_pair(pair, start_year, end_year, engine, calendar_timezone="UTC"):
    """Replay real M1 bars; decisions only see completed, contiguous aggregates."""
    df = load_minute_df(pair, start_year, end_year)
    rules = {"M5":"5min", "M10":"10min", "M15":"15min", "H1":"1h",
             "H2":"2h", "H4":"4h", "D1":"1D"}
    series = {tf:df_to_candles(resample_ohlc(df,rule,calendar_timezone=calendar_timezone),TimeFrame(tf))
              for tf,rule in rules.items()}
    available = {tf:[c.available_at for c in bars] for tf,bars in series.items()}
    minutes = df_to_candles(df,TimeFrame.M1)
    trades, active = [], []
    for i, candle in enumerate(minutes):
        for trade in list(active):
            trade.evaluate_bar(candle,i)
            if trade.closed:
                active.remove(trade)
        now = candle.available_at
        # Only scan when the explicitly selected confirmation timeframe closes.
        tf = engine.confirmation_tf
        end = bisect_right(available[tf],now)
        if not end or available[tf][end-1] != now:
            continue
        slices = {}
        for name,bars in series.items():
            n = bisect_right(available[name],now)
            slices[name] = bars[max(0,n-240):n]
        setup = engine.scan_asset(pair,slices,current_time=now)
        if setup:
            outcome = TradeOutcome(setup,i)
            trades.append(outcome)
            active.append(outcome)
    for trade in active:
        trade.end_of_data(minutes[-1].available_at)
    engine.coverage = getattr(engine,'coverage',{})
    import hashlib
    engine.coverage[pair] = {"first":df.index[0].isoformat(),"last":df.index[-1].isoformat(),
                             "m1_rows":len(df),"source":df.attrs.get("source","fixture"),
                             "sha256":hashlib.sha256(pd.util.hash_pandas_object(df,index=True).values.tobytes()).hexdigest(),
                             "calendar_timezone":calendar_timezone,
                             "confirmation_tf":engine.confirmation_tf,
                             "missing_intervals":int((df.index.to_series().diff()>pd.Timedelta(minutes=1)).sum())}
    return trades


def compute_metrics(trades: List[TradeOutcome], target_attr: str) -> Dict[str, Any]:
    """Computes quantitative metrics for a specific target strategy."""
    if not trades:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "net_r": 0.0, "expectancy": 0.0, "profit_factor": 0.0, "max_dd_r": 0.0
        }

    ordered = sorted((t for t in trades if getattr(t,target_attr) is not None),
                     key=lambda t:t.exit_times[target_attr])
    results = [getattr(t,target_attr) for t in ordered]
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
    simultaneous = {}
    for t in ordered:
        at = t.exit_times[target_attr]
        simultaneous[at] = simultaneous.get(at,0.) + getattr(t,target_attr)
    cum = np.cumsum([0.0] + list(simultaneous.values()))
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
    report_lines.append("**Research execution:** gross returns exclude spread, commission, financing and slippage. "
                        "Unresolved and unfilled orders are excluded from resolved P&L, never counted as zero. "
                        "Coverage is recorded separately; requested dates do not prove full-year data.\n")
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
    report_lines.append("| Strategy Target | Trades | Wins | Losses | Win Rate | Gross resolved return (R) | Expectancy (R) | Profit Factor | Max DD (R) |")
    report_lines.append("|---|---|---|---|---|---|---|---|---|")

    for label, attr in targets:
        m = compute_metrics(flat_trades, attr)
        report_lines.append(
            f"| **{label}** | {m['trades']} | {m['wins']} | {m['losses']} | "
            f"{m['win_rate']}% | **{m['net_r']:+0.1f}R** | {m['expectancy']:+0.2f}R | "
            f"{m['profit_factor']} | {m['max_dd_r']}R |"
        )
    report_lines.append("\n---\n")

    report_lines.append("## Outcome accounting (same setup cohort for every target)")
    report_lines.append("| Target | All setups | Closed | Unknown | Unfilled |")
    report_lines.append("|---|---|---|---|---|")
    for label, attr in targets:
        counts = {status:sum(t.status[attr]==status for t in flat_trades)
                  for status in ("CLOSED","UNKNOWN","UNFILLED")}
        report_lines.append(f"| {label} | {len(flat_trades)} | {counts['CLOSED']} | {counts['UNKNOWN']} | {counts['UNFILLED']} |")
    report_lines.append("\n## Monthly results by setup month (UTC)")
    report_lines.append("| Month | Target | Setups | Resolved | Unknown | Unfilled | Gross resolved R |")
    report_lines.append("|---|---|---|---|---|---|---|")
    for month in sorted({t.setup.timestamp.strftime('%Y-%m') for t in flat_trades}):
        cohort = [t for t in flat_trades if t.setup.timestamp.strftime('%Y-%m')==month]
        for label,attr in targets:
            metrics = compute_metrics(cohort,attr)
            unknown = sum(t.status[attr]=='UNKNOWN' for t in cohort)
            unfilled = sum(t.status[attr]=='UNFILLED' for t in cohort)
            report_lines.append(f"| {month} | {label} | {len(cohort)} | {metrics['trades']} | {unknown} | {unfilled} | {metrics['net_r']} |")

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
            "confirmation_tf": s.timeframe,
            "fill_bar_open": t.filled_at.isoformat() if t.filled_at else "",
            **{a+"_status":t.status[a] for a in t.attrs},
            **{a+"_reason":t.reasons.get(a,"") for a in t.attrs},
            **{a+"_exit_time":t.exit_times[a].isoformat() if a in t.exit_times else "" for a in t.attrs},
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
    parser.add_argument("--out", type=str, default="reports/repaired", help="Output directory")
    parser.add_argument("--download-m1", action="store_true", help="Prepare historical cTrader M1 cache explicitly")
    parser.add_argument("--confirmation-tf", choices=["M5","M10","M15"], default="M5")
    parser.add_argument("--calendar-timezone", default="UTC", help="Provider bar anchor, e.g. Europe/Athens; UTC research default")
    args = parser.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()] if args.pairs else DEFAULT_PAIRS
    print(f"Starting FZ-ASM Backtest for {args.year} across {len(pairs)} pairs: {', '.join(pairs)}")

    engine = FZASMEngine(extra_pairs=set(pairs), confirmation_tf=args.confirmation_tf)
    all_trades: Dict[str, List[TradeOutcome]] = {}

    for pair in pairs:
        if args.download_m1:
            from .minute_cache import prepare
            prepare(pair,args.year)
        trades = backtest_pair(pair, args.year, args.year, engine, args.calendar_timezone)
        all_trades[pair] = trades

    os.makedirs(args.out,exist_ok=True)
    with open(os.path.join(args.out,"coverage.json"),"w") as f:
        json.dump(engine.coverage,f,indent=2)
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

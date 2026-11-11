# ASM repair handoff

## Implemented

- Removed the H1 direct-entry fallback. Required confirmation timeframe is explicitly M5, M10 or M15 (M5 default); selection is fixed before a run, not chosen from later profitability.
- Candle timestamps remain bar opens. Every candle carries an availability/close time. The engine rejects unfinished candles, and the runner exposes only closed aggregates. Missing constituent minutes invalidate an aggregate. Provider timezone is configurable, with DST-aware resampling. UTC remains an explicit research default, not a verified broker daily anchor.
- Freeze sweep, directional map and POI while awaiting lower-timeframe confirmation; invalidate the context when the sweep extreme or target is taken. Reject dual sweeps and nonconsecutive sweep candles.
- Model A creates a pending limit at the displacement FVG or last opposing candle zone, instead of entering at the break close. Model B creates a pending limit behind the inducement. Both require a valid structural target and equilibrium beyond entry; arbitrary replacement targets are removed.
- Real M1 prices drive fills and exits. Pending orders expire at session end. No profit is awarded without a fill. Gaps, end-of-data exposure and unprovable intrabar sequencing remain explicit UNKNOWN outcomes.
- Partial exits weight both halves; time exits value remaining exposure. Each exit variant has its own status, reason and exit time. Drawdown uses chronological exits, netting simultaneous exits before drawdown calculation.
- Reports include the identical setup cohort for every target, resolved/unknown/unfilled counts, monthly setup cohorts, and per-variant CSV evidence. Coverage records data range, M1 row count, gaps, input hash and calendar/timeframe settings.
- Added an explicit cTrader M1 preparation path with four-hour read-only historical requests and monthly checkpoints. No order-placement methods are called. Missing M1 data fails the run; H1 is never interpolated.
- GitHub regression workflow now tests repairs, not expected failures. Backtest workflow runs regression tests before research, keeps original results intact, and uploads new results as artifacts rather than automatically committing them.

## Verification

48 deterministic tests pass locally, including future-data perturbation, M5/M10/M15 routing, retest order pricing, missing-data rejection, fill-before-outcome, partial accounting, ambiguous intrabar outcomes, mirrored BUY/SELL stops, timeout valuation, DST daily closure, monthly checkpoint reuse and report reconciliation. GitHub Actions repeats these checks. No new full-year profitability result is claimed.

## Remaining source-validation limits

This is a repair of the demonstrated execution defects, not proof of complete fidelity to every lesson. The inherited daily-map / ITF level detectors still contain mechanical approximations. Lower-timeframe minor structure still uses a four-bar proxy; the last opposing candle/FVG construction and inducement-distance tolerance need chart-by-chart source validation. The automatic choice between M5/M10/M15 has not been invented: each research run chooses one explicitly. The Asian UTC session window is inherited and must be reconciled with the teacher's chart clock/provider settings before using the results as broker-specific evidence. These limitations must remain visible in any performance claim.

Minute OHLC cannot prove every intrabar event order; ambiguous outcomes are deliberately not assigned wins or losses. Returns are gross: spread, commission, financing and slippage are not estimated. Bid-only research prices are not a bid/ask execution simulation. Data gaps are exposed; recorded date coverage is not proof of complete market-session coverage.

## Run after validation

Use the `FZ-ASM Full-Year Backtest` GitHub workflow on FZ-ASM. Set year, selected pairs, confirmation timeframe and provider calendar timezone explicitly. Start with one pair for data/coverage verification, then expand. New output defaults to `reports/repaired`; archived `reports/fzasm_trades.csv` and the original report remain unchanged. Credentials stay in existing GitHub secrets. No local full-year job has been run.

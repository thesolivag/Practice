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

48 deterministic tests pass locally, including future-data perturbation, M5/M10/M15 routing, retest order pricing, missing-data rejection, fill-before-outcome, partial accounting, ambiguous intrabar outcomes, mirrored BUY/SELL stops, timeout valuation, DST daily closure, monthly checkpoint reuse and report reconciliation. GitHub Actions run 42930371797 also passed all 48 checks. No new full-year profitability result is claimed.

## Remaining source-validation limits

This is a repair of the demonstrated execution defects, not proof of complete fidelity to every lesson. The inherited daily-map / ITF level detectors still contain mechanical approximations. Lower-timeframe minor structure still uses a four-bar proxy; the last opposing candle/FVG construction and inducement-distance tolerance need chart-by-chart source validation. The automatic choice between M5/M10/M15 has not been invented: each research run chooses one explicitly. The Asian UTC session window is inherited and must be reconciled with the teacher's chart clock/provider settings before using the results as broker-specific evidence. These limitations must remain visible in any performance claim.

Minute OHLC cannot prove every intrabar event order; ambiguous outcomes are deliberately not assigned wins or losses. Returns are gross: spread, commission, financing and slippage are not estimated. Bid-only research prices are not a bid/ask execution simulation. Data gaps are exposed; recorded date coverage is not proof of complete market-session coverage.

## Run after validation

Use the `FZ-ASM Full-Year Backtest` GitHub workflow on FZ-ASM. Set year, selected pairs, confirmation timeframe and provider calendar timezone explicitly. Start with one pair for data/coverage verification, then expand. New output defaults to `reports/repaired`; archived `reports/fzasm_trades.csv` and the original report remain unchanged. Credentials stay in existing GitHub secrets. No local full-year job has been run.

## Source review follow-up

See FZ_ASM_SOURCE_VALIDATION.md and FZ_ASM_SOURCE_REVIEW.html. Removed Map 5 fabricated projection: it now requires an explicit, already-known untaken range-target candle. The scanner does not yet select that candle, so it emits no Map 5 trades. Daily candle-range setups also reject a boundary already reached by the sweep. Order blocks record their formation availability separately from origin and label FVG versus unvalidated no-FVG displacement candidates. No blanket FVG-only filter was added: the lesson explicitly allows exceptions. Expanded local suite: 51 passing tests.

## 2026-11-11 — paired stop study implemented

User authorized H1/H2 sweep-extreme and lower-timeframe invalidation stops as independent backtest variants. New default engine policy `mss_retest` requires the completed lower-TF structural break before a pending FVG/OB retracement order; `legacy` explicitly retains the older inducement route. M5 remains the default, with M10/M15 fixed before running.

- The existing four-bar structural-break detector is still a research proxy, not a newly validated swing detector.
- FVG entry prefers an already-known, aligned, unmitigated POI boundary inside the gap; otherwise uses the gap surface. No-FVG shifts may use the last opposing candle OB. Overlapping local key-level discovery remains limited to the POI supplied by the context builder.
- `hourly_sweep`: beyond the actual H1/H2 sweep extreme plus existing three-pip buffer.
- `ltf_invalidation`: beyond the last opposing confirmation-TF candle and its departure leg through the confirmed break, plus the same buffer. This explicit candidate rule is provisional, not a claim that the teacher always uses it. No opposing candle means UNAVAILABLE, never a fabricated stop.
- `--stop-mode both` clones each signal before replay; same entry/time, distinct stops and fixed-R targets. Each variant has independent M1 execution/ambiguity accounting. Reports are separated, with monthly breakdowns and a common signal ID; variant returns are not added together. Missing local stops are counted and have blank stop/P&L CSV values.
- GitHub Actions inputs expose stop mode and entry policy. No annual run has been launched for this change; run full backtests via Actions when requested. Existing historical results are unchanged.
- The separate direct H1 A/V entry route has not been added by this stop-study change. Its exact key-level extraction still needs a sourced mechanical definition; no silent H1 fallback is introduced.
- Local regression: 59 tests pass, including mirrored stops, causal POI availability, actual separate stop outcomes, paired IDs, monthly reports and missing-stop accounting.

## Direct H1 A/V route and chart-validation package

Implemented `entry_policy=h1_av` as a separate opt-in route in the scanner, CLI and GitHub workflow. It uses H1 closes even when the lower-TF selector says M5. Requires the same frozen daily map, POI and session sweep context as other routes; does not bypass those gates.

Provisional mechanical definition for user chart approval: contiguous opposite-colour H1 pair containing the sweep candle; previous close is the shared body junction (V for bear-to-bull, A for bull-to-bear). Current open must be within the existing 3-pip buffer of that close. The closing candle must finish away from entry in the intended direction. A later new sweep extreme or an already-taken target invalidates it. Pending limit only after the confirming H1 close, stop beyond the sweep extreme plus buffer. No H2 substitution, no fabricated M5 stop for this route. The source concept lesson explains V/A on a line chart at 2846–2881 seconds; the exact candle-pair and tolerance implementation remains a hypothesis for user validation, not a teacher-verified rule.

64 regression tests pass. Added mirrored A/V tests, unavailable/future inputs, missing-hour and gap rejection, H2 rejection, and engine close-time/duplicate checks.

Chart package: `scripts/build_asm_validation_charts.py --source <GBPUSD M1 CSV.gz>` renders real historical GBPUSD entry-module examples from the existing IC Markets cache. Source hash, all displayed candles, entries and stop evidence are retained in `evidence/av-validation/evidence.json`. Examples intentionally test entry/SL components only: prior-24-hour reference range is supplied to the evaluator, not asserted as a qualified daily map. These are NOT claimed full-scanner trades or performance evidence. No future bars are shown; missing context hours are marked as gaps. Selected without examining outcomes. H1 sell/M5 sell: 2026-06-26; H1 buy: June 30; M5 buy: July 8. Three PNG pages and a PDF are delivered in chat. No annual backtest or live deployment launched.

## NZDJPY user reference, 2026-11-11

Read reports/FZ_ASM_NZDJPY_REFERENCE.md before claiming a teacher match. Bounded data collection succeeded via GitHub Actions. H1 sweep and body-junction price align closely, but M5 zone identity and SL distance remain unresolved. Added opt-in swing_fvg / swing_ob policies with protected-pivot breaks and local A/V overlap, retaining the old policy for comparison. Reference fixture tests cover causal recognition and explicitly preserve/report mismatches rather than fitting screenshot prices. Run tests/test_fzasm_reference.py alongside the prior suite (69 total passing). Review charts before broad backtests.

# Capacity-corrected comparison and rollover/cost investigation

User authorized proceeding 2026-11-08. No demo/live broker order execution is enabled.

Two independent Actions workflows:
- bishop-session-costs.yml: report on existing corrected cohort, using runs 42371042901, 42499187752, 42516446781. Original capacity blockage still applies. This is quick aggregation, not a replay.
- bishop-capacity.yml: fresh 2026 replay of unchanged detection/bias/SL/target rules, same frozen input cutoff 2026-11-07 11:00 UTC. New immutable order IDs and checkpoints. Monthly sections, 330-minute job limit, 12 market jobs at once. Fresh 24-hour EURUSD prefix/poisoned-future/runtime pilot must pass first. All computation runs on GitHub; no broker/DB/Telegram secrets are passed.

## Capacity correction
Original replay treated CENSORED as terminal for execution but permanently active for the capacity limit. All 26 common markets reached 10 unknowns, eventually preventing new original-Bishop and KK-aligned trades.

New research fork keeps unknown outcomes unknown. For static LIMIT orders only, it proves occupancy ends when (1) pending expiry or an observed cancellation has passed and (2) a subsequent complete observed bar touches SL or TP. Every possible state (never filled, already exited, or still open) is then flat. Release occurs at that bar's publication time, never retroactively. No expiry alone, gap imputation, outcome guessing, unsupported amendments or future candles may free capacity. This deliberately conservative upper bound can still temporarily block trading. It does not establish whether an unknown trade won or lost. Original capacity cap and selection remain.

Original research and live modules are untouched. The new replay uses research_stop_simulation for the tested M1 entry/SL-only proof. Exact OHLC-matching saved M1 hours from 42499187752 are loaded with hashes, used for execution only after the parent H1 closes. Detection sees H1 prefixes exactly as before. Many newly admitted trades lack M1 evidence; new unknowns remain explicit. This is NOT a fully tick-resolved rerun, and old corrected outcomes cannot be attached to new orders by proximity.

## Session and costs
Groups use observed fill-window overlap, NOT exact fill timestamps: 17:00-18:00 America/New_York, adjacent 16:00-17:00 or 18:00-19:00, other hours, and no proven fill window. DST conversion is explicit. Both the old cohort and fresh replay report monthly close-month figures and per-session sensitivity at 0, 0.5, 1, 2, 3, 5 pips total round-trip cost.

These are hypothetical all-in deductions against actual initial risk, NOT measured historical spread/commission/slippage or a bid/ask execution simulation. No swap/financing model, news calendar filter, rollover trade exclusion, or demo connection is implemented. Unknown/open are counted separately and excluded from R. Comparing buckets is not evidence that blocking rollover will produce the same remaining trades or improve profitability.

Artifacts: existing-session-cost-report (baseline), capacity-report (fresh gross report plus sessions/REPORT.md, REPORT.json, session_cost_scenarios.csv, monthly_cost_scenarios.csv). Report explicit partial markets if jobs fail. No source report or existing workflow is replaced.

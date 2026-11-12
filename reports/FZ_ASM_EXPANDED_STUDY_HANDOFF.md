# Expanded ASM study — 2026 to 2026-11-12 00:00 UTC

User requested all seven major JPY crosses (USDJPY, EURJPY, GBPJPY, AUDJPY, NZDJPY, CADJPY, CHFJPY), XAUUSD, EURUSD, GBPUSD. Explicit four entry scenarios: direct H1 A/V; H1 A/V after M5 structural shift; provisional M5 order block; provisional M5 FVG with overlapping A/V level. Do not mix returns across alternatives or describe the provisional interpretations as teacher-validated.

Each model's signals produce paired exact-sweep and three-broker-pip-beyond-sweep stops, then six independently replayed outcomes: 1R/2R/3R/4R, frozen Asian opposite extreme, existing FZ research exit. This is twelve scenario outcomes per signal, not twelve independent trades to sum. Signal sets may differ between entry models. Nonpositive exact stop risk stays UNAVAILABLE. Missing/unfavorable Asian target stays UNAVAILABLE for that target only. No new local-M5-stop selection is introduced.

Asian extreme uses complete M1 session history 00:00 UTC through the order decision clock; no future session extreme or later entry-fill information. SELL targets session low; BUY targets session high. The level stays frozen. FZ research exit remains half at map equilibrium, remainder at map target with break-even. It is explicitly labelled research, not proven teacher fidelity.

Execution correction from independent review: two canonical OHLC paths alone could falsely infer a pending-entry loss when the bar spans both stop and target. Added ENTRY_STOP_TARGET_ORDER unknown for that case, both directions. No loss is silently reclassified as a win.

fzasm.study replays continuously across months, preserving active trades and engine state. Monthly files are cumulative report checkpoints, not execution-state resumes. Reports group by setup month; positions can exit later. At data end remaining positions become UNKNOWN. Requested missing months are enumerated, not omitted. OPEN/PENDING remain explicit in interim snapshots.

Output: outcomes.csv; coverage.csv; monthly.csv/yearly.csv per pair, model, stop,target; monthly_groups/yearly_groups for JPY/Gold/Majors; monthly_all/yearly_all for selected-symbol totals within the same strategy scenario. Weighted win rates use positive closed / all closed including flats. No averaging monthly percentages. Missing artifacts taint aggregation coverage.

Historical fetches retain completed months and atomic four-hour chunks. Empty windows are not cached; a month containing an empty window is not marked complete. Failed downloads can resume good chunks. No H1-to-M1 interpolation. Source gaps remain visible. Fixed shared cutoff prevents serial pair jobs having different evaluation horizons.

Workflow fzasm-h1-comparison.yml now replaces the smaller comparison, same concurrency group cancels obsolete queued run. Ten serial pair jobs prevent study jobs racing broker refresh; 335-minute calculation limit within 360-minute job reserves cleanup time. Always upload partial reports; final aggregator marks missing pairs/months. Restored cache is research cTrader data; unchanged account/feed provenance limitations remain.

Independent execution and workflow reviews performed. Their concrete findings were fixed: pending-bar ambiguity, missing-month reporting, cold-start disclosure, fixed cutoff, cleanup allowance, and empty-month-cache poisoning. 94 tests passed locally before launch; included real-reference entry tests plus new target freeze, direction symmetry, month-crossing, paired-stop, report reconciliation and cache-retry tests. Empty-artifact merge tested and reports missing coverage honestly.

Limits: January starts without prior-year warm-up, daily map/ITF POI gates still apply, UTC research calendar and inherited prime sweep hours include hour02 (earlier handoff exclusion claim corrected), gross R excludes spread/fees/slippage/financing, portfolio exposure/compounding not modelled. Existing session expiry06UTC and120-hour maximum hold retained. No live orders or production deployment.

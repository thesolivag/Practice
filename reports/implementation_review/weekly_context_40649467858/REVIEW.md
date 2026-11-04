# Held USDCAD plan: isolated cause confirmed

GitHub40649467858 at e1f005f. This is a risk-plan isolation, not a full portfolio replay or a teacher execution match.

1. Reconstructed all38 original H1standingBUY plans available2026-06-12 16:00UTC from frozen40day replay40584728247.
2. Called the actual risk planner with their original bars, levels, liquidity, ranges, reference evidence and historical story details. Assertions reproduced every original stop AND target exactly before any modification.
3. Recomputed Weekly context using full frozen W,D,H4 history available at the confirmation clock. It resolves BUY through a May8Weekly→Daily engulf→H4 confirmation ROOT story; Weekly/Daily structural reads also BUY, agreeing directionally with Bishop's narration.
4. Changed only each plan's contemporaneous weekly-context fields and called the same risk planner again.

Results:
- Original targets:1.39726 /1.40240.
- Revised targets: **1.40240 for all38**.
- Original and revised stops: **1.39587 for all38**.
- Revised risk status:ELIGIBLE for all38.
- Submitted orders:0; no target/outcome fitting, riskguard override, cap increase or execution shortcut.

Thus missing higher-timeframe context is a demonstrated cause of this frozen target conflict. Price rules did not need relaxing. This check preserves the same H1 source-pattern candidates; it does not pretend Bishop's subsequent personal M30 entry was an identical H1 broker trade.

Full engine40648721296 using full history hit its300second CPU/runtime budget and produced ABORTED_RUNTIME, despite workflow completion. It is not a successful strategy replay. Next necessary step is profiling/optimizing full-history replay or a reviewed separation of long context history from entry scan work, then verifying candidate selection and fill behavior. Do not claim orders now place merely because risk geometry no longer conflicts.

Owner also closed GBPCAD breakout-stop concern: deeper stop is logical for breakout, source particular stop uses a different interpreted reference. The corrected entry remains exact broken-A retest; no universal engulfing-stop rule was added.

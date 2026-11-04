# Simultaneous execution-plan review

Problem: the seven-day EURNZD context run counted 28 wins from only three
same-price/time triggers (10, 10 and 8 variants). An order exposure cap does
not resolve which protection/target alternative represents the actual entry.

The engine now groups eligible owner candidates by instrument, timeframe,
model, side, availability time and entry price before submitting that batch.
Competing stop/target/order-kind/expiry plans produce
`AMBIGUOUS_EXECUTION_PLAN`: every candidate stays visible, no group member
becomes a paper order. Equal execution plans linked to different level IDs
produce `AMBIGUOUS_LEVEL_SELECTION`; equal prices alone do not establish equal
level cancellation lineage. Diagnostics identify the competing setup IDs once
per group. Blocked or unresolved candidates cannot create a conflict.

This is an explicit conservative operating safeguard, not a newly attributed
Bishop teaching and not a source-derived ranking of logical stops. It does not
resolve the underlying competing story/protection evidence. The source teaches
consistent model selection (course15 52–167; STRATEGY section5), while the
specification does not establish a portfolio rule for concurrent alternatives.

Exact-level, identical-plan aliases retain their prior first-context policy.
Later confirmation clocks remain distinct; independent `source_all` and
`all_routes` diagnostics retain all alternatives. Distinct timeframes/models or
entry prices are outside this guard, not proof of independent opportunities.
The change uses only candidate facts known at the same placement clock and
never chooses an alternative by later profit. The run identity records the
changed selection semantics so old and new results cannot share an identity.

Independent review rejected an initial proposal to merge equal-price plans
across level IDs, because it would arbitrarily inherit one level/story's
cancellation lifecycle. The implemented guard leaves that ambiguity explicit.
Teacher-example replay remains pending and is not replaced by these tests.

Verification: independent integration tests plus existing alias checks passed
(9 passed, 25 deselected). Full GitHub regression run `40518001892` is dispatched
for commit `cb3f406`; it was queued awaiting a runner at this review update.
No full-suite pass or revised backtest profitability is claimed here.

Final CI result: run `40518001892`, job `122236638997`, completed successfully
on 2026-10-27: 433 passed, 5 skipped, including MySQL integration. This replaces
the queued status above; historical teacher fidelity remains separate.

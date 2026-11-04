# USDCAD execution-only refinement

Purpose: resolve H1 intrabar uncertainty for the entire June5–13 portfolio before judging the source-clock H1 fourth-man example. No teacher-price fitting, source-outcome selection, exposure-cap change or detection-timeframe change.

## Frozen input and validation

Initial read-only collection: GitHub run40684156297, artifact12813488540. Complete snapshot is committed under data/usdcad_execution_m1. The collector never refreshes or writes borrowed Kevin tokens. 8367 M1 bars cover8460 expected minute slots;93 are missing. These missing minutes remain unknown and are never imputed or replaced with H1 bars.

130 complete H1 aggregates exactly match the original frozen H1 OHLC.11 H1 bins cannot establish full equality; their observed M1 prices must stay within H1 high/low, with equality of opening/closing prices whenever the boundary minute exists. The validator rejects inconsistent instrument precision, calendar/anchor, venue, provider, broker symbol and IC environment/source identity, plus nonmonotone publication. Input hashes and missing timestamps are preserved in input_validation.json.

The first strict-completeness job deliberately failed before replay upon detecting missing minutes. The revised path uses the original simulation gap-censoring rule and labels the execution result PARTIAL_UNVALIDATED. A gap does not free reserved exposure.

## Code and verification

Only prospective cap simulations and final execution receive M1; sessions, aggregation, structure, stories and setup detection receive the original H1 history. Cap remains10. No future-available M1 bar enters a submission-time simulation. Separate execution hashes/coverage enter run provenance.

Independent reviewer found no blocker after adding the monotone-publication guard and incomplete-bin consistency checks. GitHub regression40684677869:519 passed,5 skipped. Tests cover input holes, contradictory prices, wrong price basis, late internal publication, original detection inputs, M1 execution in both simulation paths, and gap-censored exposure reservation.

## Replay result

Run40684679119 completed. All130 H1 source-clock candidates retain the same1.39680/1.39587/1.40240 plan, but EXPOSURE_CAP still holds every candidate. The initial M1 portfolio has12 orders:1WIN,1LOSS,10CENSORED. Of the nine original H1-censored orders, one resolves to LOSS; eight remain labeled intrabar-uncertain. Two additional selected pending orders encounter missing M1 data.

Inspection then isolated a simulator defect: five of the eight uncertain LIMIT fills have a terminal close beyond target, without any stop touch. The terminal close proves target contact after entry under the existing constant-spread OHLC model. The old unconditional just-LIMIT censor discarded that proof. Correction424033c uses BUY close>=target or SELL close+spread<=target, while preserving all both-hit, stop-only, unresolved-path and missing-data censoring. Event publication remains at bar availability; prospective caps cannot use the close earlier. Execution policy/run identity are versioned. Independent review confirmed the proof; GitHub40686939279 passed529 tests with5 skipped. Full corrected run40686940103 completed successfully. All130 source-clock candidate records are exactly equal to the original full-history run40682098812; this is not only numerical-plan equality. The source-clock order remains held for EXPOSURE_CAP. The21 selected portfolio orders end as10WIN,1LOSS,10CENSORED; these are an incomplete zero-cost diagnostic, not a valid win-rate estimate.

Exactly five previously censored order IDs become WIN under terminal-close proof. Together with the LOSS resolved by finer candles, six of the original nine ambiguous orders are resolved. Three original orders remain genuinely intrabar-uncertain. Seven subsequently selected orders encounter missing M1 minutes. Those ten uncertain outcomes reserve the ten slots; no cap increase or outcome-based candidate choice was made.

The next evidence needed is tick ordering for the three remaining intrabar cases and quote/session coverage for the seven gap-affected orders. The teacher H1 entry has not passed end-to-end placement validation. Bishop's additional M30 engulfing and final displayed stop remain distinct from this H1 candidate test.

These outcomes are hypothetical zero-cost execution diagnostics, not mentor outcomes or strategy acceptance.

# Full-history replay performance work and decision-preservation proof

Goal: retain full frozen higher-timeframe history for the USDCAD fourth-man investigation without changing trading rules, expected teacher prices, portfolio caps, candle alignment or data coverage.

## Measured problems

Full-year replay40648721296 exhausted300seconds. Entry-stage profiling40652387148 showed preprocessing never reached entries within300seconds; its empty-profile rendering error was fixed separately. Stage-timed40653939820 then isolated284.7seconds in unfinished find_stories. Later40656994022 completed story analysis in153.1seconds but exhausted the remaining budget in detect_setups after112.1seconds. These are ABORTED_RUNTIME, not successful teacher replays.

CPU profiles40652016844,40654711644 and focused story profile40656383314 identified repeated full-event/range-history scans. The focused profile counted42million metadata gets and showed full scans in child-lineage checks and story range selection. Optimizations now:

- Index known confirmation breaks by side, all structural breaks by scope (including UNKNOWN evidence), range invalidations by scope, and earliest level-unavailability causes.
- Resolve exact range versions/parents and historical seed-linked story ranges directly, preserving each query's existing first-input tie behavior. Historical-seed story lookup is intentionally distinct from current-version lineage lookup; do not conflate them.
- End confirmation search after the earliest valid tied publication batch, or after a closed-candle invalidation makes all later confirmations impossible. Role-only changes are not treated as permanent invalidations.
- Reuse same-side H4 reaction geometry, retaining each story's birth and sponsoring-break cutoffs. Index latest visible reactions while preserving publication clocks, stable ties and the no-fallback-from-retired-episode rule.
- Avoid calculations that cannot emit entries at the selected clocks, while still producing historical breakout-reference diagnostics. An early comparison caught193 missing support records; those were restored before acceptance. Delayed confirmations crossing the scan boundary remain covered.

## Exact frozen-result equivalence

Baseline40652436745 (bb081b0) and final optimized bounded replay40681944363 (0bcdd70) use identical frozen data, case, clock window, policy and costs. Comparison asserts equality of **all29 result keys**, including structures, stories, lifecycle events, setups, orders, outcomes and support. Plan hashes differ because implementation files changed; the actual engine result does not.

Canonical result SHA256:ff2ebf1b8861e78e99a146400b43a159e21152cc1a709f49fd4b30297f1a7c8b.

GitHub regression40681932479: **511 passed,5 skipped**. Focused regressions compare indexed paths to original full scans, including future publications, tied clocks, historical seeds, unknown opposing breaks, renewed KL contact, role restoration, per-story cutoffs and delayed entries.

This equivalence proof is not teacher acceptance. Full-year order placement still requires the completed optimized replay result; a context-only risk reprice cannot imply an actual selected order.

Latest additions index episode events and first-take observations with monotone-clock guards, filter Weekly terminal events, index cancellation events, and fast-path exact JSON primitives. Independent review of0bcdd70 found no blockers. All29 bounded result sections remain exactly equal, including diagnostics. Full run40661241292 completed all calculation stages but exhausted600seconds while serializing the audit; the primitive fast path retains every record and directly addresses that measured bottleneck.

## Completed full-history replay

Run40682098812 at0bcdd70 saved the complete diagnostic audit successfully. Stage totals: analyze14.00s, stories63.62s, entries152.40s, simulation0.72s. The full compressed result exceeds GitHub's regular-file size limit; artifact12813681556 and its SHA256 manifest identify the complete saved result.

At June12 16:00UTC, all130 H1 BUY standing-extreme candidates agree on entry1.39680, stop1.39587, target1.40240. The earlier target conflict is resolved. All130 are rejected for EXPOSURE_CAP, so there is no selected H1 order or fill to claim. The cap is unchanged at10. Censored execution deliberately reserves exposure; dropping uncertain positions or raising the cap would manufacture availability. Portfolio evidence and source-clock candidates are preserved with the run.

This validates completed computation and target convergence, not end-to-end teacher replication. Next investigation is execution resolution for earlier reserved exposure, using finer frozen IC candles rather than loosening selection or choosing a winning example. Bishop additionally used M30 engulfing; the displayed final source stop is not an independently annotated H1 stop.

Portfolio evidence identifies nine earlier June5 orders censored for UNRESOLVED_INTRABAR_SEQUENCE, plus a June11 H1 standing order still OPEN at the replay horizon. These are the ten reserved slots. The next data investigation should refine those execution windows, preserving prospective availability and source-clock selection.

## Subsequent execution correction is outside this equivalence claim

The exact-equality proof above applies to runtime changes through0bcdd70. Later424033c intentionally changes execution outcomes when a terminal candle close proves target contact after a LIMIT fill, and versions execution/run identity. It does not claim equality with the old simulator. See ../usdcad_execution_refinement/REVIEW.md for separate evidence and validation.

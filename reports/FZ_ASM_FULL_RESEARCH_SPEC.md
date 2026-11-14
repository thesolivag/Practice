# ASM full-context research v1

Status: an executable mechanical research interpretation, NOT a certified reproduction of every discretionary FZ teaching. No performance conclusion. Existing pure-Asian and legacy filtered models remain separate. This specification is frozen before any new market-performance test.

## Scope and evidence

Primary sources are timestamped transcripts under knowledge-base/videos. Transcript errors and the limited resolution/access of source frames prevent treating every interpretation below as verified teacher intent. Three complete chart-by-chart validations are still not established.

| Component | Source evidence | Implemented choice / limitation |
| --- | --- | --- |
| Daily FROM/TO maps | asm-the-5-maps 306–340s,607–677s | Evaluate all eligible map candidates. No manufactured target from zone width. |
| Structural map | same742–862s; chart-work1414–1420s body-to-body break | One-neighbour body-edge pivot, confirmed before break; observed extension range. Pivot span and range-anchor selection are research assumptions. |
| Candle range | five-maps348–410s,977–999s | Single-sided daily range sweep, standing opposing boundary, target opposing extreme. |
| Consecutive leg | five-maps413–441s | At least two consecutive opposing candles, sweep of leg extreme, target opposite leg extreme. Two is a mechanical minimum, not a fitted optimum. |
| Map4 confluence | five-maps449–480s | Candle-range sweep touches pre-existing aligned daily level. |
| Map5 rejection / invalidation | five-maps533–598s,1088–1124s | Rejection at a pre-existing daily level within a still-active sponsored range; retain sponsor destination. A close back beyond the near edge confirms rejection; far-edge penetration distinguishes5B. This is an interpretation requiring chart validation. |
| Session sweeps | Day-One2553–2588s | Closed H1 sweep; H2 fallback if no H1 sweep at that clock. No qualifying sweep means no entry. |
| Lower-timeframe choice | Day-One2644–2651s,2731–2739s; concept1493–1506s | M5/M10/M15 supported. Earliest ready entry; simultaneous ties prefer M5 thenM10 thenM15. Teacher priority is not established. |
| Entry routes | user NZDJPY example; Day-One lower-TF shift; key-level866–907s | Closed close-price-pivot shift, FVG with adjacent A/V overlap or main-origin OB; H1 A/V after M5 shift as fallback. Independent direct-H1 policy remains selectable. |
| H1 alternative | user's explicit instruction | Direct H1 A/V and H1 A/V with M5 shift are separate policies. No invented H2 direct A/V route. |
| Stops | user's explicit three-pip instruction | Sweep extreme plus/minus3 broker-defined pips. Recognition still invalidates on a later breach of exact sweep extreme before order creation. |
| Targets | chart-work858–880s,1165–1170s,1696–1718s | Choose nearest unhit aligned daily-map destination, frozen when sweep qualifies. This priority is our conservative research choice. Previous-week-low is not automatically added as a new target hierarchy. |

## Deterministic decisions, exposed rather than hidden

1. Only bars available at the decision clock enter any calculation. Native D1 availability is provided explicitly; UTC intraday aggregation is a stated research calendar, not broker-native H1/H4 equivalence.
2. All active daily maps are considered. Opposing directions mean abstain. There is no unsupported map4>3>2>5>1 ranking. Same-direction alternatives use nearest favorable destination. This may reject trades the teacher takes; test it as an assumption, not as teacher intent.
3. Before the sweep opens, find active H4/H2 levels: adjacent opposite-colour body junctions, FVG-backed origin blocks, or one-time body-close-invalidated breakers. No whole-history average-body threshold. Levels retire after a close beyond the far edge. Latest qualifying level wins; not nearest to the current close.
4. Require aligned level in the lower half of the chosen bullish range or upper half of bearish range. This numerical location policy is provisional. POI must be respected by the sweeping close.
5. Preserve multiple eligible sweep contexts. A new sweep cannot be silently suppressed by an older context. Freeze context/target per sweep. Retire on direction invalidation, exact sweep-extreme breach, reached target or session end.
6. Auto route: at each closed lower-TF clock, inspect M5 thenM10 thenM15. FVG-overlap precedes OB at a simultaneous clock; M5-gated H1 fallback comes next. Earliest ready clock wins; never select by eventual outcome. Only one emitted setup per symbol/scan clock, earliest sweep first. These priorities are assumptions. Re-entry after an emitted sweep is not modeled.
7. Lower-TF CHoCH uses existing close-price pivots with one neighbour on each side, before the sweep extreme. FVG overlap must use an adjacent reversal pair whose close/open differ by no more than one pip. Main-origin OB uses the last opposing candle at/before the sweep extreme and a confirmed departure; no separate violation-block classifier is claimed. No-FVG OB acceptance in full context remains provisional.
8. H1 junction tolerance retains the existing3-pip user-study implementation. It is distinct from the one-pip FVG-overlap tolerance and neither is optimized against this new sample.
9. Orders become pending after the confirmation close. Historical taps cannot fill a newly created order. Orders expire at06:00UTC; filled trades retain the existing120-hour cap. Both are explicit execution choices. No partial profit or break-even shift is invented for the structural target.

## Reports and testing

fzasm/full_replay.py evaluates the same emitted signal independently at1R,2R,3R,4R, the causally known Asian opposite extreme, and the frozen structural target. Unknown, unfilled and unavailable scenarios stay separate. Structural target is a full exit. Invalid/unfavorable Asian destination is UNAVAILABLE. Each signal has exactly six scenario rows, not six separate opportunities.

Outputs: trades.csv, monthly.csv (pair, entry route, target), plans.json (full entry/context evidence), decisions.json (maps and rejection diagnostics), manifest.json (input hashes, assumptions and coverage), daily_audit.json. Gross and net use0.08R cost per resolved filled trade by default, based on the user's example, not verified broker charges. Missing intervals and unresolved costs remain limitations; no portfolio return or income claim.

scripts/run_asm_full_research.py requires native daily history and pre-period M1 warmup. It rejects unverified daily gaps, invalid OHLC and an empty test window. Maximum test window31 days. GitHub workflow fzasm-full-research.yml is manual only, restores existing archived data, has a45-minute job cap and a30-minute replay cap. No new annual study or price download is triggered by adding this model. If archived artifacts/cache have expired, stop with an error rather than silently change the source.

Implementation checks include body-versus-wick break, all five map families, conflicting maps, future-candle exclusion, closed-sweep timing, pre-existing levels, H2 fallback, timeframe precedence, exact scenario reconciliation and single structural exit. These tests validate the specified code behavior; they are not profitability tests or teacher-example validation.

## What is not claimed

This does not resolve every discretionary active-range, no-FVG exception, violation-block, partial-management or target-selection choice in all source videos. Those must not be called teacher-validated. The implementation is complete for the written research specification; faithful replication of the entire discretionary method remains unverified. No new performance results exist yet.

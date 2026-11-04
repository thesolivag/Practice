# USDCAD quote ordering and no-touch price evidence

Frozen audit40691550808 (artifact12817552240) collected BID/ASK quotes for20 bounded windows,212minutes total, using40 read-only historical requests. It did not refresh shared tokens, submit trades or change settings. Raw pages, decoded quotes, request bounds and hashes are committed under data/usdcad_tick_audit.

The first audit40691247413 rejected signed price deltas and preserved its raw response. The corrected decoder resets timestamp and price accumulators for each page, preserves same-millisecond groups and verifies pagination rather than dropping boundary quotes. Re-decoding the original08:48 sample exactly reproduces the frozen M1 OHLC. All three disputed minutes match M1 exactly. The successful decoder audit does not depend on the failed result's interpretation.

## Evidence actually obtained

- June5 13:43: entry occurred, target did not occur after entry in that minute. Continue the filled position into subsequent M1 data.
- June5 08:48: same result; a target touch before entry is not a profit.
- June5 12:27: target follows entry; the entry/target timestamps are1780662466243/1780662466609 milliseconds. No same-ms tie decides this outcome.
- All93 missing M1 minutes contain no returned BID or ASK updates in the complete bounded archive responses. This is not treated as proof of historical market closure or permission to insert bars. The broker's current schedule is preserved as current-only.

## Optional execution evidence implementation

`refinement_evidence.py` verifies hashes, source/environment, full pagination, raw decoding, boundary ties and exact BID-minute OHLC before enabling quote ordering. ASK request completeness is checked separately; execution retains the declared constant-spread hypothesis and does not claim actual broker fills.81 covered M1 bars match exactly;18 other covered bars are excluded as uncomparable. Only supported, fully matching minute proofs enter execution.

Missing intervals can be resolved by the original complete H1 range only when it proves entry or stop/target could not have been touched. Pending BUY requires H1low+spread>entry; SELL requires H1high<entry. Filled positions require both exit thresholds strictly outside the hour. H1 data must already be published by each simulation clock. All dependent execution events and fill observations wait until that proof's publication. No candle, quote or fill is synthesized. Unproven intervals remain censored.

A pending expiry/cancellation bounds the interval that actually needs coverage; a gap after known expiry cannot erase it. Filled gap proofs are refused across amendments, break-even actions, partial exits or manual closes rather than using stale protection levels.

The engine passes one immutable evidence object to prospective cap checks and final execution. H1 detection remains unchanged; the cap stays10. Independent reviewer found no blocker after the position-change safeguard. Focused tests:61 passed. GitHub regression40693590069 passed553 tests with5 skipped. Full replay40693590233 completed and saved its audit (artifact12818542643).

## Completed result

All nine original uncertainties resolve to8WIN and1LOSS. All seven later pending orders previously blocked by gaps resolve to EXPIRED. The source-clock H1 setup now produces one canonical BUY LIMIT order5603fd3d77ec39cb1729d7a2 after economic aliases are merged. Entry1.39680, SL1.39587, target1.40240; fill windowJune12 16:13–16:14UTC. It remains OPEN atJune13 00:00UTC. All130 complete source-clock setup records exactly equal run40682098812. The cap stays10, no expected price/tolerance or candidate geometry was altered, and no later winner was selected to force a match.

Bishop additionally used M30 engulfing. This proves an H1 paper entry can execute with the appropriate existing plan; it does not establish exact full teacher-trade identity or validate every teacher example. The source narration likewise leaves the final trade open, so no source win is claimed.

## Broader strategy limitation

The same completed zero-cost exploratory portfolio contains72 orders:22WIN,25LOSS,15EXPIRED,1CENSORED and9OPEN. The47 closed trades total-11.76703220845078R. Open and uncertain outcomes remain unresolved, so these totals are not a completed performance estimate. The evidence does not validate the strategy as profitable. Next strategy work should audit setup selection and target qualification against mentor teachings, including tiny-reward counterweekly plans, rather than tune outcomes or loosen the exposure cap.

The current screenshot uses only frozen IC H1 OHLC and the saved M1 paper-fill window. It is not a reconstructed source chart. Full result hashes, source-clock decision and every portfolio observation are preserved alongside the artifact manifest.

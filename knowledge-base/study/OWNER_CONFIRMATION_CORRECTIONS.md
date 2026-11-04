# Confirmation corrections retained from owner chart review

These corrections guide implementation and future reviews; a green unit suite is not certification of every Bishop example. Primary video frames and teacher fixtures remain independent from engine output. Do not fit entries/stops or pick later winning alternatives.

## Breakout: break, flip, then retest the exact level

BUY: identify the A-shaped SELL/resistance key level. A closed breakout invalidates resistance and changes its retest role to BUY/support. Place a LIMIT at **that exact A**, then wait for a subsequent price retest. SELL mirrors this at the broken V (former BUY support → SELL resistance). Breakout close is confirmation, not automatic entry. A nearer unrelated V/A, historical level, or chosen profitable retest is not a substitute.

Concrete root cause in frozen GBPCAD run40584565827: the05:00H2 confirmation selected a June3 V at1.86271 using generic nearest-level selection. It was a real LIMIT with later fill, not a market order at breakout close; nevertheless it referenced the wrong level. The event points to turn9d12327cad04eac46631ae3e, whose A is1.86124, already flipped on the earlier03:00 candle. A later external-break announcement must not invent a fresh breakout of an already-flipped level.

Commit4232a09 resolves an event's exact level-ID or turn-ID→A/V link, checks same instrument/timeframe, availability before the candle, old opposing role, new directional role and closing beyond the referenced price. Missing/ambiguous/contradictory links are reported unresolved, with no nearest fallback. Existing declared gap-break handling is preserved. Tests cover buy/sell, direct/turn links, no fill before retest, future invariance and invalid references. Older synthetic BO fixtures were corrected to represent an actual V→SELL flip rather than an already-SELL A.

## Engulfing: protect the current entry confirmation

The USDCHF second engulfing entry must not inherit the first engulfing's deep low merely because H4 context remains valid. Commit9ac7a74 scopes adjacent-engulfing risk to its own reference/engulf pair (+following candle for delayed IRL route), with context provenance separate. Nearby structure protection remains; context-only old range links are not automatically risk proof. Run40583792823 changed the same order stop0.79647→0.79803; Bishop drawing0.79783 allowed2pips more room. Different source/bot entries still prohibit an exact-match claim.

## “4th man” is a pattern, not H4

BUY: sweep the previous candle LOW, close back inside its range, prior HIGH remains unswept. SELL mirrors it. Do not relabel this as same-timeframe engulfing or impose an extra lower-timeframe engulfing on every entry.

USDCAD H1 source1676.8–1686.5 shows this pattern; he then personally added M30 engulfing before final entry. The bot's16:00H1 plan proposed1.39587 versus his final M30 stop1.39589, but conflicting target contexts held the bot plan. Preserve that held status and extra source confirmation; do not call it an executed standalone H1 fourth-man order. Target-context disagreement remains a separate unresolved issue.

## Stops and broker differences

Match the entry confirmation/episode first, then inspect its relevant wick and nearby structure. Do not use the first pattern's stop for a later pattern, globally remove legitimate liquidity protection, force fixed10–11pip stops into every source trade, or require exact FOREXcom/IC prices. Source labels, bot plans and actual simulated fills are separate facts. GBPCAD BO stop scope remains unresolved pending the correct breakout-level entry replay; the engulf-only fix did not certify BO stop placement.

### Verification of exact A/V retest correction

Final causal guards53ff2dc also require breakout event's candle ID/occurrence end to match the actual confirmation candle, and filter unpublished levels before testing link ambiguity. Reviewer reproduced both corner cases before correction; tests now cover them.

GitHub40586612929:484passed,5skipped. Frozen replay40586614121: first selected June9H2 BO order waits at the exact A1.86179 after05:00close, fills later06:05–06:10UTC. Source entry1.86183 is0.4pip away, without source-price fitting. Stop remains1.85847 against source1.86041; do not claim the remaining BO stop mismatch is solved. Evidence chart and raw outputs are preserved in reports/visual_review/breakout_retest_correction and reports/implementation_review/primary_video_40586614121.

### Owner resolution of the GBPCAD stop comparison

After reviewing the corrected entry chart, the owner explicitly confirmed that
the bot's deeper stop is a logical stop for this breakout. The numerical gap is
therefore an explained choice of protection reference, not an open engine-stop
defect for this case. The owner interprets Bishop's particular tighter stop as
using the engulfing reference visible on FOREXcom; that rationale is an owner
chart interpretation and is not independently confirmed from IC candles. Do
not require engulfing stops for all breakouts or alter the logical breakout
stop merely to match the position box. Earlier frozen reports' UNRESOLVED label
is superseded by this owner decision; exact cross-feed trade identity remains
unverified.

### USDCAD target-conflict investigation: history and confirmation paths

The old40day replay lacked resolved Weekly context at the4th-man confirmation. The frozen input already contains a year of history. W/D-only analysis is insufficient because it omits Bishop's Weekly→Daily engulf→H4 structural confirmation path. Including W,D,H4 with full frozen history resolves Weekly BUY (May8confirmed ROOT cascade), and June5Weekly /June11Daily structural reads are BUY, agreeing directionally with the mentor's narration. This is context evidence, not permission to choose a target or force an order. Full-engine rerun is required before declaring the held target conflict fixed.

### USDCAD target-conflict cause isolated on GitHub

Run40649467858 reproduced every original stop/target for all38 held H1 candidates with the actual risk planner, then changed only current Weekly context to full-history BUY. Targets1.39726/1.40240 became one common1.40240; all stops remained1.39587. This is a demonstrated input-context cause, not a reason to loosen risk logic. No order was submitted in this diagnostic. Full engine40648721296 hit300second runtime cap; order-book/fill validation with full history remains outstanding. A workflow success around ABORTED_RUNTIME is not a successful strategy replay.

### Completed full-history USDCAD replay

GitHub40682098812 (0bcdd70) completed and saved its full audit. All130 source-clock H1 fourth-man BUY candidates now share entry1.39680, SL1.39587, target1.40240: the prior context-driven target conflict is resolved. No H1 order was submitted: all candidates hit the unchanged10-slot exposure cap. This remains an execution/portfolio validation limitation, not a matched teacher trade. Investigate finer execution data for earlier reserved/censored exposure; do not raise the cap or erase uncertainty to force selection. GitHub regression40681932479 passed511 tests with5 skipped. Bounded replay40681944363 remains exactly equal across all29 sections to baseline40652436745.

### M1 refinement and terminal-close execution proof

Read-only IC collection40684156297 produced8367 M1 bars with93 missing minutes.130 complete hourly rolls exactly match the frozen H1 feed;11 incomplete hours retain unknown slots and observed-price bounds checks. No bar imputation or fallback was used. Environment/source identity and monotone availability are verified.

Full M1 run40684679119 resolved one original uncertainty to LOSS and exposed a simulator over-censor: five newly filled LIMIT orders close beyond target with no stop hit, which proves target contact after entry.424033c implements that narrow closing-price proof with SELL spread adjustment, preserves other censoring, and versions execution/run identity. Independent review found no blocker; GitHub40686939279 passed529 tests,5 skipped.

Corrected full M1 replay40686940103 completed. Six of the original nine unknowns are resolved (5WIN,1LOSS);3 still need intrabar ordering. Seven later selected orders hit M1 gaps. These10 reservations still hold the source-clock H1 entry under the unchanged cap. All130 source-clock setup records are exactly unchanged against full-history40682098812. Entry1.39680/SL1.39587/target1.40240 remains a detected eligible plan, not a placed teacher-equivalent order. Preserve this distinction. Next evidence: finer quote ordering and gap/session coverage; no numeric fitting or cap relaxation.

### Completed quote/H1 proof replay: held H1 entry now fills

Tick audit40691550808 (40read-only requests) verifies the three unresolved M1 minutes exactly. One target follows entry; two target touches precede entry and require continuation of the filled position. Same-millisecond ambiguity remains unknown. All93 missing M1 minutes return no BID/ASK updates; no market-closure inference or replacement candles are used.

D545e00 adds immutable quote evidence and published H1 no-touch bounds to both cap and final simulation. Dependent events wait for the H1 proof's availability. Position-changing actions inside gaps remain censored; known pending expiry bounds the interval requiring price data. Independent review found no remaining blocker. Regression40693590069:553passed,5skipped.

Full replay40693590233 completes. Original9 uncertain orders resolve8WIN/1LOSS;7gap-affected pending orders expire. All130 source-clock H1 setup records remain exactly unchanged. Canonical BUY LIMIT entry1.39680/SL1.39587/target1.40240 fills June12 16:13–16:14UTC and is OPEN atJune13 cutoff. Exposure cap remains10. Bishop's additional M30 engulfing keeps exact teacher-trade identity unverified.

The broader exploratory zero-cost run is not strategy acceptance:72orders,22WIN/25LOSS/15EXPIRED/1CENSORED/9OPEN;47closed trades total-11.767R. Do not hide this result behind the example's successful paper placement or fit risk rules to produce wins. Selection/target fidelity still requires source-led review.

### Selection/target source audit after execution recovery

Audit40705312536 reads every selected order from frozen run40693590233.57weekly-aligned orders account for-10.882R closed and15counterweekly orders for-.885R; counterweekly small targets are not the sole loss explanation.29of72 plans offer<1R and8offer<.1R, as descriptive counts only.36 exact H4 contexts expose standing ERL objectives:25same and11different targets.28exact context links remain unresolved; no same-event seed ranges resolve them, so turn/parent lineage remains to study.7 other scopes already delivered their endpoints; that is not an origin invalidation.

Primary sourcev16@1098.8–1155.3 keeps an H4 exit KL for an H1 trigger; repeating@594.1–649.9 chooses the objective before H4/H1 descent. T3@389.1–456.7 separately allows a nearby H1 ERL. Universal entry-TF ERL and any-opposite-role-level guard are implementation choices, not established rules covering every source route. Keep story destination/context objective/entry ERL/countertrend obstacle distinct.

Five OC subtype pairs have identical economic geometry and current protection, but different canonical story/cancellation lineage; they are not blindly merged. A further standing/engulf numeric pair has different proof. No minRR, outcome-selected target or blanket counterweekly ban was added.

b27023b fixes unordered range versions resurrecting an older state, with last-input exact-clock ties preserved. Independent review found no blocker; GitHub40703689363 passes555tests,5skipped. Normal production ordering means this is not claimed to erase the observed loss. Detailed source references and limitations are in TARGET_SELECTION_AUDIT.md.

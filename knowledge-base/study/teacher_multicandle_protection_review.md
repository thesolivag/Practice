# Multi-candle sweep-to-reaction protection review

2026-10-24. Source-only review of the USDCAD p15 diagnostic. No engine/fixture changes, market-data acquisition, outcome-derived threshold or matching-price adjustment. Source references below were reread directly in canonical transcripts; relevant native frames were inspected in the preceding protection audit. This review does not independently verify the supplied alternate-feed timestamps/OHLC.

## Finding

A lower-TF BO does not automatically become the entire protection episode simply because it is the last confirmation. The source supports preserving a **relevant sweep/origin extreme across the same sweep→KL reaction→confirmation sequence**, even when the extreme occurs before the final reaction candle or BO child formation. Conversely, neither a common H4 ancestor nor mere age proves that every earlier extreme belongs to this entry's protection.

For the specified alternate-feed sequence, the01–02 first take and02–03 higher high are **candidate members of the same reaction/sweep episode** if they take/extend the same eligible liquidity leg at the same context KL, and the03–04/04–05 rejection plus07UTC BO are causally descended from that leg with no intervening episode invalidation/replacement. Under that proved relationship, protecting only the later rejection/BO high drops a relevant part of the originating excursion. The source supports correcting that lost scope relationship. It does not prove that a universal min/max from the first take to every later BO is the teacher's exact formula.

The BO child's local protection remains a different source-permitted/operating alternative when independently selected. It must not be silently presented as protection of the complete parent sweep episode. A linked full-episode extreme and a local BO formation are distinguishable policies, not interchangeable labels for whichever price matches the chart box.

## Direct source grounds

Paths below are under `knowledge-base/videos/`.

| Source and exact range | Direct quote/observation | Implication and limit |
|---|---|---|
| `video-13-bias-continuation-part-2/transcript.txt`307–332 | “If I'm entering here … below this particular low”; “Even if I was entering at the same V-shaped key level … at this particular low”; shallower return still safe “below the week [wick].” | Entry-price refinement does not erase the associated formation's protective extreme. No universal arbitrary parent-range inheritance. |
| Same source1835–1857,1903–1918 | Origin has “a sweep … a break … internal range liquidity … QMR”; safer above “the strong high that was actually created.” | The current originating sweep/structure sequence, not solely the final entry candle, supplies relevant protection. Native source1848s shows this as a connected schematic sweep-high→break→QMR return. |
| Same source1955–1973,2055–2114,2142–2156 | Student entered lower KL, stop beyond higher KL while “there was still another high”; stopped. Teacher: above referenced high plus “one … or0.5”pip. | Moving beyond a nearby KL does not necessarily protect the stronger known origin. It does not identify an unbounded historical high or prove every loss is a mistake. |
| `video-14-entry-models-1/transcript.txt`221.7–263.7 | CE follows price “after taking out an internal range liquidity,” playing from the KL; this is “the origin of a trade.” | The CE is downstream of a liquidity/reaction event, so full current-origin protection can differ from the child BO extreme. The quote alone does not define a numerical episode boundary. |
| Same source593.7–616.7 | Broken OC return; stop above “this particular high,” still discussing “this origin.” | A shallow broken-OC entry can retain its source-origin high. |
| Same source1185–1207 | First and second Gold entries each reference their relevant low. | A genuinely new entry formation may have its own protection. Do not force every later continuation to reuse the first trade's extreme. |
| `bishop-defi-bishop-study-20-minute-series-part-1-repeating-a-system-that-works-an-approach-to-tra/transcript.txt`242.4–263.9,263.9–355.9 | Liquidity taken→rejection→lower-TF confirmation; “not all the time … a single candle … more than one candle … series of candles”; may be structural liquidity. | The liquidity/reaction framework is not intrinsically a one-candle event. This passage concerns formation/representation of liquidity, not a standalone command to include all candles in a stop. |
| `bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/transcript.txt`293.6–340.7 | Wait for H4 liquidity, trade into relevant KL, reaction; waiting for rejecting candle close is “your choice.” | Reaction identity is a contextual process. A complete H4 candle cannot be presumed known before its actual close; intrabar entry requires then-known finer observations. |
| `bishop-defi-bishop-study-20-minute-series-part-3-trades-breakdown-bias-to-entry-case-study-gb/transcript.txt`1287.7–1304.5,1339.7–1348.1 | Why not immediately above engulf high? “price has every right to come to this liquidity”; stop above nearby H4 liquidity/KL. | Explicitly permits wider relevant contextual protection beyond child pattern. Native1298/1344s show nearby H4 reference protected while older higher highs remain outside; not blanket H4 max. |

Native frames already extracted/inspected in `protection_scope_source_audit.md`: `/tmp/protection-v13-1848.png`, `/tmp/protection-t3-1298.png`, `/tmp/protection-t3-1344.png`. Durable sources are the cited native video PTS and corrected contact sheets (`video-13-bias-continuation-part-2`sheet032; canonical Bishop Part3 sheets022–023). This review adds no claimed native-frame precision to a deictic quote beyond those actually inspected.

## Required lineage before adding an earlier excursion extreme

The following is a proposed causal implementation contract derived from the source distinctions, not a teacher-specified numerical algorithm:

1. **Freeze context identity:** selected story and parent context break/range epoch, side, specific usable KL/role epoch and expected liquidity pool/structural leg, each available before the relevant occurrence. Common symbol/timeframe or common broad H4 ancestor is insufficient.
2. **Record first take and extension chain:** first witnessed passage of that designated liquidity pool, followed by ordered further excursion observations belonging to the same reaction leg. A later higher high/lower low can extend the leg even when the later candle is not the first pool take. Retain occurrence bounds and availability for every extension.
3. **Link actual KL reaction:** the rejecting/reaction bar(s) must react from the same designated context KL/role/episode. A later rejection need not sweep the same pool again. Preserve first-take ID and all episode-extreme contributor IDs rather than replacing the chain with the latest reaction candle.
4. **Link child confirmation:** BO or sweep+BOS must be positively related to this reaction and frozen structural references, not an old unrelated BO. Its child formation can supply an additional local protection candidate but must not silently redefine the parent's episode start. A reaction linkage already accepted for entry context should survive into risk provenance.
5. **Define causal termination/replacement:** coverage gaps, known role loss, protected-scope break or a new independently eligible reaction/continuation sequence can stop that association. If the teacher does not uniquely define a boundary, name the engine's rule; do not pick a fixed bar count, ATR distance or price threshold from this result.
6. **Freeze at availability/placement:** the protective excursion extreme uses only episode observations available when that plan becomes eligible. Future highs/lows never rewrite its initial stop. If a later continuation chooses a fresh episode, emit a new setup with new lineage. Changes to a pending or filled plan need timestamped amendments, not retrospective replacement.

For a full-episode structural profile, choose the outward extreme over **only the linked excursion/formation observations** and add the declared padding. Store which observation supplied that extreme and why it belongs. For a selected child-local or aggressive fixed profile, report that narrower scope separately and disclose known larger related liquidity exposure. The exact inclusion rule and padding remain engineering choices until source cases verify them. No reviewed source mandates that every CE use full-episode protection; the important correction is not to claim full protection while silently discarding its connected origin.

## Application to supplied alternate-feed numbers

The reported07UTC candidate is1.40425/1.40521/1.40249, while PDFp15 displays1.40471/1.40539/1.40129. The supplied diagnostic says first take01–02 high1.40499, extension02–03 high1.40538, later reactions03–04/04–05 and child BO high1.40516. This review does not independently certify those feed observations.

If all those observations pass the same-episode lineage conditions,1.40538 is a relevant **unbuffered full-episode high candidate** that a latest-reaction/BO-only stop omits. It is not automatically the correct source stop or proof of a price match. Retaining the stated five-tick padding on an assumed0.00001tick grid would produce1.40543, **not** the source1.40539. Selecting one tick simply to reach the source number would be fitting; source-specific buffer rationale/feed differences remain unresolved. The discrepancy also includes entry and target, so repairing stop scope alone cannot certify this candidate as the PDF entry.

Actual PDFp15 was independently rendered/inspected in the prior audit. It labels H1 breakout CE and H4-with-idm/H4rH4; printed stop1.40539 is a plan coordinate, not a narrated mechanical definition of the exact wick/candle or padding. An actual source-FOREXCOM candle/episode reconstruction must establish those facts. Alternate-feed resemblance and a convenient high do not replace it.

## Protection critique versus an accepted system loss

The distinction is the decision's demonstrated rule facts, not whether a wider stop would later have won:

- **Teacher's stronger-high critique:** Core13 identifies an already-relevant stronger high above the student's chosen KL protection. Bishop T3 GBPUSD identifies known nearby H4 liquidity that price can normally revisit. These nominate preentry protection information. Only aligned source evidence can prove the original plan actually failed its selected protection policy; retain all narrower losing accounts and wider surviving accounts.
- **Accepted selected-system loss:** T3 AUDCHF577.9–677.3 narrates W/D bullish, H4 breakout/liquidity, H1 engulf and a loss.636.6–647.5: “I don't actually use that … if that was the reason why I took a loss, then that's fine by me.” This rejects adding an external-breakout veto merely because of the result. No source-specific protection omission is established there.
- **Unresolved compliance:** No diagnosed mistake is not proof of perfect compliance, and “unavoidable” is too strong without all clocks/risk facts. Conversely a stopped trade alone does not identify which omitted extreme was relevant. Record `teacher_identified_candidate_deviation`, `accepted_selected_system_loss`, or `unresolved`, then verify preentry facts rather than converting every loss into a new filter.

The supported investigation is therefore **continuous, proven current-episode protection lineage** versus **selected child-local protection**, with case-specific source mapping. It is not ATR tuning, universal H4-extreme protection, automatic retries, or a rule that no compliant trade may lose.

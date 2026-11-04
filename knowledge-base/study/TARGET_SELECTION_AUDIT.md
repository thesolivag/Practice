# Target timeframe and selected-order audit

This is a source-fidelity review of the completed USDCAD run40693590233. It is not a parameter search, a new backtest, or evidence that all losing trades were mentor mistakes.

## Source findings

1. `bishop-repeating-system/transcript.txt`594.1–649.9 identifies the objective before moving down to H4 and then H1 confirmation. An entry trigger does not automatically redefine the target timeframe.
2. `video-16-storyline-1/transcript.txt`1098.8–1117.2 explicitly distinguishes the newly created H1 entry KL from the H4 exit KL.1150.1–1155.3 identifies the H4 OC as the first target.1548.4–1600.2 separately discusses H4 ERL first and a farther Weekly storyline objective.
3. `bishop-trades-breakdown-3/transcript.txt`389.1–456.7 permits a nearby H1 ERL instead of a slightly farther objective and describes discretionary front-running. This preserves a lower-timeframe exception; it does not establish a universal numeric offset or automatic override.
4. `bishop-defi-bishop-study-10-minute-series-part-1-bias-entries-amp-confirmation-entries-combined/transcript.txt`319.4–337.6 supports nearest ERL as a personal target preference. It does not establish that every entry must target the smallest containing range on the final entry timeframe.
5. `bishop-building-bias-2/transcript.txt`815.7–928.7 describes exiting a counter-structure move at the identified intervening liquidity/KL before assuming delivery through the entire dominant range. Neither that passage nor the routine/what-next examples establishes that every opposite-role candle junction across all timeframes is the intended obstacle.
6. `bishop-daily-routine/transcript.txt`393.2–427.9 and what-next455.2–480.0 explicitly permit counterweekly Daily/H4 routes. No universal ban or minimum R threshold was found.

All paths above are relative to knowledge-base/videos. These are primary transcripts; the student-compiled Bishop examples remain a separate evidence source.

## Actual completed portfolio denominator

All72 selected orders are included:22WIN,25LOSS,15EXPIRED,1CENSORED,9OPEN.47closed trades total-11.767R under the explicit zero-cost hypothesis. Unresolved/open trades prevent treating this as complete performance.

- 57 weekly-aligned orders contribute-10.882R closed;15 counterweekly orders contribute-0.885R closed. The bulk of the observed loss is therefore in aligned entries, not explained solely by the counterweekly guard.
- 29 plans have reward below1R, eight below0.1R. These are descriptive audit bins, not rejection rules.
- The nearer-KL guard changes15 plans. Only two final guard IDs belong to the H4 level set. Other timeframes are not automatically invalid: each intended target must be qualified against the source route.
- The exact-parent-scope diagnostic finds36 known standing H4 ERL objectives:25 agree with the selected target and11 differ. The remaining cases need explicit scope/seed or endpoint-delivery resolution. None is silently assigned a replacement target. A differing candidate is a source-review flag, not proof that the selected target is wrong. No consumed-endpoint-as-intact defect was established.
- Five pairs of orders share economic prices/time/TF and both OC classifications, with matching current confirmation/protection proof. Their canonical story IDs differ. A sixth numerical pair combines standing-extreme and engulfing with different proof. Numerical equality alone does not authorize merging positions with different cancellation dependencies.

## Implementation conclusions

`entry_erl` currently means nearest endpoint of the narrowest containing entry-TF range. It is an existing owner-policy choice, not a universal transcription of Bishop. The counterweekly guard currently considers current opposite-role levels across all TFs. These choices require route/context qualification before promotion as mentor-faithful defaults.

Keep four fields distinct in a future target plan: storyline destination, sponsoring-context objective, terminal-entry ERL, and countertrend obstacle. Record timeframe, range/episode link, publication, intact/consumed state and source route. Lower-timeframe replacement needs an explicitly selected route. Do not replace every target with story.destination_ticks: some current story destinations are behind entry or unknown, and source H4-first objectives can differ from the final Weekly destination.

A local H4 breakout may have no event.scope_id and still have an explicitly seeded range. The diagnostic records seed-linked alternatives without ranking them. In this72-order sample,28 sponsoring breaks have no exact range link and none has a saved range explicitly seeded by that same event. Further turn/parent lineage is required before classifying those28 entries as missing context; the valid USDCAD H1 example is among them. An endpoint marked delivered is not an origin invalidation; neither justifies deleting a source-compatible continuation by itself.

## Concrete code fix and verification

The risk API previously took the last input range version, even when it was older than an already seen published BROKEN state. It now selects greatest available_at<=submission, preserving last-input behavior only for exact-clock ties. Two permutation regressions cover both tuple orders. Production structures are normally ordered, so this fix is not claimed to explain or remove the observed loss.

Independent source and code reviewers found no blocker in this fix. GitHub regression40703689363:555passed,5skipped. Source-scope audit40703689879 succeeded; updated diagnostic40705312536 separates delivered endpoints from origin invalidation and exposes seed alternatives. No target prices, stops, costs, exposure cap, source fixture, counterweekly permission or model priority has been tuned from outcomes.

## Preserved run

Final updated audit40705312536 completed successfully (artifact12821979736). Full selected-order evidence is in reports/implementation_review/usdcad_target_40705312536/audit.json. Source run remains40693590233; no strategy or execution rerun was used to generate better performance.

## Opt-in context-objective implementation

`StrategyPolicy(target_profile='context_objective')` now carries an immutable explicit H4 sponsoring-scope objective from reaction publication into the entry risk plan. It records story destination, context objective, entry ERL candidates and qualified countertrend obstacle separately. Existing default target policies remain unchanged. Missing scope, unpublished/consumed objective, broken origin or unobserved interval holds the plan; it never borrows an unrelated containing range. Published child candles can consume an ERL before the H4 candle closes. Ordinary KL contact does not automatically retire a reusable level.

This is partial, experimental coverage, not completed mentor validation. Production structure currently does not publish the explicit `target_level_id` / `opposing_level_id` links required by this API for KL objectives, nor a qualified countertrend obstacle. Consequently the current production integration holds counterweekly ERL plans in this opt-in mode. Synthetic tests show that explicitly supplied qualified KL objectives/obstacles work; they do not demonstrate historical teacher-example matches. H4 sponsors without exact scope and direct routes without an identified reaction also remain unresolved. Source-backed lineage/link production is required before adoption. The existing `entry_erl` policy remains the explicit lower-timeframe route; no numerical proximity exception is invented.

Focused verification covers objective carry over a nearer H1 ERL, unchanged stop geometry, missing-context hold, qualified/cross-scope countertrend obstacles, causal publications, child-candle consumption and range-version permutations. These are semantic unit checks, not profitability or teacher-replay acceptance.

## Explicit H4 key-level route

`context_h4_kl` implements the distinct v16 1098.8–1155.3 route: nearest known H4 A/V/OC ahead of the actual planned entry, with current opposing role. It excludes terminal-entry-TF junctions, future levels, unavailable levels and same-direction roles. The chosen ID, price, current role, formation evidence, publication and source route are recorded. Subsequent role loss holds the snapshot; ordinary contact alone does not retire a reusable KL. A known same-direction H4 sponsoring break is required. Missing range scope remains missing and is not inferred from containment; the cited teaching does not require artificial range metadata. This supplies a production KL path, including a qualified first countertrend exit, without replacing the distinct context ERL route or the existing defaults.

The previous paragraph's production KL limitation applies specifically to `context_objective`, whose explicit range-link procedure is retained. `context_h4_kl` is separately selectable in the primary-video GitHub replay. Both require historical mentor-example validation; successful unit/regression checks alone do not establish that validation. Regression40730298538 for the preceding context-objective commit completed with572passed,5skipped.

### Source and verification record for the H4-KL route

- Transcript: `knowledge-base/videos/video-16-storyline-1/transcript.txt`,1098.8–1155.3; separate ERL teaching1548.4–1598.9.
- Visually inspected `knowledge-base/frames/video-16-storyline-1/sheets/sheet_020.jpg`:1140/1155/1170/1185seconds. The frame is Bishop's schematic teaching, not a dated historical trade or a numerical target fixture.
- Nearest H4 exit from the known entry and exclusion of newly created H1 entry KL are source rules. Known same-direction sponsoring-break requirement and deterministic same-price ID tie handling are implementation safeguards. No containing range, maximum age or quantitative proximity rule is invented.
- Commit42846f8: independent source/code review found no blocker;40focused checks pass, including detector-level successive engulfings for BUY/SELL and unchanged current-confirmation stop geometry. GitHub regression40731698879:579passed,5skipped.
- Full-frozen-context USDCAD diagnostic40731711578 explicitly selects `context_h4_kl`; its execution feed is H1, so performance is not directly comparable with the prior M1/tick-refined execution run. Teacher identity remains unverified.

Full-context H4-KL run40731711578 reached the600-second timer: preprocessing126.3seconds and detection410.3seconds completed; execution/serialization did not finish. GitHub's successful job status means the diagnostic artifacts uploaded, not a completed replay. Its summary explicitly says `ABORTED_RUNTIME`. The small timing/sample/plan artifacts are preserved under `reports/implementation_review/h4_kl_40731711578/`. A separately labelled detection-only mode now returns all detected plans before selection/execution; a nonempty synthetic pipeline check confirms exact plan equality with normal mode and forbids simulation calls. It makes no fill, outcome or profitability claim.

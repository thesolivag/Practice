# USDCAD firsthand target-route recheck

Source: `bishop-defi-bishop-study-20-minute-series-part-3-trades-breakdown-bias-to-entry-case-study-gb`, video SHA256 `ee73e7118df31d1f30524a204ffe5393bbfc05b87197f935fe01bd4687d45004`.

Re-read transcript1633.6–1735.3 and visually inspected contact sheet029 (1680/1695/1710/1725seconds). This is a historical trade breakdown, unlike the schematic v16 target teaching.

## What Bishop actually describes

1. The larger bullish idea survives the contrary local breakout.
2. He personally deleted the original H2 limit when skeptical of the downside break (1646.8–1656.6).
3. He then required additional H1 confirmation: breakout, rejection, previous H1 low swept with its high standing (1656.6–1682.6).
4. He shows an additional M30 engulfing for his final personal entry (1682.6 onward, chart switches to30minutes).
5. He explicitly says he is targeting **liquidity** (1695.5–1708.2). The final1725second frame displays that target on H4.
6. He says the trade is still open (1713.5–1719.5). The video does not establish a final win/loss.

## Consequences for implementation and audit

The v16 nearest-H4-KL exit is a distinct source route. It must not universally replace this narrated liquidity objective. Run40733956053 explicitly exercises `context_h4_kl` as a diagnostic comparison; neither a better score nor a nearer target would establish that it reproduces this trade.

The prior IC H1 source-clock candidate has entry1.39680, stop1.39587 and target1.40240. The final source drawing appears close to those prices, but cross-feed numeric proximity does not establish the final M30 entry mechanism, verified fill time or sponsoring-objective lineage. No source fixture/tolerance is changed from these readings.

The remaining mechanical checks are the actual M30 confirmation, its relationship to the H1 standing-high sweep, and the explicit external-liquidity/context link. H1-only detection cannot establish the M30 step. The frozen IC M1 archive coversJune5–13 and may support a later separate M30 aggregation, subject to its known missing-minute/coverage checks. Its previous execution-only use does not mean it has already been used as an entry-detection feed.

No stop, target, source outcome or route is fitted to a winning replay. Missing source-context links remain unresolved, rather than assigned a nearest unrelated range.

## Frozen M30 geometry and corrected nested implementation

`reports/implementation_review/usdcad_m30_source_audit/geometry.json` records a small aggregation/geometry inspection of the existing frozen M1 archive, not a strategy backtest. All ten M30 candles in the declared June12 13:00–18:00UTC exploratory window are complete and share the same data segment. The 15:00 candle (O1.39679/C1.39619/L1.39592) and15:30 candle (O1.39618/C1.39711/L1.39603) satisfy the existing bullish engulf predicate, published together with the H1 confirmation at16:00UTC. Overall archive coverage remains partial; no absent minute is synthesized.

The opt-in nested-confirmation detector previously required the lower engulf candle to **start** after the H1 standing candle ended. This unnecessarily excluded a lower confirmation completing with its parent. It now permits the same close while requiring the lower pair to be adjacent, in the same segment, and not close before the parent. Submission still waits for every dependency's publication. Parent validity is rechecked through final submission when H1 publication is delayed.

The nested route now gives risk planning only its current lower engulf pair as confirmation stop protection. H1/H4 and earlier reaction candles remain causal/context evidence rather than automatically widening the final M30 stop. Synthetic detector regressions cover simultaneous close, later lower confirmation, earlier/unpublished rejection, delayed H1 publication, parent failure during that delay and local-pair stop protection. Independent review found no remaining blocker. These tests are not a completed historical M30 replay.

Mixed H1-context/M1-child detection input remains to be connected with compatible gap/segment provenance. Equal segment IDs from different feed histories must not be assumed equivalent. The currently running H1-only target audit cannot establish this final nested chain.

## Completed target audit40733956053

The full-history detection-only report completed:25,310setup/context variants,12,056eligible and13,254unresolved. These are hypothetical variants, **not orders or daily trade counts**; selection/execution were not run. All122 source-clock H1 standing variants retain entry1.39680 and stop1.39587, while the explicit H4-KL route targets1.39838. The prior liquidity plan targets1.40240. This difference confirms why these source routes must remain distinct; the nearest KL must not replace Bishop's explicitly narrated liquidity target here.

Prior source-clock variants numbered130 and the new run has122; total story counts differ5393versus5390. Economic geometry equality does not establish lineage equivalence. The eight-variant difference is flagged for independent policy/lineage review; no teacher fixture is altered or match awarded. Compact evidence includes every current source-clock candidate and its selected objective under `reports/implementation_review/h4_kl_detection_40733956053/source_clock_comparison.json`; the complete result remains in GitHub artifact12835244714 with hashes recorded in provenance.

Independent lineage review identified policy-sensitive tie choices: structure IDs include the full policy identity, while `stories._confirm` and weekly direct/cascade selection can resolve same-clock alternatives by event ID. Changing the target profile can therefore change a structural/story choice even though `find_stories` does not directly read target_profile. Other range/parent tie sites also use such IDs. This is a concrete isolation concern, but exact attribution of the eight source-clock variants has not yet been demonstrated. A semantic tie/identity regression is required before claiming route-only lineage equivalence; no arbitrary route priority is introduced to force the old count.

The nested timing/stop commit3a63763 passed GitHub regression40735509827:585passed,5skipped. This verifies the code checks, not a historical final-M30 entry match.

# Liquidity-bias identity and environment coupling

This is a verified implementation boundary, not a claim that all Bishop liquidity examples now match.

## Source contract

- Building Bias Part2 (`bishop-building-bias-2/transcript.txt`)30.9–140.2: higher-timeframe liquidity sweep, candle closure, then next-timeframe breakout/BOS.
- 408.7–490.7: a Weekly low sweep is not an automatic buy to the high; Daily must confirm. Daily-to-H4 follows the same logic.
- 211.2–309.2: internal/external role depends on structural context, rather than every high/low having a universal role.
- 815.7–928.7: an opposing sweep can be a retracement within existing structure. First exit may be intervening liquidity/KL, not the opposite candle extreme.
- 1137–1205: higher-timeframe single-candle liquidity can correspond to lower-timeframe structural liquidity.
-Firsthand T3 breakdown, fullslug `bishop-defi-bishop-study-20-minute-series-part-3-trades-breakdown-bias-to-entry-case-study-gb`,64.8–124.7 and313.9–386.3: both bias origins feed lower-timeframe confirmation, then H4 liquidity, H4 rejection and entry confirmation. Team frame review sheet006 shows the Daily rejection and H4 structural/candle sequence; no new numerical entry acceptance is inferred from it.

## Implemented now

`PRIOR_CANDLE_SWEEP` publishes a stable named source-candle wick identity with instrument, timeframe, source bar, formation/publication clocks, kind and price. Existing known BAR/PRIOR_PERIOD pool IDs are retained as aliases when their price, side and source bar match. This is the adjacent single-candle subtype, not every liquidity form.

Its structural environment is frozen at the first observed lower-timeframe sweep-contact start. Where no such observation exists, the origin-bar start is an explicitly labelled conservative earlier cutoff. Future range states cannot rewrite this snapshot. Defined root-range direction remains distinct from the latest internal break. Same-clock contradictory root snapshots yield UNKNOWN, in cached and plain paths.

IRL/ERL remains UNKNOWN without positive role evidence. ERL is assigned only when a uniquely identified defined root's known, confirmed and undelivered endpoint pool matches the source wick and contains its source bar. Mere equal price or containment does not establish the role. No IRL is inferred by distance or invented significance.

The opposite candle wick is recorded only as an unselected candidate. It is explicitly marked TAKEN if the sweep candle has already taken that opposite extreme; otherwise NOT_OBSERVED_TAKEN. It is never promoted to an external-liquidity objective merely because it is opposite the swept wick.

The owner's required `last_pre_touch` confirmation applies to both KL-rejection and liquidity origins: freeze the lower A/V before the corresponding contact, and require its actual break. Liquidity does not require an HTF key level to exist. A previous source candle unpublished at first sweep cannot qualify strict bias. The older `source_lineage` behavior remains an explicit diagnostic alternative. The strict Weekly liquidity route cannot bypass its Daily external confirmation through a Daily-engulf/H4 cascade.

## Preserved unresolved behavior

Legacy story destination and lifecycle remain unchanged as requested. Their nearest opposing origin KL is now explicitly labelled KEY_LEVEL_EXIT_CANDIDATE and external-liquidity destination status UNRESOLVED on liquidity stories. It is not advertised as a qualified external-liquidity objective. Completing setup-specific significant liquidity and first-obstacle selection remains necessary.

These changes do not integrate all H4 BAR/SERIES/structural inducement identities into HTF bias, prove every cross-timeframe single-candle/structural mapping, or establish historical teacher-trade acceptance. Structural environment UNKNOWN does not disable an otherwise positively confirmed liquidity bias.

## Verification

`tests/test_liquidity_bias_identity.py` verifies source identity, strict BUY/SELL liquidity confirmation without any HTF KL, pre-contact/future cutoff, internal-break versus root direction, same-clock conflicting snapshots under both cache paths, equal-price non-identity rejection, taken opposite candidates, published pool aliases and delayed source publication. Existing strict-reference and cache-equivalence suites are included in focused verification. No historical fixtures or outcomes are fitted.

## Qualified destinations and separate first exits (2026-10-28)

Re-read primary Part2 transcript 815.7–928.7 and 947–987. Bishop explicitly keeps the structural direction separate from a counterstructure sweep; at 910.7–919.7 he calls the intervening liquidity/key level the first exit and says price can resume buys. A sweep of a high does not guarantee delivery to the opposite low (921.7–928.7). This supports separating the first obstacle from the overall objective, not promising opposite-candle delivery.

Story destination selection now replaces the legacy KL destination **when positive overall evidence exists**: a unique, unambiguous known DEFINED root in story direction, confirmed undelivered endpoint stage, matching endpoint price and named liquidity pool, correct timeframe/instrument, in front of current price, with observed source-timeframe bars and no already-observed taking of that pool since formation. Future pools, broken/provisional endpoints, counterstructure roots and contradictory root versions cannot qualify. No raw nearest BAR wick is promoted by distance.

The nearest opposing source-qualified KL or qualified root endpoint is separately recorded as `first_obstacle`; a distinct nearer obstacle produces `STORY_FIRST_OBSTACLE_REACHED` with no cancellation and no retirement of the overall story. The named overall endpoint still drives `STORY_DESTINATION_REACHED`. When overall proof is absent, existing KL fallback/lifecycle remains explicitly KEY_LEVEL_EXIT_CANDIDATE and external objective UNRESOLVED. This fallback is not a claim that every local KL take ends all higher-timeframe market bias.

Remaining limits: qualified child-range/internal-liquidity obstacles and broader cross-timeframe significant liquidity mapping are not exhaustively enumerated here; source candle opposite wicks remain unqualified candidates. Endpoint standing checks use available observed bars; source data readiness remains the upstream qualification. This change does not establish teacher-example replay success or profitability. Actual entry target selection is a separate sponsor-scope contract.

`tests/test_story_liquidity_destinations.py` adds BUY/SELL and indexed/plain positive objective checks, causal future/taken/broken/provisional/opposite/conflicting exclusions, arbitrary nearer wick rejection, and full story proof that taking a local first obstacle does not retire the farther objective. Combined focused suites: 74 passed. Heavy teacher replay remains on GitHub Actions.

Self-review tightened standing evidence: endpoint pool source IDs must be present in known origin-timeframe bars when supplied; observations since formation must share the current declared provenance segment. Scheduled FX closures preserve that segment; elapsed wall time is not treated as missing data. Local obstacle events at or after STORY_INVALIDATED, STORY_FLIPPED or overall STORY_DESTINATION_REACHED are removed, including same-clock ambiguity. Added causal source/segment/gap and invalidation-before-obstacle regressions. Combined focused verification now 79 passed, including scheduled-weekend continuity.

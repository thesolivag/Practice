# Bias and target priority after owner review

The owner considers the reviewed entry/confirmation/logical-stop implementation approximately90–95% aligned. Preserve it as the working baseline; fix demonstrated defects without reopening the entire model on each replay. The immediate deliverables are visible market-bias comparison and setup-relevant liquidity targeting.

## Primary source basis

`knowledge-base/videos/bishop-bias-entries/transcript.txt`:

-88.2–95.7: distinguishes the **first external liquidity** from the **overall external liquidity**.
-322.7–326.2: “once the external liquidity is taken, expect a reversal.”
-326.2–337.6: describes external liquidity targets and his personal preference for the **nearest external liquidity**; explicitly says this need not be every student's choice.

`bishop-building-bias-2/transcript.txt`,211.2–242.2: internal/external movement is contextual and cyclical. A high/low's role depends on the market scenario. Therefore “nearest” must follow qualification of relevant external liquidity, not select any nearby candle wick, narrow entry range, or key-level junction.

## Implementation direction

Keep the trade's first significant external objective separate from the overall higher-timeframe destination. Record the relevant range, timeframe, known-at clock, reference and consumed state. Taking the first objective completes that objective and requires new information/reassessment before further continuation entries. The source expectation of reversal is not permission to submit an opposite order without the required bias/setup/confirmation sequence. Do not keep an old objective marked available after it is taken.

H4 key-level exits remain their separately taught route. They must not silently replace a trade explicitly targeting external liquidity. Fixed2R/3R may be tested as separate owner alternatives; the owner's spoken “two/three” has provisionally been interpreted as R, not holding hours. No fixed2R policy, holding timer, fallback target or live setting is enabled by this note.

For bias review, show actual candles with direction, selected key level/range, liquidity objective, invalidation and assessment time. Compare the selected bias with the mentor/owner's visible reading; thousands of alternative story candidates or passing unit checks do not establish this agreement.

## Kevin implementation comparison

Inspected `origin/claude-kevin-king:slk/entry.py::_setup` and `slk/research_bias_targets.py::Selector/measure_story`. Kevin separates a nearer entry target (TP1) from the overall story destination (TP2), and the research walker distinguishes subsequent target selection after target touch or continuation close. Availability and consumed-state checks are explicit.

Kevin's numeric RR windows, fallback and entry rules belong to Kevin's implementation and are not imported into Bishop. Reuse the separation of responsibilities and evidence presentation, while deriving Bishop's significance/range and reversal rules from Bishop's material.

# Coupled bias, H4 setup and entry contract

Required owner environment (applied alongside Bishop’s two bias routes): key-level bias confirmation means breaking the **last relevant lower-timeframe A/V already known before first contact with the rejecting higher-timeframe key level**. BUY freezes H/A; SELL freezes L/V. Weekly rejection requires Daily confirmation; Daily rejection requires H4 confirmation. A newer internal break alone does not flip the larger confirmed bias.

## Key-level route

1. Witness rejection at a known, correctly functioning higher-timeframe key level.
2. Freeze the last relevant one-timeframe-lower close-line A/V at the first witnessed touch candle's start. A level first confirmed during or after contact cannot be inserted retrospectively. Same-segment and publication checks apply; ambiguous anchors remain unresolved.
3. Require a fresh closed break of that exact reference. A wick, an older A/V, or a newly formed post-contact internal reference cannot substitute.
4. Record `BIAS_REFERENCE_FROZEN`, persistent `BIAS_WAIT_EXTERNAL_BREAK` where confirmation is pending, and `REACTION_CONFIRMATION_LINK` when it arrives. The waiting event remains in historical evidence after later confirmation.
5. Assess Weekly/Daily/H4 alignment from these confirmed contexts. Preserve conflicting/waiting states; do not manufacture agreement or reverse bias merely from the last raw break.

`StrategyPolicy.bias_reference_profile='last_pre_touch'` is required by default. `source_lineage` remains only a diagnostic comparison with Bishop’s narrated alternatives. The owner explicitly clarified that external-break environment is not optional. It must not replace or omit the separate liquidity bias route.


## Separate liquidity-based bias route

The candle-sweep origin remains separate from key-level rejection: it does not require a key level to exist at the sweep. Under the required model, both origins must confirm against the frozen lower-timeframe A/V. The source-comparison profile preserves linked alternatives, including the engulf cascade, only as a diagnostic. Internal/external liquidity qualification is contextual, not equivalent to every raw high/low. Sources include `bishop-building-bias-2/transcript.txt`211.2–309.2 and `bishop-bias-entries/transcript.txt`88.2–95.7,322.7–337.6.

## H4 vantage and entry

H4 inducement (single-candle, series or structural liquidity) belongs to its sponsoring break and relevant key level. An unrelated later break must not steal an explicitly declared parent. The first take, key-level rejection and subsequent confirmation must belong to the still-valid episode; a same-scope replacement, level-role loss or data discontinuity retires it.

H2, H1, M45 and M30 confirmations share this qualified H4 context; one example's timeframe does not restrict the general detector. Confirmation can close simultaneously across parent/child timeframes when all dependency clocks permit it. Entry waits for the applicable retest. Logical stop uses the actual confirmation that produced the entry. Source-specific discretionary stops remain separate. First significant external objective and overall higher-timeframe destination remain distinct.

## Verification boundaries

Regressions exercise exact frozen reference vs older/internal alternatives; BUY/SELL symmetry; W/D and D/H4 ladders; missing/ambiguous/future/gap evidence; wick-only rejection vs actual close-through; persistent waiting events; H4 parent continuity across H2/H1/M45/M30; and nested parent/child protection. These checks establish implementation invariants, not historical mentor acceptance or profitable performance. Heavy data scans/replays run on GitHub Actions.

## Owner correction — Bishop first

The owner’s latest correction supersedes the previous optional-default interpretation: the external-break environment is required in the intended model. Both key-level and liquidity origins are evaluated by default. Primary liquidity source `bishop-building-bias-2/transcript.txt`22.9–140.2 explicitly names sweep, higher-timeframe closure and next-lower-timeframe breakout; 408.7–490.7 requires lower-timeframe confirmation rather than assuming a sweep guarantees the destination. Existing prior-candle sweep detection is an implemented route, not proof of complete internal/external liquidity fidelity across the trade breakdowns. That source-to-code audit remains separate from unit regression.

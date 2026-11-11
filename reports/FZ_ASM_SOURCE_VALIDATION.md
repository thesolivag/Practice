# ASM source validation — first evidence set

Source/code baseline: `223ae4415b7d19e6f7c6caecd9e1a281c45a8dc8`. The HTML companion shows five original frames beside the implementation comparison. These are **not** reconstructed bot executions of the pictured trades. Contact-sheet resolution is insufficient for reliable exact-price or pip-offset claims.

## Findings grounded in primary material

| Finding | Primary transcript and timestamps (seconds) | Consequence |
|---|---|---|
| Wait for H1 sweep; inspect H2 if H1 does not qualify; no sweep means leave it | `asm-asm-night-live-tarding-day-one`, 2553–2588 | Supports keeping sweep as context gate, not inventing trades to fill a session. |
| After the sweep, seek a lower-timeframe market shift | Same, 2636–2691, 2724–2739 | Supports the repaired lower-timeframe route. “Take out this low” does not establish a four-bar algorithm. |
| No universal M5 -> M10 -> M15 search order established | Live session 2644–2651 and 2731–2739; `asm-all-you-need-asian-map-concept`, 1493–1506 | Live session names M5/M15; lesson expresses preference for M10/M15. Keep selection explicit; do not assert a mandatory fallback order. |
| FVG is the gap between candle 1 high and candle 3 low in the bullish example | `asm-key-level`, 866–907; sheet 003 | The term is visibly written FVG. This resolves the transcript's “FBG/AVG” variants for this passage. |
| FVG has surface, 50% threshold and depth, with different reuse implications | Same, 979–1078; sheet 003 | Near-edge entry and mitigation lifecycle must not be conflated with a universal teacher rule. |
| Blocks with an FVG preferred; absence is not a universal disqualification | Same, 1199–1205, then 1826–2005 and 2055–2187; sheets 005–006 | Later Q&A qualifies the initial explanation. Nearby liquidity and higher-timeframe-zone alignment are named. A 1.5× body shortcut is not established by these passages. |
| Liquidity candle stands short of a level; limit goes at level behind it | `asm-all-you-need-asian-map-concept`, 1577–1615; sheet 005 | Supports pending limit route. “Closest to the liquidity” is not the same as closest POI to current close. Numerical tolerance remains unvalidated. |
| A local entry/stop is illustrated, and the teacher discusses another level after a body break | Same, 1609–1649; sheet 005 | Do not conclude that SL must always be beyond the full H1 sweep. Exact local geometry needs better source frames and rule extraction. |
| Targets are identified chart destinations | Live session, 3079–3094; sheet 009 | No support found for Map 5's 3× projection with a 1.0 price-unit floor. Removed that calculation. |
| Broader context can veto an apparent setup | Live session, 4015–4048 | Teacher declines gold in the described bearish/discount condition. Source does not support taking every hourly sweep regardless of context. |

All transcript paths are under `knowledge-base/videos/<slug>/transcript.txt`; all contact sheets under `knowledge-base/frames/<slug>/sheets/`.

## Corrections made in this source pass

1. Map 5 now requires an explicit prior range-target candle. Its relevant extreme must remain untaken, and the candle must have closed before the rejection begins. No supplied range target means no Map 5 signal. Automatic range selection remains unimplemented; this restriction is **not** evidence against the teacher's strategy.
2. Daily candle-range bias rejects sweeps that already reach the intended opposing target, including dual-sided sweeps.
3. Order-block formation time is the third candle's close; origin time is retained separately. POIs must exist before the tested hourly candle. FVG and provisional no-FVG displacement candidates carry distinct evidence labels.
4. Corrected the earlier derived specification's absolute FVG requirement. No blanket FVG-only filter was implemented.
5. Report labels distinguish the research partial-exit policy from a verified teacher exit policy.

## Still incomplete — implementation ownership, not questions for the user

- Replace four-bar minor structure with source-validated structural swing identification.
- Establish active range selection and higher-timeframe conflict resolution; current map priority/short window remain approximations.
- Model FVG mitigation depth, open-close geometry, and context-qualified no-FVG exceptions rather than body-size shortcuts.
- Resolve local invalidation/stop selection, target hierarchy and partial/break-even policy through actual examples. Transcript “here” cannot establish an exact numeric stop.
- Reconcile chart clock, session boundaries and broker candles. Do not invent intrabar confirmation from a completed-bar-only implementation.

These are findings from a focused pass through the cited segments, not a claim that every video or every trade example has been validated. No annual backtest was launched in this source pass, and no profitability claim follows from the unit tests.

# ASM implementation and backtest audit

Inspected revision: `31ba0d91db6866e6fd493db48cf75dbedd82671d` (FZ-ASM).

## Conclusion

The existing results cannot establish whether the taught ASM strategy is profitable. The runner executes a materially simplified entry route, admits future higher-timeframe prices, and lacks entry-fill validation. This audit does not establish that a corrected strategy will be profitable.

The archived report covers **2025**, with 1,389 trades. Its dynamic FZ exit totals -72.8R; fixed 1R/2R/3R/4R totals are +29/+92/+81/+14R before trading costs. Preserve these as historical outputs, not validated performance.

## Reproduced failures

`tests/test_fzasm_audit.py` contains seven strict expected-failure tests. They assert intended behavior; xfail means the defect is reproduced, NOT repaired. Local result: 26 passed, 7 xfailed, including the existing tests.

| Finding | Evidence and consequence |
|---|---|
| Future H4 data | `data.resample_ohlc` labels aggregates at their opening time. `backtest.backtest_pair` admits H4 bars with timestamp <= decision time. A synthetic 03:00 H1 high becomes visible at 01:00 through the 00:00 H4 bar. |
| Missing lower-timeframe confirmation | Runner supplies D1/H4/H2/H1, no M15. `entry.evaluate_entry` falls back to H1, yet tags it MODEL_A_CHOCH_RETEST. All 1,389 archived rows carry that label; no inducement-route results exist. |
| Unfilled orders receive outcomes | `TradeOutcome` has no pending/fill state. A BUY entry of 100 receives a winning outcome from a later bar whose entire range is above 120, without trading at entry. |
| Partial-profit overcredit | Entry 100, stop 90, TP1 110 and TP2 120: one bar crossing both targets credits 2R rather than 1.5R under the stated 50/50 exit policy. |
| Intrabar uncertainty hidden | After TP1, a bar touching both break-even and TP2 is awarded TP2 without ordering evidence. Fixed-R stop/target collisions instead assume stop first. These are inconsistent conventions. |
| Timeout marked flat | Fixed-R timeout assigns 0R even when the position's closing price represents a gain or loss. Either mark to market under an explicit exit policy or retain unresolved/open status. |
| Sweep contradicts its description | A candle sweeping both prior extremes can be labeled bullish with the prior high 'standing', although that high was broken. This proves an internal inconsistency; whether any dual-sweep variant belongs in ASM requires source validation. |

## Source comparison

`knowledge-base/videos/asm-asm-night-live-tarding-day-one/transcript.txt`:
- 2553.4–2588.0 seconds: timed H1 sweep, H2 alternative, leave it if no sweep.
- 2636.5–2656.5 and 2724.7–2738.7: after the Asian sweep, require a market shift on M5/M15.

`knowledge-base/videos/asm-all-you-need-asian-map-concept/transcript.txt`:
- 1497.8–1538.3: lower-timeframe formation/change of character and return to a key level.
- 1538.3–1591.5: candle liquidity near a key level, followed by entry at the level.
- Visually inspected the matching contact sheet `knowledge-base/frames/asm-all-you-need-asian-map-concept/sheets/sheet_005.jpg` (1500–1860 seconds). It contains separate sweep/context and entry diagrams. Small handwritten details still need individual-frame validation.

The current M15 Model A, even if supplied candles, enters at a close past a four-candle extreme rather than waiting for a documented retest. Adding M15 data alone therefore does not repair the model. CAWT, as named by the user, must not be equated with the whole ASM strategy or silently renamed.

## Other issues requiring validation

- Map priorities, confidence values, five-day range proxies and body-size-based open/close levels are mechanical approximations; validate them against the lessons before presenting them as faithful rules.
- Some fallback targets are arbitrary 2R/2.5R, not a demonstrated structural target.
- Session clock mixes UTC comments and WAT terminology; distinguish candle-open time, candle-close availability and the teacher's session clock. Verify broker candle boundaries and DST where applicable.
- Cached data is accepted with any rows in the requested year, without full-year coverage guarantees. Resampling does not reject incomplete/gapped bars.
- Aggregate drawdown follows concatenated symbol rows rather than chronological portfolio exits. Exit times are shared across variants. Costs are excluded.

## Repair order and acceptance gates

1. Introduce explicit candle availability times; prove that changing future candles cannot change earlier decisions. Reject unfinished higher-timeframe candles.
2. Supply source-supported lower-timeframe data and enforce sweep -> shift -> retest/inducement -> pending order -> actual fill. Missing required data must produce no trade, not a mislabeled fallback.
3. Implement ordered execution and consistent partial accounting. Use finer data for collisions; preserve unresolved status when sequencing remains unknowable. Define timeout exits and costs explicitly.
4. Validate source rules against selected video examples with timestamped chart evidence. Separate source ambiguity from proven programming defects.
5. Only then rerun the yearly comparison in GitHub Actions, recording coverage, data provenance, monthly results, and unresolved outcomes.

No strategy code or archived P&L has been changed by this audit. No full-year backtest has been rerun. The audit workflow runs only deterministic checks; a green workflow with seven expected failures means successful reproduction, not a corrected system.

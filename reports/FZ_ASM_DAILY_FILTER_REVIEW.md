# Daily filter review and Asian entry-only comparison

2026-11-13. Requested research comparison; production defaults unchanged.

## Source evidence

Primary transcripts (machine transcription, wording imperfect):
- knowledge-base/videos/asm-intermediate-timeframe-asm/transcript.txt, 566.9–642.6 seconds: teacher describes daily and three-day directional context and synchronization of zones with the daily timeframe.
- knowledge-base/videos/asm-asm-night-live-tarding-day-one/transcript.txt, 4759.8–4804.9 seconds: teacher distinguishes expectation from reaction and says confidence does not mean going against bias.
- Same live transcript, 6545.4–6565.6 seconds: explicitly goes to daily and identifies a daily sweep.

Conclusion: higher-timeframe context is supported by the material. This is not evidence that daily direction should always be removed. However, the current exact implementation is not established by these passages: D1 only, fixed map priority, nearest touched H4 POI, and a hard equality between POI direction and daily direction. D2/D3 are not implemented by that gate. The generated core-strategy notes are secondary interpretations, not independent teacher evidence. These differences need chart-specific verification before calling the gate teacher-faithful.

## NZDJPY rejection

At 2026-11-11 03:00 UTC, the filtered engine returns poi_daily_direction_mismatch. The earlier sweep_daily_direction_mismatch check passed. Therefore the sweep agrees with the daily bias; the selected H4 POI does not. It would be inaccurate to say that daily bias itself opposed the user's short. The new workflow records map notes, directions and POI bounds in NZDJPY-reference.json.

## Comparison specification

Three pairs: NZDJPY, EURUSD, GBPUSD. Signals November 1 through one shared, runtime UTC cutoff. Cache supplies warmup; fresh completed M1 bars extend it. Both modes use identical data. No live orders.

Filtered: unchanged existing D1/ITF POI and prime-sweep gates.
Asian-only: direction from the completed single-sided H1 sweep, 00:00–06:00 UTC sweep/session, direct H1 A/V or shared M5 close-based CHoCH plus H1/OB/FVG entry routes. No daily map, H4 POI, narrower prime-hour gate or H2 fallback. Same limit expiry, one-use sweep/context handling and conservative M1 ambiguity accounting. This is a broad context ablation, not an isolated daily-gate experiment.

Stops: exact H1 extreme and three instrument pips outside. Targets: 1R/2R/3R/4R and causal frozen Asian opposite extreme. FZ_RESEARCH is UNAVAILABLE without a daily map; internal fixed-R plan fields are not passed off as an FZ target. Asian target unavailable if history incomplete or target is unfavorable. Gross BID results exclude costs. Pending/open/unknown/unavailable remain separate. Latest trades may lack time to resolve.

110 targeted tests pass, including no daily evaluator call in entry-only mode, later Asian sweep eligibility, actual NZDJPY reference plans and future candle exclusion. A successful backtest is not proof of profitability or exact teacher fidelity.

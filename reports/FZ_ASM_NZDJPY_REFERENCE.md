# NZDJPY — November 11, 2026 reference-case audit

Status: **partial alignment, NOT a verified full pattern match**.

Source collection ran through GitHub Actions, run 43032216999. It fetched 2,031 M1 bars from IC Markets cTrader for Nov 10 00:00–Nov 11 10:00 UTC. User screenshots are FOREX.com, displayed UTC+1. Original collected CSV SHA256: f428c201ddd2c21811a5badd7c96d5dccab6154edf023eb7d7fdbd3861a29312. A four-hour unmodified subset is committed as tests/data/nzdjpy_20261111_m1.csv. All screenshot prices below are comparison labels, never detector inputs.

| Item | User screenshot | Computed IC Markets | Assessment |
|---|---|---|---|
| H1 condition | Previous high swept; low standing | 02:00 UTC high 89.185 > prior 89.132; low 89.077 > prior 89.012; close 89.094 inside prior range | Same sweep condition |
| Direct H1 A entry | 89.118 | Previous close 89.117 | 0.1 pip price difference; same proposed body junction |
| M5 structure | Marked CHoCH | Protected pivot low 89.095 at 02:05 UTC; break closes 02:55 UTC | Structure event found; exact marked pivot equivalence unverified |
| Earliest actionable time | Screenshot does not establish order submission time | 03:00 UTC / 04:00 UTC+1, after H1 closes | No order from an unfinished H1 candle |
| FVG + A level | 89.122, later marked local level | First candidate 89.120; FVG 89.119–89.121; junction origin 01:30 UTC | Close price does NOT prove same zone: origin differs |
| Order block | 89.125 | First candidate 89.130 from 02:40 UTC candle | 0.5 pip difference; block identity not established |
| Stop | 89.190 / 89.192 | Existing 3-pip buffer gives 89.215 | Does not match stop distance |

The fixed 3-pip buffer, not just provider differences, explains much of the stop discrepancy. No universal new buffer has been inferred from one screenshot. The user's take-profit boxes remain illustrations; no target calibration or profit claim was made.

## Implemented research alternatives

`recognition.py` identifies a one-left/one-right confirmed pivot preceding the sweep extreme, then the first closed break through that level. Intrahour events are retained but become actionable only after H1 confirmation. `swing_fvg` looks for local A/V candle junctions inside actual three-candle gaps. `swing_ob` freezes the last opposing launch candle at the break. Both are opt-in engine/backtest/workflow policies. The old `mss_retest` policy is retained for comparison; these unverified alternatives have NOT silently replaced it.

Causal tests check that altering all candles after the decision does not change detection; incomplete H1 context and missing M5 bars are rejected. Mirrored buy/sell and real-data regression tests pass. These establish software behaviour, not teacher fidelity.

## Outstanding reference mismatch

The first detected FVG and OB need not be the user's later chosen zones. This audit does not equate near prices with matching selection logic. Confirm the exact marked local junction / order-block origin on the FOREX.com example before treating these route definitions as validated or extending profitability studies. Broker-side bid data cannot establish identical FOREX.com gap boundaries. Full daily-map/POI qualification is not claimed: this is a component audit using the actual sweep.

Charts: scripts/build_nzdjpy_reference_review.py uses only the committed reference subset, displays UTC+1, marks model and screenshot levels, and stops at the earliest decision. Outputs three PNGs and a PDF. No annual backtest, live order or production deployment was made.

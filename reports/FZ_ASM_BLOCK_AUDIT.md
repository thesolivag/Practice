# Block selection audit — 2026-11-11

Added a general, review-only candidate enumerator. It retains opposing candles from the sweep extreme to the first structural closing break, provided a subsequent closed candle departs beyond their full range. It never selects by later retest or outcome. Existing trading selection is unchanged.

NZDJPY reference candidates: 02:10, 02:30 and 02:40 UTC. The user identifies 02:30 UTC (03:30 WAT) as a **violation block**. This user label is chart-only reference metadata, not detector input. The source transcripts searched do not establish a mechanical violation-block classifier. Do not rename every secondary candle violation block.

Important remaining discrepancy: the sweep-origin candidate uses body-to-wick boundaries, approximately 89.134–89.185; the screenshot upper block is approximately 89.157–89.189. Correct origin is not equivalent to correct zone or entry. The three-pip stop buffer remains unvalidated against the screenshot.

Audited all available reference-window H1 sweep-close decisions: three candidate-bearing setups, at November 11 03:00, 05:00, 06:00 UTC. All are NZDJPY on IC Markets bid data; the user chart is FOREX.com. This is not multi-symbol validation or a profitability test. Bull/bear recognition symmetry is covered by existing regression tests, not evidence of other real trades.

70 targeted tests pass locally. New test verifies retention, closed-H1 gating and future-price invariance. Charts produced by scripts/build_block_audit.py; full local CSV is the previously collected reference dataset. No broad backtest run and no production strategy change.

Next: establish zone boundaries and violation-block rules from teacher chart evidence, then validate on separately sampled instruments in Actions. Do not hardcode the reference timestamp as a classification rule.

## Source review and cross-symbol run

The key-level lesson defines ordinary order blocks as the last buying candle before a sell (1136–1140 seconds), and the last selling candle before a buy (1142–1146). At 1318–1358 it describes a body-broken block becoming a breaker. At 1868–1908 and 1973–1985 it explains an order-block transfer to the next candle when the FVG occurs there. These are distinct concepts; none establishes that the user's named violation block is a breaker or transfer. The reviewed contact sheet key006 also does not establish that equivalence.

Do not change the block boundary from the source candle's open to its close solely to fit NZDJPY. That would improve a plotted resemblance without establishing the general rule.

Cross-symbol collection/audit committed as a21c7f0266434eab0a76c1c8da47209e1c431546. Actions run: https://github.com/thesolivag/Practice/actions/runs/43094618464 . Fixed sample EURUSD and GBPUSD, Nov 10 00:00 through Nov 11 10:00 UTC. Uses broker M1 aggregated to complete M5/H1; only H1-close decisions audited. Saves all candidate-bearing decisions, selects first two per symbol chronologically for chart export, without outcomes. This is candidate evidence, not full strategy or session qualification.

Run 43094618464 completed successfully. EURUSD: 2,023 M1 bars, seven H1 sweeps, zero candidate-bearing H1-close decisions. GBPUSD: 2,037 bars, eight H1 sweeps, three candidate-bearing decisions. Zero candidates is not evidence of no valid trades: later M5 break decisions and full strategy qualification were not audited.

The first GBPUSD chart exposed an origin omission in the review helper: when the extreme candle itself is directional, the opposing launch candle just before it was excluded. Corrected block_audit to include the latest opposing candle at/before the extreme within the context window. Saved real M5 regression fixture verifies the November 10 11:00 UTC origin. Two exported GBPUSD samples rechecked; first now retains four candidates, second two. Original Actions evidence preserved in cross-symbol.json; post-fix evidence in cross-symbol-rechecked.json. 71 targeted tests pass locally. The trading route in recognition.py is still unchanged; this is an audit correction, not a completed production classification repair.

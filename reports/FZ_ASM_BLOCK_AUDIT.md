# Block selection audit — 2026-11-11

Added a general, review-only candidate enumerator. It retains opposing candles from the sweep extreme to the first structural closing break, provided a subsequent closed candle departs beyond their full range. It never selects by later retest or outcome. Existing trading selection is unchanged.

NZDJPY reference candidates: 02:10, 02:30 and 02:40 UTC. The user identifies 02:30 UTC (03:30 WAT) as a **violation block**. This user label is chart-only reference metadata, not detector input. The source transcripts searched do not establish a mechanical violation-block classifier. Do not rename every secondary candle violation block.

Important remaining discrepancy: the sweep-origin candidate uses body-to-wick boundaries, approximately 89.134–89.185; the screenshot upper block is approximately 89.157–89.189. Correct origin is not equivalent to correct zone or entry. The three-pip stop buffer remains unvalidated against the screenshot.

Audited all available reference-window H1 sweep-close decisions: three candidate-bearing setups, at November 11 03:00, 05:00, 06:00 UTC. All are NZDJPY on IC Markets bid data; the user chart is FOREX.com. This is not multi-symbol validation or a profitability test. Bull/bear recognition symmetry is covered by existing regression tests, not evidence of other real trades.

70 targeted tests pass locally. New test verifies retention, closed-H1 gating and future-price invariance. Charts produced by scripts/build_block_audit.py; full local CSV is the previously collected reference dataset. No broad backtest run and no production strategy change.

Next: establish zone boundaries and violation-block rules from teacher chart evidence, then validate on separately sampled instruments in Actions. Do not hardcode the reference timestamp as a classification rule.

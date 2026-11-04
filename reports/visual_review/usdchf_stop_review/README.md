# USDCHF: corrected confirmation and stop linkage

## Correction to the original comparison

The owner identified the first engulfing and the later, traded engulfing in the original T3 frame. The earlier comparison incorrectly presented the deeper first-confirmation protection as a plausible stop for the second confirmation. The yellow IC candle was already the second engulfing; the engine's inherited risk scope was wrong. The original evidence remains in Git history and frozen run40538418605; it is superseded by this explanation and figure.

Original firsthand T3 frame at1485seconds: FOREXcom H2 buy drawing entry0.79860, stop0.79783, target0.80113. Source SHA256 ee73e7118df31d1f30524a204ffe5393bbfc05b87197f935fe01bd4687d45004.

Frozen IC candle sequence:
- First engulfing June10 15–17 UTC, reference candle13–15 low0.79652. A stop below that low belongs to that first pattern.
- Its body0.79790–0.79851 is revisited by June10 21–23 low0.79787.
- Second engulfing June11 05–07 UTC, reference/current lows0.79823 /0.79817. These are its own pattern-risk candles.

## Implemented correction and GitHub verification

Commit9ac7a74 separates adjacent-engulfing pattern-risk evidence from H4 first-take/reaction qualification provenance. It includes the reference/engulf pair, plus the following candle for delayed IRL entries. Older context candles/context-only range-origin links are not automatically inherited into this stop. Nearby structure checks remain. BO, standing-extreme and nonadjacent OC routes retain their existing behavior.

GitHub regression40583792706: **468 passed,5 skipped**. Independent reviewer checked the implementation and confirmed the original first/second candle sequence.

Frozen primary replay40583792823 recomputed the same setup/order IDs: entry0.79838 unchanged, target0.80063 unchanged, stop **0.79647 →0.79803**. The binding protection is nearby same-TF level0.79808 minus the existing0.00005 buffer; current pair alone would produce0.79812. The obsolete0.79652 is absent from current protected objects. Revised stop lies2.0pips above Bishop's drawn0.79783, consistent with the owner explaining that Bishop allowed additional room below the logical second-pattern stop.

The replay order filled and reached its diagnostic target with zero costs. This is not certified identity with Bishop's broker trade: source/bot entries and targets still differ, and exact cross-feed fill correspondence is unverified. Neither prices nor outcomes were fitted to the source drawing.

Reproduce figure only: `PYTHONPATH=. python reports/visual_review/usdchf_stop_review/render.py`. This reads frozen results/candles, without running the strategy.

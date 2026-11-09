# Interactive research review — 2026-11-09

Mini App → Trade review. Read-only authenticated archive, separate from live entries and order execution.

- 3,221 grouped setups, 26 comparison markets from original run 42371042901.
- Corrected outcomes from the final ledger incorporating runs 42499187752 and 42516446781.
- Original capacity-limited cohort: do not mistake this for the newer capacity replay or infer full-year profitability.
- RR variants share a selectable setup; targets and corrected outcomes remain separate.
- Opens at decision time. Server excludes future/unavailable and unfinished candles. Reveal outcomes is explicit and independent of chart-clock advancement.
- Independent H1/H2/H3/H4/D/W selectors, older-candle paging, pan/zoom, crosshair OHLC, expanded view.
- Existing broker-calendar aggregation uses New York 17:00 with DST. Gaps remain gaps. Frozen base feed is H1 BID, not minute/tick execution evidence.
- Three starred EURUSD recognition examples have reconstructed H4 sequence evidence: Feb18 engulfing/H1 and 4th man/H2, Feb19 breakout/H1. These are bot annotations, not original teacher charts.
- Other setups have recorded entry/SL/targets and any saved stop proof; missing H4 sequence is stated explicitly, never invented.
- Levels describe the selected decision, even while browsing older candles. Numbered event markers correspond to the sequence list below the charts.
- No live database data, Telegram deliveries, broker orders or strategy rules changed.

Files: webapp/bishop_review.py, static/bishop_review.js, app registration/navigation/styles, data/bishop_review/*.json.gz. Docker already copies data/. Archive builder scripts/build_bishop_review.py requires frozen inputs/ledger/evidence paths and does not fetch broker data.

Validation: tests/test_bishop_review.py plus existing webapp auth tests; tests/ui/review.cjs added to CI; local Chromium integration also exercised actual archive and all timeframes on desktop/mobile. Production verification must be reported separately from local tests and GitHub push.

Future work: import new capacity-study results as a separately labelled dataset; save H4 evidence alongside every new research setup to extend full annotation coverage; original teacher-chart comparison remains separate work.

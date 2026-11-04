Open bishop_examples.html in a browser. It is self-contained and makes no network requests.

Includes original PDF pages13 and27, frozen IC Markets candles, every saved independent candidate across available timeframes, model stop evidence, and comparable execution outcomes. Default ordering is chronological, not ranked by result. No strict teacher match is asserted. GBPUSD uses complete M5 refinement for the seven previously ambiguous orders; incomplete M1 results do not replace it.

Build: render PDF pages13/27 with pdftoppm -scale-to1400 into /tmp/bishop-page-13.png and /tmp/bishop-page-27.png, then run python -m reports.build_teacher_visual_replay. The builder requires the saved research_later_kl_irl.json.gz investigation traces under reports/teacher_later_irl_results/<case>/ (Actions40167342640, matching-case artifact only). It verifies the frozen feed hash and aggregates candles for display; it does not run strategy detection or execution simulation.

Browser verification: all61 candidate/timeframe views rendered without JavaScript errors or invalid chart coordinates; mobile390px layout and source-image zoom checked with Chromium. Large historical replays were not repeated.

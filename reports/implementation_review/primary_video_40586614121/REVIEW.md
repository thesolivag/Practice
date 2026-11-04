# Exact broken-A retest verification

Code53ff2dc37ef15ee13e3c0199fc5b4371e14e8d83; GitHub replay40586614121, regression40586612929 (job122479606449:484passed,5skipped).

Before: run40584565827 H2GBPCAD05:00 confirmation_bo order used unrelated historical V at1.86271. After: earliest selected June9 H2confirmation_bo order_e9304ec056aa10550332e6e3 waits at1.86179, the exact Alevel155885ad57954e0276368594 (original SELL). Setup metadata declares exact_broken_av_retest_v1; its event reference equals that A's turn_id and price. The correct fresh05:00break is distinct from the stale external-break reannouncement of the already-flipped1.86124 level, which is now rejected.

Order submitted05:00UTC, later M5 retest fill06:05–06:10UTC at1.86179. No breakout-close fill. Bishop source T3 at420seconds entry1.86183 differs0.4pip; fixture/source values and tolerances were not changed. Similarity is not certified source-to-IC candle/fill identity.

Stop remains1.85847 versus source1.86041; the19.4pip stop gap remains unresolved. This change corrects entry reference, not BO stop geometry. Prior current-engulf confirmation scope correction remains in place; standing-extreme separate procedure remains unchanged. Review of the exact resolver identified and fixed wrong-candle borrowing and future duplicate-level causality issues, both covered by regression tests.

Replays/figures are diagnostic alternate-feed, explicit zero-cost outputs, not measured live performance or complete teacher acceptance. No live trades or notifications sent.

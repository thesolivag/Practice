# Broken A retest entry correction

Reproduce chart only: `PYTHONPATH=. python reports/visual_review/breakout_retest_correction/render.py`.

The chart selects the earliest actually submitted June9 H2 confirmation_bo order by clock/ID, never outcome. Frozen GitHub40586614121 input/manifest/source/code hashes preserved separately. A buy LIMIT at1.86179 references the precise broken Alevel, not an arbitrary nearby V or confirmation close. After05:00confirmation, frozen M5 data places fill in06:05–06:10UTC. This is the entry sequence described by the owner: A(resistance) → closed break → role change → buy retest. SELL is mirrored at V.

Original source T3 frame420seconds (unchanged original available in reports/visual_review/confirmation_types_review/gbpcad_420s.png) shows Bishop entry1.86183/stop1.86041. Source video SHA256 ee73e7118df31d1f30524a204ffe5393bbfc05b87197f935fe01bd4687d45004. The chart overlays those FOREXcom numbers as price references only.0.4pip entry proximity does not resolve exact candle/fill identity. Bot stop1.85847 differs19.4pips. The owner subsequently confirmed it as logical for the breakout; this is an explained difference in protection reference, not an open stop defect for this case. Bishop’s particular engulfing-based rationale remains the owner’s chart interpretation.

Source fixtures, tolerance fields and outcome expectations were not tuned. Chart rendering consumes frozen outputs; heavy replay ran on GitHub Actions. See evidence.json for the exact A, event, setup, order and observation.

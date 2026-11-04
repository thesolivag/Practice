# Firsthand video: GBPCAD case review

Primary source: T3,28.9–577.1s, source videoSHA
ee73e7118df31d1f30524a204ffe5393bbfc05b87197f935fe01bd4687d45004.
This is Bishop's own narrated trade breakdown, not the student PDF. Linked
frames/transcript are frozen in tests/bishop_video_breakdown_cases.json.

GitHub40531068022 succeeded at4efefaf, preserving full H4/entry diagnostics.
Independent source/code review found procedural overlap but NOT a full match:

- Source: H4sweep+BOS→single-candle liquidity→H4KLreaction→H2BO;
  simultaneous H1BO passed forH2. Target just before H1external.
- Engine detects a real H4liquidity→take→reaction→laterH2BO chain. Its
  H4BOS f9f0... is publishedJun8 17:00UTC through1.86060;
  H4BARpool LOW1.86091 is knownJun8 21:00UTC.
- First take: H2bar4e68... Jun8 21–23, low1.85852. Later reaction:
  H2bar0598...23–01, low1.86026, against H4OC1.86050 formedMay25.
  H2BO8075...01–03, available03:00UTC, haslow1.86062.
- Seven June9 H2BO time/entry/risk plans arise from391 source-context aliases.
  These are alternatives in the diagnostic window, not seven mentor trades.
  First03:00 plan1.86145/1.85847/1.86262 expiresunfilled. Later05:00 plan
  1.86271/1.85847/1.87040 has a target near the source drawing, but cannot
  substitute for his selected entry merely because it later wins.

## Concrete stop mismatch

Source frame390 starts with a broader drawing; frames420/435 tighten the
stop around1.86041→1.86037 for entry1.86183 and target~1.87039 (~5–6R).
These are demonstrated tool values, not invented exact broker-fill accounting.

All seven engine plans stop1.85847: entries._protection_episode_bars passes the
first-take excursion AND later reaction bars; risk.plan takes their lowest
wick1.85852 and subtracts5ticks. This is a traceable whole-excursion protection
choice, not spread or rounding error. A later H2close-pivot1.86071 is already
known, but its TURN_LEGpool also inherits1.85852 from the preceding high-anchor
leg. Choosing that newer pool alone would not repair protection. A fresh
BOseed range also points to older protected geometry; no justified fix is to
select whichever wick is numerically closest to the source stop.

The exact source-to-IC candle/pivot correspondence and model-specific logical
invalidation must be established before changing protection globally. Other
firsthand cases explicitly protect nearby H4liquidity/KL, so a global removal
of H4 protection would contradict the corpus. Original source facts and
expectations were not altered to fit engine outputs.

## Limits and next decision

The fixed visible-chart Junewindow is exploratory, not a certified fill clock.
Forty-day context does not establish sourceMonthly support; W/Dcoverage is
partial.27hypothetical orders across this window are not27teacher examples
or a source profitability claim. The narrated trade is the primary evidence;
its full engine replay remainsNOT_ESTABLISHED. The separate July nativeIC
alignment audit does not prove JuneFOREXcom-to-IC equivalence.

Next evidence: identify the sourceH4KL/reaction and selectedH2 entry candle
against the corresponding IC bars, then define that confirmation model's
logical protection without inheriting an unrelated earlier excursion or
choosing retrospective price matches.

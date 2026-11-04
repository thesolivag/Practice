# Second stop comparison: firsthand GBPUSD H2 sell

Top of comparison.png is the unaltered original T3 frame at1350s/22:30,
GB PUSD2h FOREXCOM: entry1.33793, stop1.33925, target1.33308 (13.2pip risk).
At1287.7–1304.5 and1334.9–1348.1 Bishop explicitly protects nearby H4liquidity
and its key level, not merely the engulfing high. Some tighter accounts stopped;
others survived to target. No all-account win is claimed. The1320s H4 drawing
has the same entry/stop but an earlier different target1.33438.

Bottom is actual frozen IC H1 data aggregated into H2. All eligible June11H2
SELL candidates share stop1.33923, above a recorded protective high1.33918 with
5tick padding. The source and bot stop levels differ by0.2pip. This does not
certify their source candle/entry identity.

Both relevant bot candidates are visible, rather than silently substituting a
later one:07:00 standing-extreme candidate, entry1.33836;15:00 engulf_av_retest
candidate, entry1.33613. The latter is the first eligible strict H2engulf for
this day, selected by availability thenID, not profit or price proximity. It
was held by EXPOSURE_CAP, not executed. Its confirmation candle is13–15UTC.
Source entry1.33793 is not asserted equal to either bot entry.

Frozen full replay:reports/implementation_review/primary_video_40535518232,
GitHub40535518232 at16e6442. Exact price/identity assertions and report hash are
inrender.py andevidence.json. No trading rules, source fixtures or tolerances
were altered for the image. The original video hash matches the first example.

Additional literal observation for later model investigation: the earlier IC
03–05 bullish candle closes1.33836;05–07 bearish opens1.33835, closes1.33774.
The one-tick opening gap fails full-body coverage in the current strict engulf
predicate; the bot instead labels that candle standing-extreme. Adjacent
01–03close1.33793 and03–05open1.33792 also differ by one tick, affecting an exact
OC-junction convention. This records why labels differ; it does not justify
relaxing a definition or certify that this is the source candle without review.

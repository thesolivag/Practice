# Full ASM filter audit — 2026-11-15

Evidence: run43681358570, May1–7 inclusive2026; downloaded original EURUSD/GBPUSD decisions and manifests under evidence/full-filter-audit. No rerun, optimization or strategy changes in this audit.

## Findings
EURUSD: 3 NO_PREEXISTING_LEVEL_IN_RANGE_HALF rejections; 3 SWEEP_MAP_CONFLICT rejections; 72 CONFLICTING_DAILY_MAPS decision clocks. The72 clocks cover May6 00:00–05:55UTC, not72 trades. An older bearish candle-range map (known May3 21UTC, origin1.17852,target1.16551) coexists with newer bullish candle-range/leg maps (known May5 21UTC, origin1.16765,targets1.17486/1.17852). choose_map rejects the entire mixture before entry recognition.

GBPUSD: 8 NO_PREEXISTING_LEVEL_IN_RANGE_HALF; 5 SWEEP_MAP_CONFLICT; 30 NO_ACTIVE_DAILY_MAP decision clocks (May1 03:30–05:55UTC). At May1 01UTC the selected structural map is bullish from1.3454 to1.36121, known April30 21UTC; the level gate rejects. At03UTC a sweep disagrees with that bias. These are rejection events/clocks, not proven missed fills.

## Source/code assessment
The intermediate-timeframe lesson at1750–1914s supports maps forming/rejecting at zones and context-based selectivity. It does not establish the exact code policy requiring every entry POI in the lower half of a bullish daily range / upper half of bearish daily range. The ranges lesson3286–3355s discusses H4 sweep, internal range and lower-timeframe liquidity; that is not enough to certify a universal daily-midpoint veto. The written model specification already labels this policy provisional.

All-map conflict abstention is likewise a documented conservative research choice, not validated FZ priority. It is mechanically consistent with code, but may reject legitimate nested-range opportunities. Do not automatically choose newest map or disable the filter merely to improve backtest returns.

The composite NO_PREEXISTING_LEVEL_IN_RANGE_HALF code combines several failures: no level, wrong direction, no touch, outside range half, or sweeping close not respecting level. Artifacts do NOT record candidate-level diagnostics, so these11 events cannot be attributed specifically to the midpoint rule. Missing per-level evidence prevents certifying each rejection. A later diagnostic patch should record those components, sweep and candidate prices without changing trade selection.

## Conclusion
The run demonstrates these research rules execute; it does NOT establish that the full teacher method rejects these setups. It also does not demonstrate profitable missed trades. Before annual expansion: expose candidate-level diagnostics, inspect the named clocks against source-supported range context, and settle map conflict/range-selection rules. Keep original run immutable. No profitability inference from zero filled trades.

# Missing primary-video cases: independent source observations

The source inventory includes these four actual episodes; the earlier four-case replay did not.
`source_observations.json` supplies a comparator-ready `cases` list with instrument, side, entry_tf,
entry_model, source_observed_window, drawings and limitations. All observations remain
SOURCE_OBSERVATIONS_NOT_ENGINE_ACCEPTED. This review changes no engine, fixture or workflow.

| Case | Formation locator (displayUTC+1) | Execution model | Source outcome |
|---|---|---|---|
| AUDCHF | Tue9Jun2026, toolanchor07:00 | H1 engulfing | Explicit loss |
| NZDCHF | Wed10Jun2026, toolanchor02:00 | H2 breakout+liquidity after journal correction | Immediate stoploss |
| USDJPY | Wed10Jun2026, toolanchor13:00 | H3 breakout/retest | Manual profit exit around2R |
| EURGBP | Friday29MayH1, retained into Monday1JunH2 support | OriginalH1 engulfing limit | Clean trade narrated |

Anchors locate source drawings/formation bars; none proves a broker fill timestamp. Comparison
windows span the source-observed local formation day (EURGBP spans the narrated Friday–Monday
sequence). Do not invent narrow tolerance, choose a best fit or award acceptance from these windows.

Numeric drawing states are kept separately: AUDCHF changes target while entry/SL stay stable;
NZDCHF explicitly corrects its initial wider stop and final target is offscreen; USDJPY originally
shows weeklyhigh160.725 then illustrates a hypothetical3R target160.598 while stating actual exit
around2R. EURGBP's laterH2 illustration supports an existingH1 limit, not a second automatic order.
No loss is removed, no hindsight filter substitutes for the setup actually traded.

Fourteen native1366px frames were extracted directly from the original local release videos at
explicit source seconds using accurate seek; each quoted frame has its SHA256 in the JSON.
Existing15s contact sheets were also rendered directly to locate the sequence. This is a targeted
source review, not exhaustive frame coverage or a broker execution audit.

`frozen_inputs.json` preserves the earlier local-search audit and records the new three-pair
GitHub40782235154 frozen rawH1 collection. Each downloaded CSV hash and row count is independently
checked. EURGBP already has IC MarketsH1 history covering itsMay/June episode. Candle presence
makes replay possible; source-feed/calendar mapping and exact causal event identification remain
work for the replay, not facts manufactured by this report.

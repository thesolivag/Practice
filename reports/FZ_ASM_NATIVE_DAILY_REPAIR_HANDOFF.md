# Native D1 / main-block repair

Previous expanded study 43163729089 completed technically but produced zero trades. Cached NZDJPY diagnostic43243673097 proved321259 M1 bars producedzeroD1because strict minute aggregation required1440bars everyday. Those empty results are not profitability evidence.

Repair commit32fd3fe1c6230dc5c1d9fa6a6af7d0d47b8c5416:
- Broker-native D1 replaces minute-derived daily input when supplied. No missing minute prices filled; M1 execution/intraday gap guards unchanged.
- Native daily availability is next broker D1 open, preserves23/25hour boundaries. Expected weekend gaps retained with conservative delayedavailability; unverified weekday gaps rejected by callers. Last native row absent explicit providerclose omitted.
- study CLI requires native daily CSV. Legacy backtest CLI requires native daily directory. Annual workflows must be updated with native D1 collection before manual reuse; no annual rerun authorized untilshortcheck reviewed.
- study replay accepts native_daily and requested signal period, retaining earlierM1for intraday context. Context rejection diagnostics expose no daily map/noPOI/mismatches instead of silentzero.
- Trading order_block selector now chooses latest opposing origin at/before sweep extreme, with subsequent full-range closing departure by structuralbreak. This replaces selecting last little opposing candle beforebreak. No violation-blockclassifier invented.
- NZDJPY example: mainorigin02:10UTC=03:10WAT, entry89.134, zone89.134–89.185. Previouschosenorigin02:40UTC/entry89.130 replaced. Teacher's exactupperzone boundaries remain unverified; fixedbody-to-wick rule notfitto pixels.

106 tests pass locally, including12nativeD1tests andrealNZDJPY/GBPUSDreference regressions. Independent agentimplemented/reviewed nativeavailability. GitHub regressioncheck43258214079 passed. Shortvalidation43258214359 runs Nov1–11 NZDJPY/GBPUSD/EURUSD using restoredM1caches andSep1–Nov12nativeD1 (~one small brokerrequest perpair). It fails if no signals acrossallthree and exports rejectiondiagnostics/referenceplan. No full-yearrepeat.

Chart: evidence/main-block-repair/NZDJPY-main-block-repaired.png; regenerate scripts/chart_main_block_repair.py. Shortvalidation exports dailyOHLC/sourceaudits/reports forreuse; checkresults beforeannualworkflow changes.

## Completed shortvalidation

Run43258214359 succeeded; GitHub106tests passed. NativeD1:50completedbars perpair, zero unverifiedweekdaygaps,10conservativelydelayedweekendbars. NativeOHLC/audits in artifact13962342251.

Nov1–11: NZDJPY0directH1/0H1+M5/1OB/1FVG; GBPUSDzeroall; EURUSDoneeach. Sixsignals, pairedstops×sixtargets=72outcomerows. Fiveorders expiredunfilled; onlyEURUSD Nov6 01:05UTC FVGsignal filled01:25UTC. Allfixed1R–4R alternatives reachedtarget withbothstops; Asianresult+.277778R exact /+.229885R buffered; FZresearch+2.998264R/+2.481322R. These are alternativesforONEtrade, not12independentwins. Too small forprofitabilityconclusions.

NZDJPY mainOBreference at03UTC correctlyorigin02:10UTCentry89.134, but fullcontext rejects atthatclock:poi_daily_direction_mismatch. Later04UTC signals (OB89.134/FVG89.133) expireunfilled. Therefore originalreference geometry fixed does NOT meanfullstrategyreplicatesreferenceentrytime. Do not secretlyremovefilter orclaimmodelmatchedteacher. Inheriteddaily/ITFPOIfilterneeds sourcereview beforefullannualrerun.

No annualrerun launched. Userpreferredminimalexpense andfixesfirst. Outputs local evidence/native-validation-results, ZIPnative-daily-short-validation.zip. Newmainchart evidence/main-block-repair/NZDJPY-main-block-repaired.png. NewCLI nativeD1requirements intentionallypreventoldminute-derivedannualreuse; fullworkflows neednativecollector/gaphandling beforefuturemanualrun.

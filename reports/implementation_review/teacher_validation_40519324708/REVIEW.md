# Teacher validation: not accepted yet

GitHub run [40519324708](https://github.com/awujo/practicing/actions/runs/40519324708)
succeeded at commit `b1d38ce`. All 15 H4/H2 fixtures were calculated under both
confirmation and owner-direct procedures: 30 calculations, no budget aborts.
Each procedure had 9 complete input windows and 6 input-gap diagnostics.
The other 25 fixtures were outside this targeted run. Every strict result is
UNRESOLVED, because required source facts remain incomplete; this is neither
15 observed engine failures nor 15 matches. Original compressed reports and
checksummed summary are preserved here. The 40-case fixture hash is unchanged.

Regression run40519262290 separately passed436 tests,5 skipped. Regression
success is not source-example acceptance. Owner-direct reports contain14
`direct_h4` and20 `direct_h2` orders, confirming those paths were exercised;
those are hypothetical orders across diagnostic windows, not matched mentor
trades, independent examples, or portfolio performance.

## Independently inspected source mismatches

**Silver p22:** the actual source image labels Daily bearish breakout/PDH
swept → H4 breakout with inducement → H2 engulfing CE. Drawn plan:
59.7269 /60.0626 /58.3773. The eligible same-side H2 `engulf_av_retest` in
the confirmation report is58.653 /60.047 /57.211, available Jul13 15:00UTC.
It occurs after the source chart's Jul13 06:24UTC+1 creation timestamp and
therefore cannot identify the depicted source confirmation. That timestamp
is an observation ceiling, not an inferred fill time. The exploratory replay
currently scans through Jul14; finding a later engulf does not repair the
original miss. The report contains500 missing M1 observations. Feed alignment,
original reaction linkage and structure selection must be traced separately;
no tolerances were widened and no nearest-price plan was promoted.

**GBPCAD p47:** complete input window,2043 setups,0 orders;477 eligible
candidates across all timeframes rejected for conflicting execution plans.
The H2 BUY subset has559 candidates,89 eligible, grouped into7 same-clock,
same-model, same-entry triggers. All7 have conflicting risk plans. Example:
May20 09:00UTC OC confirmation at1.84285, stop1.83966, targets1.84301 and
1.84773. The smaller target is introduced by a counterweekly/retracement guard;
the larger comes from an unguarded story. The safety guard correctly blocks
both, but competing context selection is unresolved. Source p47's drawn
engulfing plan1.84768 /1.84653 /1.85244 has not been established by these
candidates. This observed conflict cannot be attributed to missing candles.

**H4 p20:** independently viewed source charts show silver/oil drawn plans,
but no labeled CE subtype, parent breakout/liquidity chain or placement time.
An H4 chart alone cannot certify `direct_h4`. Stops sit within wider wick
extremes; neither should automatically be equated to a whole-swing wick stop.
Source creation clocks are not fill clocks; drawn target traversal is not proof
of actual fill, management or realized win. Oil quote scale must remain explicit.

The independent reviewer checked the implementation and these source findings.
Its final aggregate-review turn hit an agent usage limit; the primary agent
checked the aggregate against the30 preserved reports. No final independent
aggregate sign-off is claimed.

Next work is causal story/target lineage for p47 and a source-screenshot-bound
reaction/confirmation trace for p22. Do not rerun broad profitability tests or
select whichever target gives a match.

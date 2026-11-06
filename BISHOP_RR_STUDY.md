# Separate Bishop 1R / 2R / 3R paper study

The existing nearby-H4 target strategy is unchanged. This study enrolls the same
new, actually issued Bishop entries after its per-user activation timestamp.
It does not reinterpret historical wins/Unknowns, select held alternatives, send
Telegram messages, or place broker orders. It currently studies the running
KK-aligned Bishop entries; it does not start the archived standalone scanner.

## Frozen study stop v1

Current-confirmation evidence is recorded separately from the old H4 first-take
history. Adjacent engulfing uses its own reference/engulf pair (plus the delayed
IRL candle where applicable). BO and nonadjacent OC use the currently selected
KL-reaction-to-confirmation episode, including its intervening candles. Fourth
man uses its reference/sweep pair. The adverse wick is protected, plus the
baseline's already-qualified nearby same-timeframe protection. The existing
0.5 distance-unit buffer is explicit (0.5pip on supported FX), rounded up to an
instrument tick. BUY/SELL mirror each other.

This is a declared experimental stop rule, not a certified universal Bishop
formula. The saved owner review accepts some deeper BO stops. We do not globally
replace those production stops. Missing candle IDs, missing calendar-aware slots,
data gaps, or unmapped active-range protection hold the study as UNRESOLVED rather
than invent a tight stop. Relevant H4 protection beyond this mapped evidence is
not claimed to be universally solved.

Source: Bishop OWNER_CONFIRMATION_CORRECTIONS.md; T3 1676.8–1686.5 (4th-man pattern),
1292.4–1304.5 and1334.9–1348.1 (nearby protection); video15 1715.7–1730.7 and video14
1186–1207 (current OC entry/protection). The source does not specify a universal
mechanical start boundary for every nonadjacent OC episode; that uncertainty is
why this policy is a separate experiment.

## Execution and reporting

One entry and frozen study SL produce three independent full-exit LIMIT orders,
TP=entry +/- (entry-to-SL distance)*1,2,3. A 1R win does not stop 2R/3R tracking.
Expiry/cancellation evidence and closed-candle execution conventions are retained.
Ambiguous intrabar outcomes stay Unknown. Data revisions censor active study
observations; completed results freeze. No partial exits or automatic breakeven.

Results are estimates under the same explicit zero-cost assumption as baseline;
net profitability after broker costs is not established. Entries → Bishop study
shows per-exit wins/losses, open/Unknown, total R, closed-equity drawdown, and paired
R using only entries resolved at all three targets. The paired cohort can exclude
slow/unresolved exits, so both raw and paired counts remain visible. Drawdown
excludes floating losses and batches simultaneous closes; R is not account %.
Full-history compact statistics include all enrolled rows; latest50details only.
Older active studies stay in tracking even when recent history exceeds500rows.

## Isolation and operation

Dedicated bishop_rr_studies table with user_id and versioned study/order IDs.
Frozen source geometry, stop proof, costs and variant orders cannot be rewritten.
No baseline orders/targets/stop logic changed; entries.py only adds evidence IDs.
Settings bishop_rr_study defaults on; disabling stops future enrollment while
existing studies continue. Selected markets only. Shared feed lock. Independent
90-second job,12-second child per market, fair user/pair rotation; failure cannot
undo baseline persistence. Deferred markets can catch up from frozen source rows.
Runs after normal Bishop hourly step; separate initialization workflow restores
existing candle cache without contacting a broker or sending Telegram.

## Verification

Focused tests cover old-context exclusion, preserved nearby protection, BUY/SELL,
missing same-segment candles, future invariance, independent1Rwin/2Rloss/3Rloss,
ambiguous Unknowns, revised history, private API, MySQL ownership/stale writes and
immutable geometry. Browser test checks comparison table.
Frozen GBPCAD diagnostic: unchanged baseline stop1.85847; study stop1.86021 from
two current episode candles. This candidate was held and is not enrolled as a
trade. A baseline parity replay matches orders, observations, execution events,
actions, selection and all setup fields except the two added study evidence fields.
No study performance results or profitability claim exist at launch.

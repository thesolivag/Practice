# Bishop 2026 comparison

Read-only GitHub workflow `bishop-year.yml`. Requested period: 2026-01-01 through a fixed snapshot of the last closed hour (never beyond 2027-01-01). Uses the owner's currently selected, supported instruments and current strategy preferences, exported as a whitelist without credentials/user records. Actual historical web preferences/DB bias history are not claimed. No live entries, results, notification switches or strategy rules are modified.

## Arms

- `standalone`: current Bishop baseline confirmation rules and original structural SL/nearby qualified target, without the KK web-bias gate. This is not an older archived binary/version.
- `kk_aligned`: same baseline rules, requiring the KK live bias projection reconstructed at every historical clock, then the H4 sponsor sequence. Present-day database bias is never used for past entries.
- `kk_aligned_1R/2R/3R`: same admitted aligned entry cohort, current experimental logical stop and three independent full exits. Original orders are retained unchanged.
- `recognition_1R/2R/3R`: new strict closed-break/later-liquidity/take/reaction/confirmation study, using current logical stop and identical-entry full-exit alternatives. These are explicitly new research orders, not claims that production recognition placed trades.

1R/2R/3R are risk multiples, not one/two/three-hour holding periods. Entry detection still uses H4/H3/H2/H1 as supported by the existing engine; recognition uses H4 context and H1/H2/H3 confirmations.

## No-future boundary

For every observed closed H1 hour, the detector receives a physically truncated 35-day prefix; the KK bias engine receives only its closed prefix (up to the existing live lookback). Only setups available at that exact decision clock can be issued. Late discoveries cannot backfill profitable historical entries. Frozen orders and stop/target evidence persist through quarter checkpoints. Execution sees only the prefix known at the next replay step. Late-discovered cancellations are applied at first observation, never backdated. Current-bar prices cannot fill an order submitted at that bar's close.

Source ambiguity/dedup/ranking rules are reused. Baseline/KK capacity is ten concurrent or unknown orders per market; unknown exposure reserves capacity. Recognition RR exits are an independent signal study with identical enrollment across exits, not an account-allocation strategy. No future winner resolves competing plans. SL/TP in one bar and uncertain fill paths remain CENSORED; no arbitrary profitable intrabar path.

Preparation snapshots primary broker quotes into an isolated local store. Missing sources/calendars/35-day warmup are excluded explicitly. Missing live-equivalent KK higher-timeframe warmup blocks KK-aligned bias rather than inventing it. Deriv's historical retrieval limit may therefore leave aligned histories unavailable. Gaps and exact source hashes are reported. Research never saves its cache over the live cache. The existing broker token manager may refresh credentials during acquisition under the shared feed lock; replay workers receive no DB/broker/Telegram secrets.

## Verification and runtime

Unit tests cover physical-prefix boundaries, unfinished bars, conflicting alternatives, capacity, frozen geometry, next-bar execution, unknown outcomes, non-backdated cancellations, paired cohorts, and checkpoint/feed serialization. Before the full run, a GitHub pilot compares the same decision with the full stored file, a physically shortened file and poisoned future quotes, then benchmarks 24 replay hours. All full-run decisions still use physical prefixes; pilot equivalence is not a substitute for that boundary. A measured quarter over the job budget stops launch for subdivision.

Four sequential quarter jobs per market preserve checkpoint state. Up to twelve markets run concurrently, leaving capacity for the live scanner. Each job is bounded to330minutes. Failures upload checkpoints; the final report marks missing/incomplete markets and never treats them as zero-trade completed runs. Full-year runtime may be many hours.

## Results

GitHub artifact `year-report` contains REPORT.md and REPORT.json. Per-market/quarter artifacts retain exact orders, decisions, bias provenance and checkpoints for audit. Retention30days: download artifacts before expiry. Final totals include completed markets only. Report wins/losses/open/unknown, total/mean R, profit factor, closed drawdown, confirmation/timeframe breakdowns, and paired exits resolved across all three targets.

Gross zero-cost R matches the original paper hypothesis. Explicit1/2-pip round-trip deductions are cost hurdles only; they do not model spread-dependent fills, actual historical fees or financing. Closed drawdown excludes floating losses; summed R is not compounded account return. Same-year analysis of rules developed during2026 is an in-sample retrospective study, not an unbiased forward profitability guarantee. The next evidence after this comparison is prospective demo testing with measured execution costs.

# Independent bounded implementation audit

Date: 2026-11-14. Auditor: separate audit agent. Scope: PLAN.md and research.py; targeted synthetic and pre-final data-quality checks only. No strategy exploration, full backtest, or final-period performance inspection performed by auditor.

Audited research.py SHA256: `b4df15d8584a2e731edf54340e37d2184a18bd3d0456862a3b403f729837f30c`.

## Finding

No fatal mathematical or causal implementation defect found for the stated daily screening model. This is implementation assurance, not verification of an economic advantage or executable auction fills.

## Checks passed

- All six signals use completed prior observations only. Mutating current/future prices did not alter the current signal. Prior-day reversal/continuation direction checked with synthetic prices; trailing SMA excludes current session.
- Revised execution order selects the candidate after development and before validation calculations. Selection expression references development Sharpe only. Neighbor validation gates are applied to the selected family, without replacement by another family.
- Full raw JSON is parsed, but final-period OHLC is skipped before access in the daily-row construction. No final-period return statistics are calculated. Corporate-action split-event presence is checked globally; this is not a final strategy-performance test.
- 3,021 development/validation rows, 2010-01-04 to 2021-12-31, pass positive/non-null OHLCV, OHLC ordering, duplicate/order checks, and exact XNYS session-date equality using the calendar package. No missing or extra sessions in these periods.
- Synthetic compounding: +10%, -10%, idle, -10% gives -10.9% total return and 19% end-of-day drawdown. Trade losing streak correctly remains consecutive across an idle day. Trade count and exposure checked.
- Cost algebra is self-financing for adverse entry/exit prices plus both-side proportional commissions. A flat base-cost trade returns -0.000399920013, approximately -4 basis points; idle sessions incur zero.
- Gross, base-net and stressed-net paths are separate. Monthly/calendar-year returns compound. Confidence intervals use deterministic circular three-month bootstrap blocks. Gates correspond to the registered thresholds.

## Resolved before results

Initial implementation computed validation before selecting the development candidate, although selection mathematically used development alone. Code now selects before validation calculations. Calendar completeness checking was added. PLAN.md now explicitly labels end-of-day drawdown, approximate clock exposure, summed-percentage-return concentration, unverified fractional auction execution, and pointwise confidence intervals.

## Remaining limits

- End-of-day drawdown excludes intraday troughs and cannot establish a 20% intraday-loss bound.
- Daily official open/close prices plus fixed adverse costs do not verify order acceptance, auction availability, quotes, actual fills, halts, rejected exits, or exceptional-session execution. Fractional all-equity auction orders are not established as feasible. No stop/target is used, so there is no within-bar stop/target sequencing ambiguity.
- Single-vendor data has not been independently cross-checked; historical vendor revisions remain possible. Positive findings must not advance before independent data verification and whole-share execution feasibility checks.
- Three-month bootstrap intervals based on four validation years are uncertain and pointwise, not adjusted for six comparisons. Passing a gate is not proof of statistical discovery.
- Concentration is summed trade percentage returns, not dollar profit attribution; clock exposure assumes ordinary 6.5-hour sessions and is approximate. Initial trend warmups differ by 100 versus 200 sessions.

Conclusion: suitable to run the frozen development/validation screening batch with these limitations disclosed. A failed validation must stop research and leave final performance untouched. A pass alone does not justify forward paper testing until the stated data and execution checks are resolved.

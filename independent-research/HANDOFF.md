# Independent SPY research handoff
Status: completed; all six variants failed validation. Stop. Final performance unexamined. No forward paper test justified.

Repository: https://github.com/thesolivag/Practice/tree/research/independent-spy-20261114/independent-research
Research code/protocol/data commit: 8df1cff6dae18cbbfabc724f929f1e3a3092e6dc
Workflow: https://github.com/thesolivag/Practice/actions/runs/43623063737
Parent inspected: bb9b698470a7f8d350f7be782c0b678655ee8c63

Run Python 3.12, install exchange-calendars==4.13.3, then `python independent-research/research.py` from repository root. It uses the archived snapshot, not a fresh download. Exact numerical bootstrap uses Python random.Random seed 20261114 and 5000 resamples. Dependence block length 3 months; pointwise intervals, not simultaneous inference.

Data URL: https://query2.finance.yahoo.com/v8/finance/chart/SPY?period1=1262304000&period2=1767225600&interval=1d&events=div%2Csplits
Downloaded 2026-11-14. Source SHA256 e4e49bb5d439b63dd201b6f2285221fa9abf2ff3783920edf89e9a8ee1f9f10e. Vendor history may be revised. 2010–2021 observations pass positive OHLCV, OHLC ordering, unique sorted dates, exact XNYS calendar sessions. No independent price-vendor corroboration. Final 2022–2025 archived in JSON but no final prices, returns, aggregates, charts or outcomes used for selection. No 2026 prices used.

Workspace initially empty. Accessible repository current tree contained workflows, no candles or strategy source. Read workflow plumbing to establish data/Actions access only; legacy rules not imported. Existing broker secret names in old workflow do not prove credentials or data access. Independent workflow uses no broker/database secrets and cannot place trades. GitHub main unchanged.

PLAN.md defines pre-result hypotheses, sample splits, sizing, cost decomposition, gates and stopping rules. research.py contains implementation. AUDIT.md records bounded separate-agent review. results/summary.json records every variant in each observed partition; results/daily.csv records daily gross/base/stress returns and trade indicator including inactive sessions. REPORT.md and monthly.csv present outputs. No unrecorded strategy variations tested. Targeted synthetic checks are implementation tests, not extra hypotheses.

Execution limits: official daily opening/closing prints are fill proxies. Cost inputs are conservative assumptions rather than contemporaneous quote/auction evidence. Fractional all-equity trades not proven available at auctions; commission minimums and whole-share cash residuals unmodelled. Halts, rejects, auction imbalance and MOC availability unresolved. Flat every close, no stop/target, overnight return, margin financing, borrow or dividend cashflow; zero cash interest. EOD drawdown omits intraday drawdown. Approximate clock exposure overstates half-day holding time. Gross and net each compound on their own equity. Returns reset to unit equity for each partition, without resetting signal lookback. Cold start has no pre-2010 warmup, deliberately no later replenishment. Reported concentration uses summed percentage returns unless explicitly identified as dollars. No live deployment or paper execution created.

Decision policy: if selected candidate or neighbor fails validation, stop even if another family looks better in validation; leave final test unopened. This is a bounded negative screen, not proof no other strategy can work. If all gates pass, independent vendor and executable order checks are still prerequisites to final test and paper-test proposal.

Result commit: 23bc0615b04821208264be72c55e4269321cf827. Actions job succeeded in 30 seconds (17:48:08–17:48:38 UTC), below the 60 runner-minute cap. All six hypothesis variants consumed; no further exploration authorized under this protocol. Local work comprised implementation, targeted checks, data download/quality checks and report formatting only.

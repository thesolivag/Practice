# Independent SPY research result

**No dependable advantage found within this fixed research budget. Stop; no final test and no forward paper test recommended.**

Six registered variants were tested in one GitHub Actions development/validation batch. No strategy rules were imported from previous methods. Development selected reversal_0.005 before validation was calculated. Both reversal variants fail the fixed validation gates. Every other variant also fails. Gross/net returns below are compounded cumulative returns for each entire partition, not annual returns.

| Variant | Period | Gross | Net 4bp | Net 8bp | Net Sharpe | Trades | EOD max DD | Net expectancy/trade | Max losing streak | Sessions exposed |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| reversal_0.005 | development | 33.92% | 14.76% | -1.66% | 0.30 | 386 | 13.70% | 4.00 bp | 6 | 19.18% |
| reversal_0.005 | validation | 28.41% | 17.31% | 7.17% | 0.49 | 226 | 17.44% | 7.77 bp | 6 | 22.42% |
| reversal_0.01 | development | 11.55% | 3.06% | -4.79% | 0.10 | 198 | 16.36% | 2.09 bp | 5 | 9.84% |
| reversal_0.01 | validation | 22.12% | 16.72% | 11.57% | 0.55 | 113 | 12.65% | 14.67 bp | 5 | 11.21% |
| continuation_0.005 | development | 5.54% | -13.90% | -29.76% | -0.31 | 509 | 19.83% | -2.70 bp | 6 | 25.29% |
| continuation_0.005 | validation | -6.35% | -17.27% | -26.92% | -0.59 | 310 | 24.01% | -5.75 bp | 5 | 30.75% |
| continuation_0.01 | development | -11.10% | -18.68% | -25.62% | -0.63 | 223 | 21.14% | -8.99 bp | 7 | 11.08% |
| continuation_0.01 | validation | -16.37% | -21.30% | -25.95% | -0.88 | 152 | 23.83% | -15.19 bp | 8 | 15.08% |
| trend_100 | development | 23.53% | -32.50% | -63.12% | -0.63 | 1511 | 38.04% | -2.46 bp | 7 | 75.06% |
| trend_100 | validation | -8.28% | -33.40% | -51.64% | -0.96 | 800 | 37.48% | -4.83 bp | 11 | 79.37% |
| trend_200 | development | 39.30% | -26.08% | -60.77% | -0.44 | 1584 | 31.40% | -1.75 bp | 10 | 78.69% |
| trend_200 | validation | -14.13% | -39.22% | -56.98% | -1.08 | 864 | 42.97% | -5.48 bp | 12 | 85.71% |

## Selected rule and uncertainty

Signal: prior completed close lost at least 0.5% against its preceding close. Buy at next regular-session opening auction proxy and sell at that session closing auction proxy. Long-only, 100% equity, no stop or target, flat overnight. Behavior rationale: temporary selling pressure may reverse next session. The fixed alternative continuation hypothesis and simple trend filter were competing explanations, not later tweaks.

Development: net CAGR 1.74%; 6 positive calendar years; approximate clock exposure 3.58%. Monthly mean return 95% block-bootstrap interval [-0.148%, 0.456%]. Five best trades contribute 101.54% of summed net percentage returns; remaining trades sum to -0.24% (not a compounded portfolio return).

Validation: net CAGR 4.07%; 3 positive calendar years; approximate clock exposure 4.19%. Monthly mean return 95% block-bootstrap interval [-0.350%, 1.155%]. Five best trades contribute 98.36% of summed net percentage returns; remaining trades sum to 0.29% (not a compounded portfolio return).

Validation has 226 trades across just 48 months. Only 3 calendar years are positive. The Sharpe and bootstrap gates fail. At the 1% neighbor threshold the five-best-trade exclusion also turns negative. Positive stressed P&L does not compensate for these failures. The positive development estimate was itself weak and cost-sensitive. The intervals do not adjust for six comparisons; they are screening uncertainty estimates, not evidence of a discovered anomaly. Heavy tails and dependence can make the bootstrap optimistic.

Economic interpretation: daily intraday continuation and these daily re-entered trend filters did not overcome assumed turnover costs. This does not test multi-day trend following or the overnight premium. Daily trend filters were deliberately traded intraday to avoid unverified dividend and financing assumptions; the conclusion applies only to these registered rules.

## Selected rule monthly returns

Net returns, 4bp round trip, with each calendar month compounded from session returns. All variants and gross/stressed monthly returns appear in results/monthly.csv.

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | Year net |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010 | -4.01% | 1.48% | 1.07% | 1.53% | 0.68% | 0.62% | -1.17% | 1.62% | 1.36% | 1.80% | 1.18% | 0.63% | 6.86% |
| 2011 | 0.49% | -0.60% | 0.59% | -0.13% | -0.66% | -0.08% | -0.57% | 2.62% | 2.64% | 4.95% | -1.26% | 0.29% | 8.42% |
| 2012 | -0.21% | -0.01% | 0.62% | -2.19% | -2.83% | 1.75% | -0.94% | 0.37% | 0.38% | -1.87% | 0.35% | 2.08% | -2.59% |
| 2013 | 0.00% | 0.64% | 0.33% | 0.67% | 1.64% | -0.75% | 0.00% | 0.42% | -0.37% | 0.70% | 1.34% | -0.33% | 4.36% |
| 2014 | -1.49% | -1.56% | 0.07% | -1.04% | 0.97% | 0.69% | 0.81% | 1.28% | 0.55% | 0.28% | 0.00% | 0.44% | 0.96% |
| 2015 | -4.04% | 0.89% | -0.83% | -0.04% | 0.47% | -1.58% | -1.62% | -4.56% | 0.51% | 0.59% | 1.12% | -1.39% | -10.17% |
| 2016 | -1.96% | 2.96% | 2.04% | 0.53% | 0.75% | -1.22% | 0.84% | 0.51% | 1.86% | 0.08% | -1.08% | 0.23% | 5.57% |
| 2017 | 0.20% | 0.00% | 0.09% | 0.59% | 0.40% | -0.12% | 0.33% | -0.12% | -0.02% | 0.00% | 0.39% | 0.00% | 1.76% |
| 2018 | -0.67% | -5.96% | -3.21% | -0.20% | 1.59% | 0.87% | -0.10% | -0.33% | 0.27% | -4.02% | -0.56% | -2.27% | -13.90% |
| 2019 | 2.34% | 0.60% | -0.07% | 0.14% | -0.39% | -1.02% | 1.09% | -1.37% | 1.20% | -0.23% | 0.00% | 0.83% | 3.11% |
| 2020 | 1.58% | -1.00% | 11.20% | 4.33% | 1.05% | -2.69% | 4.57% | 0.56% | -1.55% | 2.37% | -0.04% | 1.09% | 22.85% |
| 2021 | 1.11% | 0.24% | -0.18% | 1.97% | -0.33% | 0.97% | 1.55% | 0.54% | -0.96% | 0.83% | -0.28% | 1.89% | 7.56% |

## Verification and limits

Separate-agent audit passed targeted signal causality, cost arithmetic, compounding, EOD drawdown, streak and exposure checks. Calendar comparison verifies all 3,021 development/validation sessions against XNYS. OHLCV positivity, ordering, uniqueness and chronology pass. No full local backtest was run. One successful Actions job ran the registered batch; no failed strategy variations were discarded.

Results remain single-vendor screening estimates. Contemporaneous spreads and auction fills are not observed; the model charges 0.5bp spread, 0.5bp commission and 1bp adverse slippage per side. Stress doubles all three. Real broker minimum fees, rejected orders, halts and auction execution are unresolved. Fractional all-equity auction orders are not verified. The EOD drawdown omits intraday losses; approximate exposure ignores shortened sessions. No independent vendor reconciliation was performed because validation already failed. These limitations could worsen results and do not justify advancing a failed candidate.

No final-period returns or aggregate performance were calculated. No 2026 data, execution system, live trade or paper trading deployment was used. The six-variant hypothesis budget is exhausted; there is no replacement candidate and no tuning against the held-out period. This is not proof that SPY has no possible trading advantage.

## Reproduce

See HANDOFF.md, PLAN.md, AUDIT.md and research.py. Code/data/protocol commit: 8df1cff6dae18cbbfabc724f929f1e3a3092e6dc. Actions run: https://github.com/thesolivag/Practice/actions/runs/43623063737 . Research branch only; main unchanged. report.py transforms saved summary outputs into this report and monthly.csv without rerunning the backtest.

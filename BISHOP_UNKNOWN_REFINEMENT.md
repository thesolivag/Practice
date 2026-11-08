# One-minute execution audit of unknown yearly trades

Separate workflow: `.github/workflows/bishop-unknown.yml` (manual or push to that file).
Pinned source run: https://github.com/thesolivag/Practice/actions/runs/42371042901
Pinned source commit: `861549cbd919021905ad721f9799f969a5ceacf8`.
Period remains 2026-01-01 through 2026-11-07 11:00 UTC. This is not a new year replay.

Only original CENSORED orders from the final monthly checkpoints are examined.
Original frozen signals, entries, SL, TP, quantity, recorded cancellations, costs
and historical cutoff are retained. No strategy detector runs and no new entry
is created. Previously resolved outcomes are not altered. The exact original
simulation module is checked by SHA256. Each original unknown must reproduce
before refinement is permitted.

The executor replaces ambiguous H1 bars with 60 complete M1 bars from the same
primary provider. Both a current H1 download and the M1 rollup must exactly match
the frozen H1 OHLC. Duplicate/missing minutes, changed prices, absent broker data,
unknown original execution or still-ambiguous within-minute sequences remain
unresolved. There is no Dukascopy substitution, forward fill or SL/TP ordering
assumption. The original source did not retain broker environment/symbol identity;
we use its configured cTrader demo provider and record current public symbol
identity plus exact H1 comparisons, rather than claim archived identity proof.
Deriv uses its original public feed. Raw minute/hour evidence is saved with hashes.

Subsequent hourly ambiguities can also be refined, bounded at 128 hours per order.
Once a pending trade was censored, the original replay ceased gathering its
later cancellation decisions. If minute evidence does not prove a fill by that
original censor point, it stays unknown. Proven fills can be followed to their
frozen exits. This is a fixed-cohort outcome audit, not a rerun of capacity,
subsequent bias decisions, portfolio allocations or new signals.

Each market job has 120 minutes; network work has a 90-minute budget. Two market
jobs can run concurrently, with the shared market and personal feed locks around
each one-hour cTrader acquisition. Connections close and leases release between
hours so live scanners can acquire the feed. Broker authentication may refresh
existing tokens via the existing token manager; no paper/live trading tables,
orders, notification settings or Telegram messages are written by this workflow.
No live scanner or original year workflow is modified.

Artifacts: `unknown-PAIR` contains per-order before/after evidence and minute files;
`unknown-report` contains REPORT.md and REPORT.json. The report compares the same
26 eligible markets as the original report, preserves original totals separately,
and shows newly won/lost, still unknown, open, added gross R and unresolved causes.
Other markets are retained separately in JSON. Missing jobs make coverage PARTIAL.
Completion does not mean every unknown was resolved. R excludes transaction costs.

Validation: targeted synthetic tests cover both TP-first and SL-first paths,
within-minute ambiguity, exact rollup/coverage, frozen-order immutability, cutoff,
source reproduction, download failure redaction, missing management, budgets and
partial report aggregation. Actual downloads and full audit run on GitHub only.

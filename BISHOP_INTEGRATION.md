# Bishop alongside KK — paper integration

Bishop is a separate paper strategy in the existing web app. Entries and private
Telegram entry/result messages identify **KK · Paper** or **Bishop · Paper**.
The Entries strategy filter and separate paper summaries avoid mixing KK's
TP1/TP2 accounting with Bishop's single qualified target. Existing KK records,
settings, history and strategy calculations are preserved.

## What runs

The existing `bishop_confirmation` v2 engine is vendored from Bishop snapshot
`6e1caa0417cedfa10b276867f3daec83a08b57f9`; see bishop/PROVENANCE.md. It keeps
H4 context, explicit liquidity/reaction lineage, model-specific confirmation,
retest level, logical stop and nearest eligible liquidity target. It does not
replace KK's continuation/QMR logic or add a universal 24-hour reaction rule.
Direct/aggressive/nested Bishop profiles are not enabled by this integration.
Historical mentor-example acceptance remains incomplete.

`python -m slk.bishop_paper` runs after the successful KK hourly step, under the
existing shared feed lock. It reads primary stored candles without opening a
broker connection or using the Dukascopy fallback overlay. Selected watchlists
and per-user delivery preferences are respected. A new **Bishop paper entries**
setting controls new entries; turning it off continues tracking existing paper
entries on still-selected markets. Removing a market explicitly suspends tracking
without inventing a close. Users and deferred markets rotate fairly within the
six-minute budget; a market child is killed after 15 seconds. Deferrals and
unsupported calendars are shown in Entries → Bishop scan details.

First scan activates each selected market at the current time and imports no
old signals. Subsequent scans consider new setups after activation, with at most
seven days of bounded catch-up. Paper results assume hypothetical submission at
the completed setup time, not actual Telegram receipt time; hourly delivery may
be later. No broker order is created. Bishop has no approval button and its IDs
cannot be passed to the numeric KK approval route.

## Declared limits

- Detection uses 35 days of context, so older monthly/weekly context may be
  unavailable. Frozen paper execution uses up to 180 days of primary H1 data.
- H1 data supports H4/H3/H2/H1 entries. There is no invented subhour data.
- Primary cTrader FX uses the DST-aware New York-close calendar. Continuous
  Deriv uses UTC and its MID quote series. Metals, indices and other calendars
  remain unsupported for Bishop until their schedules are explicitly supplied.
- All Bishop costs are explicitly zero. MID quotes are allowed only under this
  zero-cost synthetic-price paper hypothesis. R is not net broker performance.
- Ambiguous OHLC, gaps, revised observed candles or missing original active
  history stay **Unknown**, with their reason and frozen original plan. Unknown
  exposure remains reserved; it is never converted into a win/loss.
- Explicit causal story events cancel pending dependent orders. A disappearing
  setup is not a cancellation, and a story cancellation does not close an
  already filled position.

## Storage and delivery

The same database is reused. New `bishop_app_entries`, `bishop_app_state` and
`bishop_app_outbox` tables carry explicit `user_id` ownership. No Bishop row is
attached to a KK bias ID. Plans, price/source metadata and costs are immutable;
terminal paper results do not regress. Execution-prefix hashes detect revisions.
A transaction records each entry/result and its deduplicated private outbox
message. Delivery claims have leases; Telegram itself does not provide exactly
once delivery across a crash after sending and before acknowledgement.

Resolved Bishop records and sent outbox messages are retained for 30 days;
open/Unknown entries are preserved. The summary explicitly covers at most the
most recent 500 Bishop records. Existing KK and personal-alert retention is
unchanged. No production messages or user preferences are created for testing.

## Validation

Independent source/integration review; deterministic closed-bar/source/price-grid
and frozen-order replay tests; explicit Unknown/revision tests; disposable MySQL
ownership, immutable-plan and concurrent-delivery tests; compact/full engine
parity tests; signed API strategy-filter and approval-boundary tests; mobile
browser labels/filter/results/no-Bishop-approval checks. The bounded deterministic
35-day FX benchmark completed in 4.797 seconds; both 180-day variants exceeded a
45-second guard, motivating the documented detection bound.

## Target hierarchy correction (2026-11-05)

The trade target is the nearest qualified setup-local external liquidity or
source-supported H4 exit key level. A local external range can sit inside the
larger storyline range. The larger story objective is displayed separately;
automatic discretionary extensions or partial exits are not implemented.

Range boundaries use close prices, whereas their named turn-leg liquidity uses
wick prices. Qualification verifies the exact published turn and candle evidence
instead of requiring these different prices to equal. Continuation ownership is
recorded explicitly and ambiguous ownership remains unresolved. A close-line
break alone does not consume an untouched wick target.

The first scan after this revision starts new detections from its activation
time, preventing retroactive alerts from corrected historical plans. Existing
frozen paper orders retain their original geometry and execution tracking.
Teacher-example agreement remains incomplete; see
`reports/teacher_validation/2026-11-05-target-fix/REPORT.md`.

## Confirmed web-bias gate

New Bishop orders require a current, watched, trade-eligible CONFIRMED bias from
the same user's existing web-app bias table. The latest row per market/timeframe
is authoritative; an ended row never revives an older confirmed row. Watched
confirmed biases must agree with the entry direction. A linked H4 break must be
known after the web bias confirmation and before the entry. The Bishop detector
continues to validate its liquidity/reaction/confirmation sequence. The gate runs
before ambiguity/deduplication/exposure selection.

Each new order freezes the web bias ID, timeframe, side, confirmation clock and
H4 sponsor evidence. Entries and messages display alignment. Historical rows
without this evidence are explicitly marked Legacy; their outcomes are not
rewritten. Still-pending legacy orders, or linked orders whose web parent is no
longer eligible, receive a cancellation at the observation time. Filled orders
retain their original geometry and continue tracking. A fresh revision watermark
prevents backfilling newly eligible historical signals.

Stop review: the saved Bishop branch and integrated entries.py use the same
confirmation protection logic. The saved engulfing correction is present. The
archived breakout review explicitly leaves the earlier-take-low issue unresolved;
it does not certify every breakout stop. No speculative stop/RR adjustment is
included in this alignment change.

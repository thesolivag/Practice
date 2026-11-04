# Bishop entries and the Kevin web app — 2026-11-04

Reviewed Bishop snapshot `6e1caa0417cedfa10b276867f3daec83a08b57f9` from
`thesolivag/Practice`, branch `claude-bishop-aggressive`, alongside Kevin
`70a34ad36c77936dec157dd15ef40aaa9a2dbca1`.
This is a source/code review, not a new strategy deployment or teacher-example acceptance.

## What the current Kevin app does

`slk/entry.py` implements Kevin's continuation (A-series) and QMR (B-series)
entry paths. The Entries/Paper results tabs refer to that engine. Personal
confirmation watches in `slk/user_alerts.py` detect Breakout, Engulfing and
4th man; selecting a confirmation is not equivalent to selecting Bishop's
whole bias-to-entry sequence.

## The sequence described by the user exists in Bishop's material

Primary text: Bishop `knowledge-base/videos/bishop-entries-part5/transcript.txt`.

- 42.2–79.7: H4 breakout or sweep-and-break confirms daily context; then seek
  entries toward the external liquidity objective.
- 156.9–221.2: one direct H4 route waits for liquidity formation and places the
  limit at the relevant key level, anticipating the sweep and expansion.
- 240.5–284.2: liquidity may be single-candle or structural/a series of candles;
  Bishop explicitly says it may not be the immediate single candle.
- 291.0–334.6: the confirmation route instead waits for price to trade into
  the H4 key level and react before seeking lower-timeframe confirmation.
  Waiting for the H4 *reaction* candle to close is described as personal choice.
- 337.5–366.7: confirmation timeframes include H3, H2, H1, M45, M30, M15 and M5.
- 376.7–459.6: breakout, sweep-and-break and engulfing are described.

The direct H2 route has a distinct explicit H4 *breakout-close* requirement
(103.9–108.9). An optional reaction-close choice must never be used to accept
an unfinished breakout or unfinished confirmation.

No universal 24-hour reaction requirement was found in this session. The
user's phrase may mean “reacts on four hours/H4”; this needs clarification
before introducing a duration rule. Bishop's policy currently has an optional
1440-minute pending-order expiry; that is an operating policy, not proof of a
teaching rule. It is separate from the requested one-day personal-watch default.

## Existing implementation and limits

Bishop `bishop/v2/entries.py:detect_setups` has distinct `direct_h4`,
`direct_h2`, `confirmation_bo`, `confirmation_sweep_bos`,
`confirmation_engulfed_oc`, `confirmation_standing_extreme` and other named
source-specific routes. Its reaction episodes, liquidity lineage and retest
levels are explicit. `bishop/v2/types.py:StrategyPolicy` defaults to
`bishop_confirmation` and supports multiple entry timeframes.

The current Bishop handoff requires H4 liquidity → key-level reaction →
source-timeframe confirmation → retest entry, with stops derived from the
selected confirmation and separate nearer liquidity/HTF objectives. Historical
teacher-example verification remains incomplete; a passing regression suite
must not be represented as full mentor matching or profitability.

Bringing this into the Kevin app requires a separate strategy selection,
Bishop-specific storage/settings, qualified selected-market broker data at
supported resolutions, and tests of the complete causal chain. Copying only
confirmation names or replacing Kevin's entry function would lose these rules.
No Bishop code or live Kevin strategy rules were changed in this alert release.

## Delivered alert behavior

New personal alerts default to one day in the web form; entering Confirmation
resets its default to one day. An explicitly chosen one-week duration remains
available. Existing saved expiries and retained event history are unchanged.
Pause applies to ACTIVE personal price/confirmation watches; resume skips
signals during the paused interval and resets sampled-price baselines. Pausing
does not extend expiry. A triggered/pending delivery must finish or be cancelled
rather than silently discarded. Paused watches count toward the account limit
and can be cancelled. All controls retain per-user ownership.

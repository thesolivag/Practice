# Browser, alerts, journal and replay

Telegram remains the account identity. These tools share the same account and watchlist; they do not create a second trading account.

## Connect a browser or Chrome extension

1. Open the Telegram Mini App and select **Browsers**.
2. Generate a code for **Browser** or **Extension**. Codes last five minutes, work once, and are tied to that purpose. A newer code replaces an unused code of the same purpose.
3. For a browser, open https://slk-backtest-viewer.onrender.com and enter the code. For the extension, use its popup.
4. Review and revoke sessions from Telegram. Sessions expire after 30 days, with at most 10 active sessions per account. Signing out revokes the current session.

Browser sessions use a secure HttpOnly cookie plus same-origin CSRF protection. Extension tokens are stored only in the extension's trusted worker context, can manage manual alerts, and cannot access journal data, change account settings or approve broker orders. Broker approval remains Telegram-only.

Download the extension at `/extension/download`, unzip it, open desktop Chrome's `chrome://extensions`, enable Developer mode and choose **Load unpacked**. Select the directory containing `manifest.json`. See [extension/README.md](extension/README.md) for permissions and Chrome Web Store publication steps. No extension has been published to the store. Standard mobile Chrome does not install desktop extensions; the Mini App supplies the same alert form on phones.

## My alerts: two separate flows

Choose **Price alert** or **Confirmation alert** in the Mini App or chart extension. Their controls and trigger rules are separate; both use your Telegram account and saved user scope. Neither places an order.

### Price alert

Choose a market and required price, then sampled crossing, closed-candle crossing, close above/below or rejection. Candle-based choices use the selected timeframe. Model selection and lower-timeframe engulfing do not apply to a normal price alert. Quote crossings compare fresh samples; a cross that reverses between minute checks can be missed.

### Confirmation alert

Choose one or more of the three approved models, or **Any of these models**, and up to six timeframes. **Anywhere on this market** watches for the selected patterns without requiring a price. **At a level** also requires a reaction at your chosen price. Choose **First matching event** or **Each new event until expiry**. The optional lower-timeframe engulfing filter applies only here.

- **Breakout** includes breakouts with or without a liquidity sweep. A completed close breaks the latest confirmed close-line swing. The local swing uses one completed neighbour on each side; this is a bounded detection setting, not a claim to reproduce every discretionary structural reading.
- **Engulfing** invalidates an opposing open-close key level formed by two consecutive opposing candles. The line is the first candle's close, near the second candle's open. BUY closes above that line; SELL is mirrored. It need not engulf both bodies or cross the first candle's open. An already-broken boundary is not reused.
- **4th man** sweeps the previous low for BUY, leaves its high standing and closes strictly inside the previous range. SELL is mirrored; neither candle has a mandatory colour. The sweep close is a candidate level for a later retest. A formed confirmation does not mean a retest/entry has happened.

The lower-timeframe filter uses the same open-close engulfing definition, rather than textbook two-body coverage. Confirmation context is limited to eight bars. Missing components, unfinished candles and stale quotes are rejected. Level-touch evidence must start at or after watch creation; a partially elapsed creation candle cannot prove when its touch happened. Equality at a breakout/engulfing boundary is not a break; 4th man requires a strictly standing opposite extreme and strict inside-range close.

Timeframes use real finer candles when available: H1 history cannot reconstruct M5. FX follows the existing broker/New York calendar; Deriv uses UTC. The minute scanner still shares acquisition over only selected pending markets and observes the existing scan budget. Delivery can be deferred when the checker is busy.

Recurring alerts retain separate delivered-event snapshots for replay, instead of moving the replay time of an older alert when another confirmation arrives. Successful deliveries advance detection cursors; the next minute does not deliberately send the same event again. Failed delivery remains pending. Notification history keeps at most 1,000 events per user, 10,000 globally, 30 days and an 8 MiB logical global budget. Older snapshots can be evicted by these limits; candles remain shared rather than duplicated per user.

Old `pinbar_v1`/`cisd_v1` watches remain retired and must be recreated. Legacy valid one-model watches preserve their level-scoped behaviour. The form/schema provide current validation limits. See [Bishop source recheck](knowledge-base/study/bishop_confirmation_source_recheck.md) and source-derived normalized tests in `tests/test_confirmation_models.py`; those tests establish coded behaviour, not measured live accuracy.

Set cron-job.org to **GET every minute**:

```text
https://slk-backtest-viewer.onrender.com/cron/alerts?key=YOUR_EXISTING_CRON_SECRET
```

Replace the placeholder with the private Render `CRON_SECRET`, or send that secret in `X-Cron-Secret`. This endpoint accepts a short request and starts the checker directly in the web service. It does not dispatch a GitHub job and does not need `GH_DISPATCH_TOKEN`. Duplicate admissions within55seconds are ignored; overlapping checks defer safely. A200 response means accepted, not that every watch has already been evaluated. Free-service restarts, slow broker requests and a busy checker can delay a check; durable pending watches catch up on subsequent calls.

The checker uses only pending selected markets, up to4perbatch, and a cooperative40secondbudget that reserves processing/deliverytime. Slow initial authentication or provider calls may overrun that budget; a lock prevents overlapping workers. Quote-only watches download no history; smaller-timeframe watches fetch only their needed minute context. D/W watches reuse incremental hourly files. No language-model calls are used. Confirmation watches await completed candles; price crossing compares samples and can miss moves between checks.

The old five-minute GitHub schedule has been removed. The **Personal alert checks and replay cache** workflow remains a manual bootstrap/warmup tool; `configure_only=true` syncs private application/account credentials from existing Actions secrets into server-only database keys, atomically. Those credentials and OAuth tokens are not in public settings or extension code. The hourly workflow also maintains this server configuration. Neither credential values nor Telegram bot secrets are sent to a browser.

The extension detects supported TradingView/Deriv symbols, follows chart changes, and opens its floating dock by hover, focus or click. A manual override stays selected until **Follow chart** is chosen. The price field clears when the market changes to prevent reusing another chart's level. Prices are entered explicitly; the extension does not guess prices from a chart canvas. Existing unpacked installations must reload/redownload version0.1.3.

## Lightweight journal

Create a manual journal note or link it to your own alert/entry. Record entry, stop, target, result in R, outcome and notes. Values are manually recorded, distinct from broker fills or simulated results. Limits: 200 records/account, 2,000 characters/note, 8 MiB shared logical storage budget. Images and attachments are not accepted.

## Replay: alert replay and price replay

**Alert replay** starts from your own historical bias, entry or delivered personal-alert event. Its starting clock is the recorded event time. Immutable personal-alert snapshots supply the original known event/level markers; mutable later targets/results are not passed off as historical knowledge.

**Price replay** starts from a chosen market and historical date/time. It does not require a saved alert, create a fake alert, or add a journal entry. Use it for manual chart practice independently of notifications.

Both modes offer H1/H2/H3/H4/D/W from actual retained H1 candles. Subhour replay is not available from this cache. Switching timeframe preserves the same replay clock; only complete candles known by that clock are shown. **Next candle** advances in the selected timeframe; **Play** repeats it. Reset returns to the original alert or chosen starting time. Gaps remain visible, partial higher-timeframe bars are omitted, and provider/calendar labels remain visible.

Each request uses at most 505 hours of H1 source data. D/W initially use 21 days of earlier context; intraday starts and forward steps use 14 days back and seven days ahead plus one hour for DST. Forward windows roll with the clock, so practice is no longer limited to seven days. Panning to the left loads another bounded page without changing the replay clock. Higher-timeframe pages remain sparse until more history is loaded; this is not native multi-year D/W acquisition. The shared compressed database cache has a 16 MiB logical capacity; no per-user candle duplication. Missing windows first attempt bounded on-demand broker H1 acquisition under shared feed/publication leases, with process throttling. Completed candles are cached in monthly chunks; unavailable/busy requests fall back to queued publication from existing incremental candle files. No full three-year archives are created by this path. Opening or stepping a replay never makes an unbounded broker-history request. Historical coverage depends on retained data; a calendar picker does not guarantee every date is available.

Signed replay cursors are bound to user, mode, market, starting time and timeframe. Alert sources are re-authorized on stepping/timeframe changes. The hourly and personal-alert workflows publish queued windows. GitHub's transient candle cache is acquisition input, not the durable replay service. This is manual candle replay, not a profitability-tested automatic backtesting engine.

## Operations and validation

The canonical `db/schema.sql` and fallback `webapp/schema.sql` contain idempotent tables for pairing, sessions, watches, journal and shared replay. Component SQL files are kept as readable definitions; edit the canonical/fallback copies together for later migrations.

Set `APP_ORIGIN` to the exact public HTTPS origin when running behind a proxy (configured in `render.yaml`). Keep database/broker/Telegram credentials in existing server/Actions secrets, never extension code. Run:

```sh
python -m pytest -q tests
node tests/ui/workspaces.cjs
node tests/ui/extension.cjs
```

Real database tests require `SLK_TEST_MYSQL` pointing to a disposable MySQL 8 database. They must never point to production. Browser tests need Playwright and Chromium (`CHROMIUM_PATH` can override its path).

### Full-screen replay workspace

The viewport uses vendored TradingView Lightweight Charts5.0.8 (Apache2.0, shipped LICENSE/NOTICE and chart attribution). This is our replay application built on its renderer, not the complete proprietary TradingView application.

Drag/pinch/wheel navigation, draggable scales, crosshair OHLC inspection, fit and return-to-head controls keep chart navigation independent of replay time. A compact bottom strip provides select-bar, restart, play/pause, next candle and speed. Shift+Right steps; Shift+Down toggles playback outside form fields. Select bar explicitly starts a price replay at that completed candle's close. Settings/exit or Escape leaves the full-screen workspace. Axes, crosshair and input use the account's timezone.

Horizontal lines, trend lines, rectangles, text and long/short risk/reward are practice annotations. Select and drag an object, or drag selected handles to move endpoints/corners/prices. Risk/reward starts with a configured ratio; independent entry/stop/target handles recalculate the displayed R. The collapsible editor accepts exact prices/times/text. Undo/redo retains up to50 snapshots and drawings are capped at50. Notes are canvas text, never HTML. Drawings use price/time anchors, survive pan/zoom/timeframe changes, and clear on a new replay or restart. They remain in memory only: no cross-reload resume, database drawings, journal fills or live orders.

Older pages are fetched only after chart navigation or the Earlier control, with one request in flight. Busy/unavailable pages preserve the chart and boundary for retry. Step failures preserve the chart; playback stops when there is no newly completed candle, avoiding repeated requests. Stale responses and mixed-provider pages are discarded. Only revealed closed bars enter the renderer and its autoscale/crosshair. The existing16MiB shared cache ceiling and feed/publication locks remain; minute replay, native multi-year D/W context and persistent session resume are not included.

Validation uses deterministic multi-bar synthetic FX/continuous-market fixtures with weekend gaps, deliberate future-price sentinels, mobile/desktop layouts, pan/zoom/OHLC, older-history loading, drawing drag/undo/redo and timezone checks. These test interactions and safeguards, not live broker accuracy or full TradingView feature parity.

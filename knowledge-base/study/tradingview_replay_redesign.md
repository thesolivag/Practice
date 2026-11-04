# TradingView Bar Replay research and SLK replacement model

Implementation update 2026-10-27: the viewport, compact controls, direct drawing manipulation and bounded older/rolling-forward history are now implemented. See WORKSPACE.md for shipped scope and limitations. Native multi-year D/W history and persistent resume remain outside this implementation. The research below records the original assessment.

Reviewed 2026-10-27. User requested research before another redesign. Interpretation: voice transcription “13 review” means TradingView. No production UI changes in this research pass.

## Sources actually inspected

1. TradingView, Bar Replay: how and why to test a strategy in the past:
https://www.tradingview.com/support/solutions/43000712747-bar-replay-how-and-why-to-test-a-strategy-in-the-past/
Read full official guide; inspected its toolbar and playback-speed screenshots. Documents select bar/date/first available/random starting point, play/pause/manual forward, configurable speed, time-synchronized intervals, saved session restore, drawings, historical-availability boundaries and shortcuts.
2. TradingView Lightweight Charts product:
https://www.tradingview.com/lightweight-charts/
Interactive financial charts, mobile interactions, custom data, Apache2.0 open-source. This is a chart library, not the complete tradingview.com product.
3. Lightweight Charts documentation:
https://tradingview.github.io/lightweight-charts/
Current documented library supports series, custom plugins and chart APIs. Pin a version and ship attribution/license with vendored assets.
4. Advanced Charts FAQ:
https://www.tradingview.com/charting-library-docs/latest/getting_started/Frequently-Asked-Questions/
Requires supplying a datafeed; distribution/access and use conditions differ from Lightweight Charts. No assumption that existing app has access or that embedding this library supplies Bar Replay.
5. Advanced Charts Datafeed API:
https://www.tradingview.com/charting-library-docs/latest/connecting_data/Datafeed-API/
History requests should prioritize enough bars (countBack), chronologically ordered; explicitly signal exhausted history. Symbol timezone/session metadata matters.
6. Trading Platform documentation:
https://www.tradingview.com/charting-library-docs/latest/trading_terminal/
Restricted-access separate product; trading widgets require additional integration. Not needed just to practice replay.

Evidence limit: inspected official public docs/screenshots, not an authenticated TradingView paid replay session or a user-provided set of 13 templates. Do not claim pixel-perfect parity or that drawing drag interactions were manually exercised in TradingView.

## Why current implementation fails as a replay workspace

- webapp/journal_replay.py fixes context to14calendar days and forward range to7days for ALL intervals. Forex daily context is about10bars; complete weekly context is extremely small. Higher-timeframe charts therefore look sparse and cannot support meaningful historical browsing.
- slk/replay_cache.py MAX_BARS512 and 21day API envelope block loading older history when panning. Earlier button only slices already-loaded bars.
- app.js uses manually painted canvas and elapsed wall-clock spacing rather than a chart viewport. rangeEnd remains at replay clock when looking left; weekends and earlier browsing can produce excessive empty space.
- No standard crosshair/OHLC candle inspection, direct pan/pinch interaction or draggable scale. Buttons are not substitutes for those interactions.
- Stacked tools/forms consume much of a mobile screen; drawings use tap-to-move rather than direct shape/handle dragging. Labels and drawing positions need renderer-managed coordinates.
- Current backend exposes H1/H2/H3/H4/D/W only. There is no genuine subhour/monthly replay or archive infrastructure to claim as already implemented.
- Existing closed-bar and user-ownership checks are valuable and should survive replacement.

## Replacement model (implementation specification)

Use TradingView Lightweight Charts as the rendering foundation, preserving attribution. Build our replay controller and drawing tools on its documented APIs/primitives. Do not claim this imports TradingView's proprietary full app or its complete replay functionality.

Chart workspace:
- Dedicated viewport, compact top market/timeframe/timezone controls, central chart taking most of usable screen, side drawing toolbar on desktop/collapsible toolbar on phone, compact bottom replay strip.
- Drag to pan, wheel/pinch zoom, crosshair and candle date/OHLC readout, legible time/price axes, scale adjustment, fit/reset and return-to-replay-head.
- Viewport state independent of replay clock. Looking left never rewinds/reveals data; playing can follow head unless user deliberately browses history.
- Loading/error states must stay inside the chart without blanking existing candles or moving the workspace back into settings.

Replay:
- Choose start by chart candle or settings-timezone date; show earliest available date honestly.
- Play/pause, one completed candle forward, adjustable bar rate, restart/change start; keyboard shortcuts ignore focused form fields.
- Preserve one UTC replay clock when changing intervals. No OHLC from after that clock reaches series, autoscale, tooltip, drawings calculations or indicator inputs.
- History requests before the clock allowed; cached future candles stay inaccessible until revealed. Efficient stepping without full chart rebuild each candle.
- Resume state stores small metadata, not copied history; isolate by account and clear on logout. Decide client-local vs bounded DB retention before implementing persistence.

History:
- Replace fixed14day context with resolution-aware paging, targeting roughly200visible/context candles as an initial UX goal, subject to real source availability.
- Fetch earlier pages as viewport approaches left edge; stop with explicit oldest-available boundary. Rate-limit and deduplicate requests and retain16MiB compressed shared-cache ceiling.
- H1 backing data is inadequate as an efficient universal history transport for years of W/D. Use provider-native higher intervals or aggregated archive chunks; authentic lower intervals must be acquired separately. Preserve broker sessions/DST when aggregating.
- Three-year archives are a storage option, not an existing feature. Do not start bulk acquisition until archive schema, refresh/manifest, source coverage and retrieval are implemented and tested.
- Distinguish archive/history store from hot replay cache. Do not increase database capacity silently.

Drawing interactions:
- Horizontal line, two-point trend line, rectangle zone, text, long/short risk/reward.
- Place, hit-select, drag whole object, drag endpoint/corner handles, edit properties, delete, undo/redo, optional snapping.
- Persist price/time anchors rather than pixel coordinates. Snap to candle where requested; pan/zoom/timeframe changes must not drift objects.
- Long/short tool exposes entry/stop/target handles and computes R from those prices; fixed-R is an optional constraint, not the only usable workflow.
- Canvas text never becomes executable HTML. Explicit annotation limits; no implied live order execution.

## Acceptance gates before replacing production

1. Real multi-bar IC Markets and Deriv fixtures, not only one synthetic oversized candle. Include weekends, DST/session boundary and data gaps.
2. On390px phone and desktop, chart navigation and candle inspection work without manipulating a long form or relying on Earlier/Later buttons.
3. Dragging left loads older history and preserves viewport; D/W expose meaningful context where available. No empty-space stretching to replay head.
4. Crosshair gives correct candle/time/OHLC; Lagos input09:00 resolves08:00UTC and displays09:00 consistently.
5. Play/pause/speed/step and timeframe switch preserve replay time; no future candle leakage, including higher-TF unfinished bars and stale responses.
6. All drawing tools pass placement, hit-selection, whole-object dragging, resize/endpoint dragging, editing, deletion and undo/redo across zoom/timeframe changes.
7. Cache hit avoids broker fetch; miss is bounded, deduplicated and reports unavailable/busy honestly; database and request budgets verified.
8. Test actual touch/pointer interactions and visually inspect representative charts. Existing functional form tests alone do not establish chart usability.

Implementation order: renderer + viewport/candle inspection → resolution-aware history/clock integration → compact replay controls → drawing primitives/handles → persistence and realistic usability regression. This research commit does not mark that replacement as delivered.

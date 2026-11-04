# Radar feature separation recheck — 2026-10-26

Requested scope: recheck the extension/replay video and distinguish price alerts from confirmation alerts, and alert replay from standalone price replay. This document is an audit and the corrected feature boundary, not an implementation claim.

## Evidence re-inspected

New Radar update video: `knowledge-base/videos/kevin-devt-building-the-slk-bias-bot-new-featuress-on-slkradar-journal-feature-alert-replay-b/transcript.txt`. Visually inspected all four contact sheets and native frames at 05:10, 05:55, 07:00 and 09:40.

- 03:44–05:03: normal price watching, sampled crossing, candle close above/below and rejection. Price is the trigger reference; a confirmation model is not required.
- 05:04–06:45: the extension's **Alert me** selector changes to **Confirmation**, separately from its **Condition** selector and timeframe. Optional lower-timeframe engulfing is another control. [Native 05:10](examples/radar-update-t310.jpg).
- 07:00: the screen says **One Telegram message when a 4th's pin-bar confirmation forms at 2786.5430 on any timeframe from 30m to 4h, with a lower-timeframe engulfing. Either direction.** This proves separate type/model/timeframe controls, multi-timeframe selection and a one-shot level-scoped confirmation in that demonstration. It does not prove recurring alerts, unrestricted no-level scanning, or an "all models" option. [Native 07:00](examples/radar-update-t420.jpg).
- 09:07–10:23 and 12:08–13:18: history/Telegram → particular alert → replay; chart timeframe can change and candles can advance. He explicitly says **this feature is just to play back your alerts** around 09:58–10:03. [Native 09:40](examples/radar-update-t580.jpg).
- The reviewed video does not establish an independent pair/date replay launcher. The user separately requested ordinary price replay/backtesting-style practice; that should be treated as its own requirement, not claimed as observed footage.

## Current implementation gaps

1. `extension/content.js` and `webapp/static/index.html` expose a single mixed Condition selector. Price conditions and the three confirmation models are blended.
2. `slk/user_alerts.py:validate` requires a positive `level` for every watch and only accepts one model/timeframe. The current lifecycle emits one notification and becomes FIRED. It is not an unrestricted or recurring confirmation subscription.
3. The recent model correction added Breakout, Engulfing and 4th man, but did not separate the feature flows. Correct detector names do not establish complete product functionality.
4. `webapp/journal_replay.py` accepts an owned bias/entry/watch as replay source. Its `source()` rejects a free pair/date source. The Replay form requires a saved alert. There is no standalone price replay entry point.
5. Current replay serves closed H1 candles only. Timeframe switching shown in Radar is not implemented. The shared cache/queue is reusable infrastructure, not proof that full chart replay exists.

## Correct separation

| Flow | User chooses | Trigger or starting point | Independent of |
|---|---|---|---|
| Price alert | market, price, crossing/close above/close below/rejection, relevant timeframe, direction, expiry | price condition becomes true | confirmation model selection |
| Confirmation alert | market, one or multiple of Breakout/Engulfing/4th man (including Any), timeframe(s), direction, optional lower engulfing; optional At a level scope | selected completed-candle confirmation forms | merely crossing a price and having a saved bias/entry alert |
| Alert replay | own historical alert → Replay | actual stored event time, with event/level markers | manually choosing an unrelated start date |
| Price replay | market, historical start date/time, timeframe → Start | chosen historical clock; future candles hidden until advanced | existence of a saved alert |

Expose Price/Confirmation as distinct choices in both Mini App and extension, with different condition/model controls and explanatory text. Confirmation should support an explicit **Anywhere on this market** versus **At a level** scope so the user's any-confirmation request is not accidentally restricted by the normal price form. Price alerts must keep price mandatory. Do not silently remove level scoping from existing confirmations: it has a distinct meaning.

For confirmation delivery, explicitly distinguish **first matching event** from **each new matching event until expiry**; the current one-shot lifecycle must not be advertised as "whenever". Recurring mode needs event identities, retained user-specific delivery claims and per-event deduplication, not repeated sending of the same old pattern every minute. The video's one-message demonstration remains one-shot evidence; recurring mode is a user-requested extension.

Expose **Alert replay** and **Price replay** as separate modes, even if they share the same chart component and cache. Reset labels, source validation and cursor identity must reflect the selected mode. A price replay must not manufacture a journal or fake alert just to satisfy the old replay API.

## Acceptance checks before claiming the separation built

- Price flow offers only price conditions, requires price and does not apply confirmation or lower-engulfing fields.
- Confirmation flow offers exactly the three approved models plus multi-select/Any; no separate sweep-and-break/CISD. Anywhere scope evaluates patterns without a fake price; At a level preserves reaction ordering.
- Selected timeframes/models are evaluated independently; the notification identifies which actual model/timeframe matched. Repeated minute calls do not repeat an already delivered event.
- Union only users' selected instruments/timeframes for acquisition; reuse one provider snapshot and the existing minute budget. No catalogue-wide scan or runtime AI calls.
- Alert replay authorizes the event and starts at its real event time. Price replay authorizes a known selected market and bounded date window without requiring an alert ID.
- Both replay modes hide all candles beyond the replay clock, including after timeframe switching, reload and cursor replay; signed cursors stay user/mode/market/timeframe bound.
- Both modes report missing data and limits honestly. Reuse the shared bounded candle cache and publication queue; don't make every chart click request broker history.

Follow-up implementation (2026-10-26): separate Price/Confirmation controls, model/timeframe selection, scope, recurring immutable event delivery and distinct Alert/Price replay launchers are now built. H1-derived higher timeframe switching preserves the replay clock. The code-gap list above records the pre-correction state. Subhour replay is still unsupported by the retained H1 cache; standalone history availability remains bounded. See WORKSPACE.md and the handover for validation and deployment status.

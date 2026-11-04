# SLK Chart Alerts (Chrome Manifest V3)

This extension creates personal SLK watches from supported TradingView chart pages and Deriv charts. The server evaluates conditions and sends Telegram messages; keeping a chart open is not required. Available conditions and timeframes come from the server. Candle conditions require completed bars; price crossings use sampled quotes and can miss a crossing between checks. Verify the selected broker market: chart prices and the bot's feed can differ.

Do not double-click `popup.html`: it cannot authenticate as an extension. Install the folder using the steps below, then use the extension toolbar icon. For normal website login, open the hosted SLK site and generate a **Browser** code instead of a **Chrome extension** code.

## Install for testing

1. Download `/extension/download` from your deployed SLK website and unzip it.
2. In desktop Chrome, open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select the directory containing `manifest.json`.
3. In the Telegram Mini App, open **Browsers**, choose **Chrome extension**, and generate a single-use code.
4. Click the extension icon and enter the code. The paired session appears in Telegram's browser list and can be revoked there.
5. Open a supported chart, hover over or click **SLK alerts**, confirm the detected market/provider, select a level, condition and timeframe, then create the alert. Use **Active alerts** in the dock to review or stop it, or **My alerts** in the Mini App.

The floating dock follows recognized TradingView and Deriv chart symbol controls as the chart changes. A manual market selection stays fixed until **Follow chart** is clicked. When automatic detection switches markets, the old price is cleared so you enter a price for the new chart. If the chart cannot be identified reliably, the market stays blank for manual selection. Drag the panel handle to reposition it. Chart hover prices drawn inside a canvas are not read; enter the intended level explicitly.

The extension only requests local extension storage and access to the SLK API. Content scripts run on TradingView `/chart/` pages and `charts.deriv.com`. Authentication tokens are kept in extension-only local storage, inaccessible to chart content scripts; no Telegram bot token or cron secret is used. Disconnect clears local credentials and attempts server revocation.

Regular desktop Chrome Web Store extensions are not available in standard Chrome on Android or iPhone. The same alert controls are available in the Telegram Mini App and paired website.

## Chrome Web Store submission

The package is ready for local installation, not published to the Chrome Web Store. Publication requires the owner's Chrome Web Store developer account, its registration requirements, a listing, screenshots, privacy-policy URL, support contact, permissions/data-use declarations, and Google's review. Upload a ZIP with `manifest.json` at its root. Explain that extension storage holds the user's revocable SLK session and that alert configurations are sent to the SLK backend for Telegram delivery. Do not claim affiliation with TradingView or Deriv.

For a different deployment, change `API` in `background.js`, the API `host_permissions` in `manifest.json`, and the website link in `popup.html` together before packaging. No remote JavaScript or inline popup scripts are used.

Confirmation choices are Breakout (including sweep-and-break), Engulfing (opposing open-close level invalidation), and 4th man. The optional lower-timeframe filter also uses open-close engulfing. Reload the unpacked extension after updating.

## Separate alert types (0.1.3)

Choose **Price** to watch a required level for crossing, candle close or rejection. Choose **Confirmation** for Breakout, Engulfing or 4th man, select any combination of models and up to six timeframes, then choose **Anywhere on this market** or **At a level**. Any selects all three models; it does not add unlisted models. Confirmation delivery can stop at the first event or continue for each new matching event until expiry. Optional lower-timeframe engulfing is a confirmation filter. Changing the selected/automatically followed market clears its old price and note.

The Mini App's Replay tab separately offers **Alert replay** from an owned historical event and **Price replay** from a chosen market and date in your settings timezone. Both support changing the chart timeframe without advancing its replay clock. Replay uses retained shared history and may report missing or queued data rather than downloading broker history on every chart click.

## Market and alert controls (0.1.4)

All, Regular, Deriv and Crypto filters use broker catalogue categories. Chart following switches the category when needed. A timestamped broker sample appears for the selected market; **Use price** explicitly copies it into your level. Quote previews refresh once a minute while the dock is open, share a bounded server cache, and defer if the personal scanner is busy. Missing or stale samples are shown as unavailable. Price crossings remain sampled, not continuous touch detection.

**Active alerts** shows this market by default; **All my markets** shows your other active watches. **Stop** cancels your watch; a delivery already in progress can report a retry message. Lists refresh after creation/cancellation and once a minute while open.

Version 0.1.5 automatically fills an untouched, empty price field with the selected market’s fresh broker quote when the dock opens or the market changes. Users can edit or clear it; refreshes and reopening preserve those edits. Switching markets resets the old level. Anywhere confirmation watches remain price-free. Use price remains available to explicitly replace a level.

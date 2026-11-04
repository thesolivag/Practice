# Bishop paper deployment

Repository: `awujo/practicing`. Branch: `claude-bishop-aggressive`. Render service definition: root `render.yaml`. The service is separate from Kevin's `slk-miniapp`; do not change Kevin's service or existing secret values.

## Separate application database and bot

Create a Bishop Aiven MySQL database/user and a Bishop Telegram bot. Set the following names in both GitHub repository secrets and the new Render service as applicable:

| Name | Where used |
|---|---|
| `BISHOP_DATABASE_URL` | Actions and Render; Bishop application database only |
| `BISHOP_DATABASE_PASSWORD` | Optional separate password override, Actions and Render |
| `BISHOP_DATABASE_CA` | Aiven CA PEM or CA-file path, Actions and Render |
| `BISHOP_TELEGRAM_BOT_TOKEN` | Render authentication and Actions delivery |
| `BISHOP_TELEGRAM_CHAT_ID` | Actions delivery destination |

The database tables use `bishop_` names. The hosted application refuses fallback to shared `DATABASE_URL` or `TELEGRAM_BOT_TOKEN`. Its database connection parameters do not mutate the collector's environment. Existing shared `DATABASE_*` and `CTRADER_*` secrets remain the read-only IC Markets source configuration; Kevin alone owns its refresh tokens.

Deploy the new Render service from the Bishop branch. Set the new HTTPS URL as the Bishop bot's Telegram Mini App/menu URL. `/healthz` is a lightweight application health endpoint; actual database/worker connectivity must be checked through a completed scan and the authenticated app. Do not paste credentials into chat or commit them.

## Current bias worker

`Bishop current IC Markets bias` (`bishop-live-bias.yml`) is manually dispatched on the Bishop branch. Initial operational coverage is GBPUSD and EURNZD. It reads closed H1 candles, keeps a 400-day raw cache and requests only a two-day overlapping delta thereafter. A repeated closed hour reuses its verified cache without broker authentication. Historical revisions, changed conventions or cache corruption stop the run for review. No data fallback is used.

Bias scans evaluate same-timeframe closed structural context. They skip reaction/confirmation story generation, entry detection and order execution. Monthly/weekly/daily/H4 observations retain scope and provisional-parent qualifications. They are not confirmed entry instructions. Their lean database snapshots have a 2 MB guard; raw candles remain in cache/artifacts. Once a closed hour is persisted, reruns reuse it rather than changing the historical decision. Different input for that same hour stops for review.

Without Bishop database secrets, the workflow produces artifacts only. With those secrets it persists to Bishop's database. Enable the GitHub repository **variable** `BISHOP_TELEGRAM_DELIVERY_ENABLED=true` only when the Bishop bot/chat are ready. First-run historical events are baselined without sending; current bias states can produce an initial notice. New changes are deduplicated. The workflow never sends broker orders.

Telegram confirmed sends are not resent. Explicit rate-limit rejections are deferred; network-ambiguous sends remain UNKNOWN and interrupted claims remain SENDING for review, rather than automatically duplicating a potentially delivered message.

## External cron

On Render configure:

- `BISHOP_CRON_SECRET`: a new Bishop-specific random secret.
- `BISHOP_GH_DISPATCH_TOKEN`: repository-scoped GitHub token with Actions write permission.
- `BISHOP_CRON_ENABLED=true`: turn on the authenticated endpoint when configuration is ready.

Configure the external cron service to POST to `https://<bishop-render-host>/cron/tick`, initially hourly at minute 5, with header `X-Bishop-Cron-Key: <BISHOP_CRON_SECRET>`. The endpoint always dispatches `bishop-live-bias.yml` at `claude-bishop-aggressive`; callers cannot select another repository, branch or workflow. A queued response means GitHub accepted dispatch, not that the subsequent scan succeeded. GitHub Actions scheduling on the default Kevin branch is not used.

## Validation boundary

All 40 teaching examples have source-review records. Twenty-seven contain explicit directional bias context. Fourteen with usable source creation clocks and matching saved IC Markets data agreed on same-timeframe structural direction in run40342942707; that is not setup-time or entry-replay acceptance. Remaining source labels, assessment clocks, CFD calendars and quote-currency mappings stay explicit gaps.

Paper entries and continuous position lifecycle are the next stage after current bias operation is checked. The existing offline paper engine/store supports that work, but this current-data workflow intentionally creates no entries or orders. No Render service, cron schedule, database credentials or Telegram configuration is created by committing these files.

### Historical gaps and current readiness

The weekend-only FX calendar leaves some historical closures unresolved. They remain missing observations and keep the full-window result `PARTIAL_UNVALIDATED`. Bias-only presentation can separately report `CURRENT_SEGMENT_ONLY` when all latest same-time break bars and their referenced turning-point bars are known and wholly after the last gap, with uninterrupted expected base coverage through the closed-bar horizon. Unknown references, old anchors, opposing simultaneous signals and trailing missing slots are not discarded to obtain a direction. This exception never authorizes paper entries or changes the full execution engine's missing-data rules.

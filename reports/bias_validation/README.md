# Bias-first validation

The first milestone is comparing Bishop's documented bias with the engine at the same time and on the same bias timeframe. Entry confirmation timeframes are separate. A BUY/SELL trade label is not a verified higher-timeframe bias annotation.

The source inventory in `source_readiness.json` is generated with `python -m reports.audit_teacher_bias_readiness`. It does not run detection, alter the frozen examples, or treat missing evidence as a mismatch.

For each source annotation, record direction, bias timeframe, actual assessment/setup UTC time, transcript timestamp and chart/frame reference, key level, reason for bias and invalidation. Where source time or chart geometry is unresolved, keep the annotation pending. Compare IC Markets candle structure with the source feed; exact printed price equality is not required.

Replay must use only data available at the assessment time. Show the engine's selected bias and its explanation, rather than finding any matching candidate among competing stories. Report direction agreement separately from agreement on timeframe, key-level structure and reasoning. Missing input, unclear source and genuine disagreement remain separate outcomes. Do not use future trade outcomes to choose bias.

The mini app should display source bias, engine bias, timeframe, assessment time, reason, invalidation and review status. Optional owner bias is stored separately and does not change engine detection. Paper entries follow bias review.

## Deployment isolation

Use the existing repository and Bishop branch, with a separate Render service, Telegram bot and Aiven MySQL database/user. Map repository secrets `BISHOP_DATABASE_URL`, `BISHOP_DATABASE_PASSWORD` and `BISHOP_DATABASE_CA` to Bishop runtime configuration. Use Bishop-specific Telegram secrets and workflow/concurrency names. Do not replace Kevin's existing secret values. Existing Bishop paper tables have the `bishop_` prefix.

Historical IC Markets collection currently borrows Kevin's database credentials to read cTrader tokens. That read-only data-source connection is distinct from Bishop's future writable application database. Keep those configurations separate; changing the application database must not silently move the token lookup. No hosted connection or Telegram notification has been activated by this readiness report.

## Built runtime and bias path

`render.yaml` now describes the separate Bishop service. Its factory requires `BISHOP_DATABASE_URL` and `BISHOP_TELEGRAM_BOT_TOKEN`; it never falls back to Kevin's application credentials. Database password and CA overrides are passed per connection, leaving the read-only collector's existing configuration untouched.

`python -m bishop.scan_bias --input <csv.gz> --manifest <manifest.json> --as-of <UTC> --out <directory>` skips entry detection. Optional `--history-start`, `--origin-tfs D H4` explicitly bound a diagnostic. `--persist` writes to the isolated Bishop application database. The mini app Bias tab reads current snapshots; terminated/suspended stories are excluded, opposing active stories remain a conflict, and incomplete input cannot publish a directional bias. This view is an implementation policy requiring source validation.

The Actions checks include two saved-data scans at the PDF creation times, using D/H4 origins and bounded history. These are snapshot diagnostics, not verified setup-time replays. No broker connection, new collection, database write or Telegram send occurs in these jobs.

Delivery is off by default. To configure new bias/event alerts, both the producer and sender need `BISHOP_TELEGRAM_DELIVERY_ENABLED=true`. The sender runs as `python -m bishop.telegram_delivery` with Bishop database credentials, `BISHOP_TELEGRAM_BOT_TOKEN` and `BISHOP_TELEGRAM_CHAT_ID`. Existing disabled previews are not sent retroactively. Confirmed sends are not resent; network-ambiguous sends remain UNKNOWN for review, and interrupted SENDING claims require review. This deliberately does not claim exactly-once network delivery. The new sender has not been activated.

Remaining external provisioning: the owner's separate Aiven database/user, Bishop Telegram bot, Render service and scheduled dispatcher. No new credentials have been supplied to this workspace; never paste tokens into chat. Enter them in Render/GitHub secret settings.

## Source review and timeframe correction

All 40 frozen examples now have separate source-review records: 38 PDF cases and two native-video cases. There are 27 explicit directional bias observations; 13 remain unresolved. This does not change the original frozen trade fixture or verify any setup-assessment clock. AUDUSD p25 explicitly has bullish Daily context despite a SELL plan; direction must come from the source context, not the trade side. EURGBP p8's printed standing-extreme wording conflicts with the owner's clarified buy definition and remains flagged, without changing the model to fit it.

A Daily breakout is a structural event on D. `Story.origin_tf=D` means a Daily reaction followed by H4 confirmation. Comparing those as equivalent was a presentation error. Current output separates `structural_context` on the actual timeframe from reaction/confirmation setup stories. The most recent observed closed structural break is a disclosed direction signal; it is not a fully confirmed parent-story reversal or entry authorization. ROOT ranges retain their DEFINED/PROVISIONAL status. Same-clock opposing break signals remain unresolved. Snapshot comparisons use the same structural timeframe as the source label.

The mini app can fetch original teaching charts through an authenticated image endpoint. It serves 33 rendered PDF pages and the two existing native frames; it does not expose secret files or rely on users opening HTML source artifacts.

Use the manual `bias_inventory=true` input on the Bishop application checks workflow for a one-time sweep of the reviewed source labels using saved data. Missing labels, missing clocks, absent inputs, unresolved context and directional differences stay separate. This sweep is not part of every normal push.

Independent review found and fixed MySQL read-snapshot staleness, idle reconnection, historical alert flooding and known Telegram rate-limit rejection handling. First-run historical events are retained without sending; subsequent events use an availability watermark. Explicit 429 responses defer retry; uncertain network sends do not automatically retry. Claims recheck deferred eligibility under the database lock.

Current snapshot inventory from run40342942707: 14 same-timeframe directional agreements, 13 missing source bias labels, eight missing usable input/calendar/mapping combinations and five missing usable snapshot clocks. No comparable directional disagreement was observed in that sweep; all actual teacher setup-clock acceptance remains unresolved. Results are in `snapshot_inventory.json` and shown in the authenticated review view.

The current-data worker is now implemented separately in `bishop-live-bias.yml`, with incremental verified raw caching, frozen-hour idempotency and optional isolated persistence/delivery. It analyzes structural context only; historical reaction/confirmation graph generation is skipped so full warmup graphs are not copied into the free database hourly. See `bishop/OPERATIONS.md` for configuration and limits. External hosting/schedules/credentials still require provisioning.

The first current-data run40391840762 successfully collected both 400-day FX windows without token refresh or trading. Compact bias outputs were12,649bytes (GBPUSD) and19,592bytes (EURNZD), rather than copying full historical story graphs. Both full windows correctly remained PARTIAL because51 historical weekday slots were absent around year-end; database persistence was not configured. Subsequent bias-only readiness now requires explicit proof that the observed break and reference are independent of those older gaps, while preserving the gaps and full-window PARTIAL status. This rule is never used to enable entry/order execution.

Final validation: run40396402296 on629086d passed410tests and skipped5, including three tests against an ephemeral real MySQL8service (fresh cross-connection reads, numeric retry deadlines and concurrent single-notification claiming). Optional media installation is now a manual workflow input; obsolete development checks are cancelled automatically. This avoids repeating slow media setup for routine bias/database changes.

Run40393856297 successfully reused both cached current-data snapshots and produced qualified current-segment observations while preserving51missing historical slots per pair. Compact results were14,427bytes/23,112bytes; database persistence and Telegram delivery remain unactivated. `current_results/` contains the archived evidence, and `release_status.json` records the validation boundaries. Browser previews render archived Actions data through a local authenticated TestClient; they are not a hosted deployment. The preview helper is `python -m reports.preview_bishop_app`.

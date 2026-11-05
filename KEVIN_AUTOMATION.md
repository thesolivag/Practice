# Kevin automation

## Status

- 2026-11-05: Diagnosed run41945533672: candle cache miss; 2018 completeness gate prevented save; 37-market preparation took ~182s before user run record. Live workflow now saves successful incremental stores immediately after live scan under isolated live-candles-v1 keys, restoring these first and legacy candles-v3 second. Full-history research cache policy unchanged; next run must seed cache before warm-run speed can be measured.
Hourly bias scanning uses cron-job.org -> Render /cron/tick -> live.yml, with cron expression `2 * * * *`. GitHub's schedule is removed. This workflow checks out claude-kevin-king. Manual dispatch remains available. Repository secrets are required separately from Render environment settings.

## Log

- 2026-11-05: Diagnosed run41945533672: candle cache miss; 2018 completeness gate prevented save; 37-market preparation took ~182s before user run record. Live workflow now saves successful incremental stores immediately after live scan under isolated live-candles-v1 keys, restoring these first and legacy candles-v3 second. Full-history research cache policy unchanged; next run must seed cache before warm-run speed can be measured.

- 2026-11-05: Removed live.yml GitHub :07 schedule on main and Kevin per user request. External cron-job.org should call Render /cron/tick at 2 * * * *. Manual workflow_dispatch retained. External timer settings and historical DB rows cannot be verified from this session. Render currently has only a ten-minute in-memory dispatch cooldown, not durable hourly deduplication. GitHub runner queue latency remains possible.

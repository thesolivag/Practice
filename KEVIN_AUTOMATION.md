# Kevin automation

## Status
Hourly bias scanning uses cron-job.org -> Render /cron/tick -> live.yml, with cron expression `2 * * * *`. GitHub's schedule is removed. This workflow checks out claude-kevin-king. Manual dispatch remains available. Repository secrets are required separately from Render environment settings.

## Log

- 2026-11-05: Removed live.yml GitHub :07 schedule on main and Kevin per user request. External cron-job.org should call Render /cron/tick at 2 * * * *. Manual workflow_dispatch retained. External timer settings and historical DB rows cannot be verified from this session. Render currently has only a ten-minute in-memory dispatch cooldown, not durable hourly deduplication. GitHub runner queue latency remains possible.

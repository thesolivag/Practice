# Kevin automation on main

## Status
The default branch registers live.yml for hourly scheduling and Render dispatch.
It explicitly checks out claude-kevin-king; main does not contain the application.
Repository Actions secrets are required separately from Render environment variables.
Personal one-minute checks remain on Render /cron/alerts.

## Log
2026-11-04: Registered existing Kevin live workflow on main, preserving its
concurrency group, limits and secret names. Missing required secrets fail visibly.
No Bishop files changed. Live scan success still requires runtime verification.

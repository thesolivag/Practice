# H1 A/V baseline with optional M5 confirmation

User stopped further OB/violation-block investigation. Implemented explicit h1_av_m5 entry policy: require closed H1 sweep and its confirmed H1 A/V body junction, plus a closed M5 protected-swing break in the intended direction. No OB or FVG dependency. This is the authorized simplified route, not an automatic choice among unvalidated M5 blocks. Existing direct h1_av remains the comparator.

Shared shift recognizer is unchanged: one-left/right pivot before sweep extreme, first closing break afterward. Intrahour shift is actionable no earlier than H1 close. H1 junction and shift must both be known; order is pending from that clock only. Broken data continuity, breached sweep extreme, already-taken map target and wrong-side limit are rejected. Existing execution replay begins on subsequent M1 bars, retaining unknown outcomes.

Reference NZDJPY gives entry 89.117 at 03:00 UTC after 02:55 UTC M5 break. Stop remains 89.215 (three-pip buffer beyond H1 high). No claim that buffer equals user's screenshot. M5 local stop unavailable on this route by design; compare hourly_sweep only.

75 targeted tests passed locally: reference entry, H1-close gating, no-shift rejection, future-candle filtering, single emission, buy mirror, missing M5; existing execution tests retained. Exact teacher fidelity and profitability are not implied by tests.

GitHub comparison workflow: 2026 YTD, fixed NZDJPY/EURUSD/GBPUSD, direct H1 vs H1+M5, serial pair jobs (avoid concurrent broker token refresh), six-hour maximum per job. Each route gets separate monthly results and 1R/2R/3R outcomes; unknown/unfilled not counted as wins. Existing daily-map/ITF POI and prime-session filters remain, including UTC prime 00–02. NZDJPY reference sweep at 02 UTC is outside that inherited prime window; the entry-module match does NOT prove full-engine qualification. UTC research calendar and gross results exclude spread/fees/slippage. Do not call them live income expectations.

Historical M1 preparation checkpoints completed months. Partial current month refreshed. Reports/artifacts and cache preserved on failure. No broker orders or production deployment.

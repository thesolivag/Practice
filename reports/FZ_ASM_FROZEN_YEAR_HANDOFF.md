# Frozen January–October 2026 study

Workflow fzasm-frozen-year.yml: ten serial pair jobs, each limited to 180 minutes, followed by aggregate coverage and metric report. Cache source is prior annual run 43163729089, exact per-pair cache key; missing cache fails visibly rather than launching an unexpected annual download. New broker requests are native D1 from November 2025 and December 2025 M1 warmup only. Warmup chunks checkpoint. Trading orders are never submitted.

Pairs: USDJPY, EURJPY, GBPJPY, AUDJPY, NZDJPY, CADJPY, CHFJPY, XAUUSD, EURUSD, GBPUSD. Signals January 1–October 31 inclusive; cutoff November 1 00:00 UTC. November used for development is excluded. Positions unresolved at cutoff stay UNKNOWN; no November outcomes leak in.

Frozen recognition/entry rules are inherited from lifecycle validation. Both daily-on and daily-off retain H4 directional POI agreement and prime-hour restriction. Lifecycle enabled, fixed-target entry eligibility. Four entry routes, exact/three-pip sweep stops, 1R/2R/3R/4R/frozen Asian extreme. FZ research target unavailable in these fixed-target arms. Stop/target alternatives are paired, not separate independent evidence.

Native D1 weekday gaps quarantine BOTH modes after a gap can be observed (26 hours without the next daily open), until three new completed native candles establish context. No gap filling or invented daily closes. Audit lists excluded periods; figures are for observed/eligible data only, not complete calendar coverage. M1 gaps retain conservative UNKNOWN accounting. Intraday calendar remains UTC research timing.

Risk/cost CSV: each pair/model/mode/stop/target/month plus ALL. Win rate, gross R, resolved-exit drawdown and longest resolved losing streak; unknown/unfilled/unavailable counts. Costs 0,0.5,1,2 instrument pips per resolved trade are sensitivity deductions, not real bid/ask fills or proven net returns. Drawdown excludes unrealized exposure and unknown outcomes; overlapping models must not be summed. Combined report marks absent jobs, rather than zero profit.

Tests: 115 passing before launch. Production defaults unchanged. Follow-up: inspect each pair completion marker/coverage, source calendar issues, monthly results, and sample winning/losing/rejected charts before proposing demo. No profitable configuration should be selected solely on this in-sample historical comparison; reserve subsequent forward data for validation.

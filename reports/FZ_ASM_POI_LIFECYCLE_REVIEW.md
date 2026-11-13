# H4 zone lifecycle investigation

The October-warmup NZDJPY reference selected a bullish OPEN_CLOSE zone 88.871–89.260 originating October 16. Available source M1 aggregated to complete H4 shows October 28 00:00–04:00 UTC closed at 88.688, below the zone bottom. That is a witnessed invalidation before the November 11 entry; not necessarily the first invalidation, since the locally inspected snapshot begins October 25.

Code findings:
- detect_open_close_levels never retires its zones.
- detect_breaker_blocks retires original OBs but not subsequently broken breakers.
- Open-close and breaker timestamps were stored at the source/breaking candle open, despite being known only at its close.
- Engine chooses the nearest midpoint among touched eligible zones before directional agreement checks. This can select an opposite-direction zone even when another candidate agrees.
- Open-close expansion qualification uses 1.5 times the whole supplied-window mean body size, not a fixed formation-time threshold. This remains a provisional, history-sensitive heuristic, not a validated teacher definition.

Correction tested as opt-in poi_lifecycle=True: assign completed-bar availability; retire zones on first subsequent closed candle strictly beyond far edge; wick-only crossings and equality do not retire. No automatic resurrection or polarity flip for open-close zones. Default engine, existing ranking and expansion threshold are preserved for controlled comparison. Existing OB-to-breaker conversion is retained.

Source limits: key-level transcript discusses breakers/reclaimers (1731.9–1758 seconds) and invalidation zones (1848.5–1866.1 seconds), but the exact generic retirement policy is a research interpretation, not chart-verified teacher fidelity. Do not claim this proves all key levels correctly modeled. Fixing missing lifecycle does not validate the expansion-zone definition.

114 targeted tests pass, including mirrored bullish/bearish breaks, equality/wick survival, no mutation of baseline objects, and the observed NZDJPY price. Workflow reuses the same frozen artifact, November 1–13 08:59 UTC period, October warmup and three pairs. Original versus lifecycle changes only availability/retirement; additional daily-on/off fixed-target arms identify interactions. NZDJPY report includes every candidate and its retirement evidence. No broker orders or new market data downloads. No profitability claim until results are inspected.

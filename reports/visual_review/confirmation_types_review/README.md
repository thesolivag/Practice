# Breakout and 4th-man stop comparisons

Requested definitions: BUY standing-extreme confirmation sweeps the prior low, closes within that prior candle's range, and leaves the prior high unswept. It is not an H4 timeframe name and is distinct from engulfing. Actual frozen OHLC is plotted; original video frames are unchanged.

## Standing-extreme: USDCAD

Source T3,1680seconds (28:00), H1: narration1676.8–1686.5 explicitly confirms previous low swept with high standing, V-shaped KL. There is no isolated H1 position box. He then uses additional M30 engulfing for final entry. At1710seconds (28:30), final box entry1.39681, stop1.39589. This must not be called a standalone fourth-man stop.

Current-code GitHub diagnostic40584728247, frozen H1 IC input: June12 previous14–15UTC candle H1.39845 L1.39673; sweep15–16UTC H1.39726 L1.39592 C1.39711. Thus prior low swept, close back within prior range, prior high intact at confirmation. Bot planned entry1.39680 and stop1.39587 (swept low minus5ticks). All38 qualified context variants agree on stop; targets differ1.39726 /1.40240. Execution guard holds this opportunity as AMBIGUOUS_EXECUTION_PLAN. **No order was placed for this opportunity.** The figure does not claim it was.

Bishop's final M30 stop and bot's H1 proposed stop differ0.2pip, but source/bot confirmation procedures differ. Exact broker trade identity and target fidelity are NOT established. Other searched source candidates did not establish a cleaner standalone placed fourth-man stop: PDFp8 has contradictory high-swept/low-standing BUY label; USOIL/EURAUD later actual entries use engulfing or no stop box; CADCHF standing entry missed and later box is hypothetical direct. None were silently relabeled.

## Breakout: GBPCAD

Source T3,420seconds (07:00), H2 breakout: entry1.86183, stop1.86041, target1.87039.

Current-code GitHub diagnostic40584565827: earliest *actually submitted* June9 H2 breakout order is05:00UTC, entry1.86271, stop1.85847,target1.87040. Selection is chronological, not outcome-based. It filled in zero-cost replay and later reached its diagnostic target. Earlier03:00 opportunity is now held by exposure cap; the older figure's expired03:00 order should not be mistaken for current execution.

The bot's stop still protects earlier liquidity-take low1.85852, not merely current03–05UTC confirmation candle low1.86159. Gap to source stop is19.4pips and remains unresolved; this figure exposes it, not certifies it as logical. Exact source-to-IC entry correspondence remains unverified. The prior engulfing-only scope fix did not change BO procedures.

## Provenance and reproduction

Both diagnostic inputs/outputs/code hashes are preserved under reports/implementation_review/primary_video_40584565827 and primary_video_40584728247. T3 source SHA256 ee73e7118df31d1f30524a204ffe5393bbfc05b87197f935fe01bd4687d45004. Source episodes in tests/bishop_video_breakdown_cases.json. Neither expected prices nor fixture tolerances fitted to output; no live orders or messages sent.

`PYTHONPATH=. python reports/visual_review/confirmation_types_review/render.py` renders charts only, not strategy runs. evidence.json records setups, selected/held status, source numbers and candle identities.

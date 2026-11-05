# Bishop teacher-example pilot — 2026-11-05

**The deployed configuration did not reproduce an eligible entry in any of the
three source-observed windows tested. Exact teacher agreement remains unscored.**
This is an observed reproduction gap, not proof of a 0% live accuracy rate.

The pilot used the deployed `bishop_confirmation` profile, H4/H3/H2/H1 entry
frames, 35-day context, seven-day eligibility, compact story diagnostics and
explicit zero costs. No strategy, broker connection, production setting or
notification was changed. Frozen source expectations were recorded before replay.

## Results

| Primary-source episode | Source narration | Same-side/timeframe plans in source window | Eligible selected orders | First observable issue |
|---|---|---:|---:|---|
| AUDCHF BUY, 9 June 2026 | H1 engulfing; explicit loss | 40 | 0 | All targets unresolved |
| NZDCHF BUY, 10 June 2026 | Journal-corrected H2 breakout/liquidity; immediate loss | 0 | 0 | No matching H2 BUY candidate; earlier context/entry chain needs alignment |
| USDJPY BUY, 10 June 2026 | H3 breakout/retest; discretionary exit around 2R | 342 | 0 | All targets unresolved |

Plans include repeated contexts and different model routes; these counts are
**not counts of distinct trades or accepted matches**. AUDCHF includes22
`confirmation_engulfed_oc`,8 `oc_break_retest`,4 `confirmation_sweep_bos`,4
`engulf_av_retest` and2 `confirmation_bo` plans. USDJPY includes294
`confirmation_bo` and48 `engulf_av_retest` plans. No closest-price winner was
selected and no numeric acceptance tolerance was fitted.

All three replays completed, in6.400s,3.290s and4.501s respectively. Each result
was `PARTIAL_UNVALIDATED`. H1 and H2 base aggregation was complete over the replay
window, while month/day/week/H4/H3 aggregation includes partial bins. There were
zero complete monthly bars in these35day windows. This cannot establish full
higher-timeframe context parity with the mentor.

## Independently checked blocker

For every AUDCHF and USDJPY candidate counted above, `target_ticks` is null and
`details.unresolved_reasons` contains:

- `qualified_first_external_objective_unresolved`
- `target_unresolved`

The earliest AUDCHF candidate's H4/H1 sponsor objectives lack explicit
sponsor-to-range scope/seed links. The earliest USDJPY candidate's H4 sponsor
lacks that link; its H3 direct-scope endpoint is rejected as already delivered,
with an endpoint/pool price mismatch and unknown/consumed context.

This agrees with the current `objectives.py` qualification logic and `risk.py`
withholding an entry without a qualified target. The observed gate is target
qualification, before order selection and fill simulation. It is not yet proven
whether the cause is insufficient context, an overly restrictive implementation,
source-feed alignment, or a combination. No candidate has been independently
identified as the mentor's exact setup.

## What the source independently establishes

A separate primary transcript/frame review confirmed AUDCHF BUY and a personally
narrated LOSS. The weekly/daily context is bullish; H4 breaks up with liquidity;
H1 engulfing is used. The teacher explicitly rejects adding an external-breakout
restriction to explain away this loss (video PTS636.6–647.5).

FOREXCOM H1 chart frames at PTS670/675 show reconstructed entry0.56205 and
stop0.56169. The target drawing changes0.56339→0.56378. The left tool anchor
9June07:00UTC+1 converts to06:00UTC, but is not proven order/fill time. These
are source observations, not a broker execution ledger. Both drawing states are
retained in the comparisons; neither is chosen to fit the replay.

Primary source: `claude-bishop-aggressive` snapshot
`6e1caa0417cedfa10b276867f3daec83a08b57f9`, canonical T3 transcript577.9–677.3s
and native frames in `reports/implementation_review/primary_missing_cases_source/`.
The source inventory/source observations in this directory retain exact paths,
video/frame hashes and limitations. Losses were not removed from the sample.

## Causal-prefix check

One additional AUDCHF snapshot stopped at9June23:00UTC, keeping the exact same
history start and eligibility start as the later snapshot. All1,754 earlier
setup records exactly matched the records published before that cutoff in the
later run, by canonical JSON hash. Orders and execution events were empty in
both. This check found no retrospective change for that prefix. It does not
establish teacher agreement or eliminate every possible look-ahead error.

## Honest completion measure

The inventory contains17 named source episodes, including missed/conditional/
passed examples;8 contain narrated personal participation, including one
multi-account episode. It is not an inventory of17 verified fills.

- Diagnostic replays completed: **3** selected episodes.
- Eligible-order reproduction in those broad windows: **0 of3**.
- Fully accepted teacher matches: **none awarded**.
- Exact teacher-acceptance percentage: **not calculable**; no independently
  aligned, exact-testable denominator is established yet.
- Remaining inventory readiness is recorded in `coverage.json`.

An outlook, a missed/no-retest example or a mentor's discretionary manual exit
must not be graded as a conventional completed TP/SL trade. Unmentioned engine
entries are not automatically false positives unless the source window has
been independently annotated with explicit rejection/no-entry evidence.

## What prevents exact acceptance

The mentor charts use FOREXCOM TradingView; replay data is IC Markets cTrader.
Exact source-to-IC candle identities, entry/fill clocks and numeric tolerances
are not independently established. Targets or management are uncertain in some
source examples. The35day live context is also limited. Therefore raw numeric
price differences in `*.public.json` are diagnostics, not acceptance scores.

The next validation task is to bind one source H4 liquidity/reaction and its
lower-timeframe confirmation to exact source/IC bars, then inspect the missing
objective lineage using only information available before entry. A source-grounded
correction should follow that evidence. Adding a fixed-R target or loosening a
gate merely to produce an order would not establish teacher agreement.

## Reproduction and evidence

From this validation branch, with a local checkout of the Bishop source snapshot:

```sh
python scripts/validate_bishop_teacher.py --source-root /path/to/bishop-source --seconds 30
python scripts/validate_bishop_teacher.py --source-root /path/to/bishop-source --seconds 30 --prefix-only
```

Frozen CSV/manifests are in the source snapshot under
`data/primary_missing_inputs/{AUDCHF,NZDCHF,USDJPY}/`. Each replay verifies the
CSV hash and records engine/module hashes and clocks in its plan. No broker or
production credentials are required. Published `*.public.json` retains every
candidate's ID, clock, geometry, raw differences to every source drawing and
objective qualification diagnostics. Raw compressed engine outputs remain local;
`raw_artifact_manifest.json` records their hashes/sizes, and they can be regenerated
with the script. They are not claimed as GitHub-hosted raw artifacts.

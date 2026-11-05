# Owner clarification and primary-source target recheck — 2026-11-05

Owner clarification: the initial trade target may be nearer liquidity in a
smaller range, or a relevant key level before the larger external objective.
The broader objective may remain part of the story; later management toward it
must not be confused with the initial target. This clarification guides further
validation and does not authorize fitting a target to a later outcome.

## Source-backed distinctions

| Concept | Required distinction | Primary evidence |
|---|---|---|
| Local versus larger ERL | A level can be internal to a larger range and external to a qualified smaller range. An arbitrary internal wick is not automatically a target. | Bishop bias-entries319.4–337.6: personal nearest-external-liquidity preference; trades3 389.1–456.7: nearby H1 ERL alternative |
| Trade TP versus story destination | A nearer trade exit does not delete or replace the farther storyline objective. | Storyline1 1548.4–1600.2 |
| Context KL before ERL | An H4 KL/OC can be the first exit for an H1-triggered entry. The cited lesson explicitly excludes using the newly created H1 entry KL as that exit. | Storyline1 1098.8–1155.3 |
| Target timeframe | The target can be chosen before descending to the final entry timeframe. No universal H1-only or H4-only target rule follows. | Repeating-system594.1–649.9; distinct nearby-H1 route in trades3 |
| Later management | New evidence can support a later continuation or management decision. A future far target must not be backfilled as the original plan. Automatic partial exits/extension are not established by this audit. | Storyline1 1548.4–1600.2 and separate target-plan/management contract |
| Counter-structure obstacle | Nearer identified liquidity/KL can limit a retracement trade before the larger range objective. It is not a universal ban on counterweekly trades. | Building-bias2 815.7–928.7 |

Primary paths under Bishop snapshot6e1caa0:
`knowledge-base/videos/bishop-bias-entries/transcript.txt`,
`bishop-repeating-system/transcript.txt`, `bishop-trades-breakdown-3/transcript.txt`,
`video-16-storyline-1/transcript.txt`, `bishop-building-bias-2/transcript.txt`.
Independent reviewer rechecked the primary passages; root separately read the
nearest-ERL, pre-entry target and H4-KL passages. Existing source audit:
`knowledge-base/study/TARGET_SELECTION_AUDIT.md`.

## What the current code actually does

`nearest_erl` is not a single-global-ERL policy. `objectives.resolve_objectives`
examines the actual setup sponsors' direct/seed-linked ranges and explicit
ancestors, validates their endpoints and optionally linked opposing KLs, then
`risk.plan` chooses the nearest qualified objective ahead of entry. Overall
story destination is retained separately.

The pilot exposes missing/failed qualification, not proof that every trade was
being forced toward the largest range. Missing sponsor scope/seed links and
endpoint integrity failures prevent target publication. Additionally,
`structure.py` does not publish the `target_level_id`/`opposing_level_id` links
required for the generic linked-KL path. That intermediate-KL support is partial.
The separate `context_h4_kl` route exists but is not selected by the deployed
`nearest_erl` policy; it must not be silently substituted for every source route.

## Acceptance requirements for the next correction

1. Keep initial trade objective and farther story destination in separate fields.
2. Identify the selected target's timeframe, range/context, source route,
   formation/publication clock, price and unconsumed/current role at entry.
3. Allow a source-supported nearer local ERL or contextual KL; do not require
   the largest objective and do not equate the entry TF with the target TF.
4. Produce missing causal associations from actual structure/reaction evidence;
   do not fabricate range links, select an unrelated nearest wick/KL or add a
   fixed-R target merely to force a signal.
5. If management later changes the objective, preserve the original plan and
   record the later evidence and amendment time separately.
6. Re-run the frozen pilot against the unchanged source expectations. Preserve
   the narrated losses, unsupported cases and unresolved feed alignment.

No live policy, price, stop, target, user setting or broker execution was changed
by this clarification audit.

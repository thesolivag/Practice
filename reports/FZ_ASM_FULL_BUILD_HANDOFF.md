# Full-context ASM research build — 2026-11-14

Read FZ_ASM_FULL_RESEARCH_SPEC.md first. This is a completed executable research interpretation with explicit assumptions, NOT proof that every discretionary rule in the FZ materials has been replicated.

## Components
- fzasm/full_context.py: causal level lifecycle, five daily map families, body-based structural break, existing-price destinations and conflict abstention.
- fzasm/full_model.py: opt-in engine; concurrent sweep contexts, H1/H2 sweeps, M5/M10/M15 routes, H1 alternatives, three-pip sweep stop and recorded decisions.
- fzasm/full_replay.py: independent1R/2R/3R/4R, Asian and structural targets; structural full exit without invented partial-management rules; monthly and per-trade records.
- scripts/run_asm_full_research.py: bounded CLI, native-D1 audit, existing prices only.
- .github/workflows/fzasm-full-research.yml: manual-only sample, maximum31 days; archive/cache dependency; no annual run triggered.
- Common engine/execution repairs from the previous turn are included. Optional junction_tolerance preserves older route defaults while full research requires adjacent close/open alignment for FVG overlap.

## Verified
141 tests passed locally, including19 new full-model tests and5 audit regressions. The restored direct-H1 NZDJPY context regression now uses a small committed fixture, so it does not silently skip when the workspace archive is absent.

Single reference-clock inspection of NZDJPY,2026-11-11 03:00UTC, found aligned bearish structural and candle-range daily maps. Selected FVG-overlap pending sell89.120, stop89.215, structural destination87.908. Stop risk9.5pips; target distance121.2pips; planned12.76R, NOT a realized result. The nearer candle-range destination won over structural87.539. No future candles or outcome were used. Full plan and source-derived context are saved in FZ_ASM_FULL_REFERENCE_CHECK.json.

The reference inspection uses a short intraday archive. It is not a continuous-history full backtest, not teacher-equivalence certification, and does not establish whether an earlier same-session setup would have taken priority. A complete monthly replay must still test the frozen rules.

## Next
Review the actual reference chart (generated locally at evidence/repair-review/NZDJPY-full-context.png) and the JSON decisions. Do not optimize against its outcome. Run a short, preselected GitHub sample only after reviewing the assumption table. The default workflow window isMay1–8,2026; it is already-known historical data, not an untouched profitability holdout. Future profitability evaluation requires separate unseen data and paper testing.

No new performance backtest or deployment was run during this build. Do not quote the existing annual results as results of this new model. Manual workflows may require registration on the repository default branch before GitHub exposes dispatch; do not change the shared default branch for this.

# H4 liquidity implementation review

Scope: explicit breakout/liquidity/key-level lineage and historical causality.
This is an implementation audit, not teacher-example replay acceptance.

Source contract:
- Entries Part 5, 156.9–221.2: direct H4 breakout, known liquidity,
  relevant KL, anticipatory limit. The later sweep is not a submission gate.
- Full session study items 13–20: distinguish direct H4, closed-H4-breakout
  to H2 direct, and H4 liquidity take/reaction to lower-TF confirmation.
- Single-candle, series and structural liquidity remain separate supported
  forms. The next candle is not a universal requirement.

Independent review found:
1. Direct entries ignored a pool's explicit breakout/KL lineage. A pool could
   sponsor the wrong breakout or a nearest KL other than its declared KL.
2. Reaction entries checked `parent_break_id` but ignored `breakout_id` used
   by ordinary single-candle/series pools.
3. Direct historical pool selection used the final input segment, so appending
   a future gap could erase earlier setups.

Corrections preserve declared lineage (including rejecting contradictory parent
identifiers), select a linked KL only when causally available and usable, and
query direct pools from the originating breakout segment. Unlinked liquidity
retains existing selection conventions; these changes do not establish that
those conventions reproduce every mentor example.

Still requires separate review: full story/bias selection, numerical geometry,
logical stop selection, alternative-to-execution selection, and historical
teacher replay including missed trades and losses. Prior profitable headline
results are not acceptance evidence, particularly when correlated alternatives
were executed simultaneously.

Follow-up independent audit found delayed direct orders could also reuse a
retired breakout episode or liquidity already taken before submission.
Placement now checks known level retirement/role loss (including subsequent
restoration), same-scope range loss and fresh same-direction breakout. H2 direct
checks both its own episode and its H4 parent episode. Already-observed liquidity
takes block new anticipatory orders. Future events do not veto earlier placement;
no blanket opposite-break rule or numerical geometry rule is introduced.

First linkage commit `6c09310` passed GitHub Actions run `40515173379`:
420 passed, 5 skipped, including MySQL checks. Subsequent episode changes need
another run; these regression results do not establish historical mentor fidelity.

Final episode commit `f839979` passed GitHub Actions run `40515602201`:
426 passed, 5 skipped, including MySQL integration. Independent reviewer added
and ran 16 focused checks across the lineage/episode and existing entry-review
files, with no blocker found in this scoped change. Full mentor replay remains
separate and unresolved.

# Submission-time weekly context

Targeted trace40523456143 identified p47's same H2 entry receiving conflicting
nearer-target guards because its sponsoring stories were born before and after
positive Weekly confirmations. `initial_weekly_relation` was being used as the
current relationship even weeks later. A new entry must use evidence available
at submission, including closed confirmations published at exactly that clock.

The correction adds an explicitly named implementation convention:
`latest_confirmed_weekly_ROOT_batch_v1_OUR_CHOICE`. Among published Weekly ROOT
stories for the instrument, inspect the latest availability batch together.
Same-side confirmations retain every reference ID. Opposing simultaneous
confirmations remain CONFLICTED, with unresolved entry risk; IDs cannot choose
direction. Known invalidation/suspension/retirement of the latest batch yields
UNKNOWN without reviving an older batch. Destination touch alone is not a
positive opposite directional confirmation. CHILD stories do not silently
become the ROOT directional reference. The exact ROOT ranking is an operating
convention, not proof of mentor scope selection.

Each setup records `entry_weekly_relation` and full context provenance. Original
story side, `initial_weekly_relation`, parent_id and history remain unchanged.
This corrects the context used at submission; it does not rewrite the existing
strictly-earlier initial-parent decoration. Positive current ALIGNED evidence
removes a stale counterweekly guard/block for the new submission; current
COUNTER_WEEKLY applies the guard. Counterweekly entries remain allowed unless
the explicit owner policy disables them. Independent `retracement=True` guards
remain active. UNKNOWN retains the original conservative guard rather than
asserting a new direction. Risk memo identity includes current relationship,
all Weekly reference IDs and context policy, preserving proof/scope isolation.
The run identity also records the changed semantics.

Source contract: full_session_study8–11, WN455–480, DR394–421 and T3261–307
allow Daily/H4 counterweekly near-target entries. build_story_contract's Weekly
context section requires fresh context evidence and reassessment without
rewriting historical labels or imposing a universal Weekly veto.

Independent reviewer implemented the context helper/tests and reviewed the
entry/risk/engine integration; the primary agent reviewed the helper.39 focused
checks passed, covering same-clock availability, future invariance, conflicts,
retirement, separate retracement guards, original-history immutability, risk
memo regression, direct-entry lineage and owner policy blocks. Full regression
and focused p22/p47 historical traces will run on GitHub Actions. Neither the
helper nor those tests certify a match to the teacher's drawn p47 trade.

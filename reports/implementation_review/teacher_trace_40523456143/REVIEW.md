# Targeted mismatch trace

GitHub run40523456143 succeeded at53b4719. Regression run40523456088 passed
437 tests,5 skipped. This trace changes diagnostics and the observation ceiling;
it does not change Bishop's trading rules or promote source fixtures.

Silver p22 LEFT Saxo source header was inspected again directly: Jul13 2026
06:24UTC+1. The detector now stops at05:24UTC, retaining the distinction between
source observation and order/fill time. It emits17 setups across supported
frames,5 hypothetical orders, and7 same-side H2 candidates, all breakout-family.
There is **no H2 engulfing CE** by the source observation ceiling. The later
engulfing in the previous date-end replay cannot be substituted. The teacher
example remains missed; feed/anchor, reaction linkage and engulfing recognition
need separate causal inspection. Source fixture expectation is unchanged.

GBPCAD p47 reproduces2043 setups,477 eligible rejections,0orders. Saved story
contexts show why the target differs at May20 09:00UTC:

- Daily BUY story9cf514..., availableMay8 21:00, holds initialCOUNTER_WEEKLY
  against Weekly SELL e4495d..., availableMay4 21:00. Target1.84301.
- H4 BUY story3c4927..., availableMay8 09:00, likewise initialCOUNTER_WEEKLY
  against the same WeeklySELL. Target1.84301.
- Weekly BUY storyb8d93e..., availableMay1 21:00, has initialUNKNOWN and is
  unguarded. Target1.84773.
- H4 BUY story41ec4a..., availableMay18 06:00, initialALIGNED to Weekly BUY
  102c406..., availableMay8 21:00. Target1.84773.

The risk planner consumes frozen initial weekly relationship. Story decoration
also uses strictly-earlier Weekly publication, so a Daily story cannot see a
Weekly confirmation published at its exact clock. This identifies timing and
context inconsistencies; it does not establish which overlapping source scope
must dominate. A correction must preserve initial-history labels, evaluate
same-clock information as a batch, and resolve active/scope evidence without
choosing an arbitrary ID, the teacher's drawn target or later profitability.
Until that is established, the ambiguity guard remains in force.

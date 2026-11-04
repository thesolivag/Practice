Source-to-engine mapping review

Actions run 40166008273 succeeded, including all 354 regression tests and the frozen-input mapping assertions. No new detector run or threshold fitting was performed. The mapping exports closed candles, level availability, role history, known parent sell breaks and liquidity objects. Source object identities remain unverified.

EURNZD: distinguish the H4 V at 1.96382 (formed July 15 01:00 UTC) from the H4 A at 1.96339 (formed July 16 01:00 UTC). July 17 09:00 H3 high 1.96372 misses the former by one pip, but contacts the latter while its role is SELL and closes below it. Therefore the earlier hypothesis that no nearby H4 level was contacted is insufficient. The latest known sell parent at this contact is the July 17 01:00 H4 breakout.

The preceding H3 candle (06:00) has open 1.96040 and close 1.96255. The 09:00 H3 candle opens 1.96253 and closes 1.96005. Its close crosses the preceding open, but its open is two ticks below the preceding close. The engine's strict full-body engulf predicate rejects this pair. This is a precise geometry discrepancy, not proof that relaxing the predicate is Bishop's intended rule or that this IC candle pair is the source drawing. No two-tick tolerance has been introduced.

GBPUSD: H4 A 1.32026 is known June 24 01:00 UTC. H1 candles at 02:00 and 06:00 contact it while it has SELL role and close below it. H4 V 1.32057 is also contacted at 06:00 with SELL role. Thus no-contact and no-bearish-context explanations are inadequate. The latest known same-direction H4 structural parent for these observations is the June 23 05:00 SELL BOS. Whether that BOS, its inducement and these levels correspond to the teacher's labelled H4rH4 chain is not yet verified.

Remaining code/source audit: exact H4 pool first-take lineage; reaction and confirmation closing on the same candle; full-body engulf versus directional close across the preceding open. Existing confirmation pairing currently requires a reaction to end by the candidate's start, so a same-candle reaction/confirmation is excluded. Source contract says completing confirmation closes at or after reaction end. This boundary deserves a source-backed regression before changing execution.

No example promoted to PASS. No strategy behavior changed by this mapping.

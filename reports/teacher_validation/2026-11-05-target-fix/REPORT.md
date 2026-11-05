# Bishop target correction — bounded validation

The corrected policy qualifies setup-local external range liquidity or a source-supported H4 exit key level. The larger storyline objective remains separate. It does not pick arbitrary internal wicks or add fixed-R fallbacks.

Two concrete defects were corrected: comparing close-line range prices with wick liquidity prices, and missing explicit continuation ownership. H4 first-exit key levels have an independent source-supported route (video-16-storyline-1, 1098.8–1155.3). Ambiguous ownership stays unresolved.

## Frozen teacher pilot

The same three cases and data from the prior pilot were reused without fitting prices, outcomes, risk caps or source windows.

| Case | Source-window candidates | Selected orders before | Selected orders after | Teacher match |
|---|---:|---:|---:|---|
| AUDCHF H1 buy | 40 | 0 | 0 | Not established |
| NZDCHF H2 buy | 0 | 0 | 0 | Not established |
| USDJPY H3 buy | 342 | 0 | 2 | Not established |

AUDCHF target qualification improves from 0 to 40 eligible candidates, but exposure/selection constraints still prevent a matching order. USDJPY has 150 eligible and 192 unresolved target candidates; the two selected orders are CENSORED, not wins or losses. NZDCHF still has no matching H2 candidate in the source window. Source charts use FOREXCOM while replay uses IC Markets; exact teacher candle/fill anchors remain unverified. No teacher-acceptance rate can be calculated.

A fixed-history causal prefix comparison found identical 1,754 setups, 17 orders and 51 execution events before the cutoff when later candles were appended. This is one bounded check, not proof of every possible causal property. Machine evidence is in summary.json, prefix_check.json and the frozen source_cases.json.

Reproduction uses scripts/validate_bishop_teacher.py from branch validation/bishop-teacher-pilot-2026-11-05, with the corrected engine and the original Bishop source/data checkout. Raw engine artifacts remain local.

## Rollout

New detections activate from the first revised scan; no old corrected plans are backfilled into alerts. Existing frozen paper orders retain their geometry. The web app and entry messages distinguish the trade target/context from the larger story objective. All entries remain paper-only. Full teacher-example validation remains incomplete.

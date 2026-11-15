# ASM candidate review — frozen historical results

Source: GitHub run43685082614; original entry ledger43574624074. This is analysis of recorded outcomes, not another replay or raw-tick verification. Validation is July6–October31,2026; July is partial. Cost assumption0.08R per resolved filled trade. Results are independent research scenarios, not portfolio returns.

| Candidate | July netR | August | September | October | Total | Resolved / unfilled / unknown |
|---|---:|---:|---:|---:|---:|---|
| GBPUSD, H1 A/V after M5 shift, aligned map,1R | -1.40 | +5.80 | -2.16 | +4.28 | +6.52 |31 /14 /0|
| NZDJPY, direct H1 A/V, aligned H4/H2 touch,3R | -1.40 | +2.60 | +4.44 | +2.28 | +7.92 |26 /11 /0|
| AUDJPY, OB retracement, aligned map,Asian extreme | +10.53 | +3.12 | +18.06 | -4.66 | +27.07 |22 /9 /0|

## Concentration and costs
GBPUSD: excluding best3 trades leaves+3.76R. Largest drawdown of resolved outcomes3.24R. With assumed cost raised to0.16R/trade, result+4.04R; at0.25R,+1.25R.
NZDJPY: excluding best3 leaves-0.84R; largest resolved-outcome drawdown3.24R. Costs0.16R:+5.84R;0.25R:+3.50R.
AUDJPY: best trade net+13.39R; excluding it leaves+13.68R; excluding best3 leaves+4.19R. Largest resolved-outcome drawdown4.66R. Costs0.16R:+25.31R;0.25R:+23.33R. These cost deductions are sensitivities, not a historical spread simulation.

AUDJPY best case: September4 05:00UTC decision, sell112.754, stop112.822, frozen Asian target111.838. Risk0.068=6.8pips, target distance0.916=91.6pips, gross13.47R. Recorded fill05:05; exit12:52. Arithmetic and recorded chronology reconcile; raw M1/tick path has NOT been independently revalidated here.

## Comparison without the feature
Discovery / validation mean netR per resolved trade, feature present versus absent:
GBPUSD:+0.045/-0.347 in discovery; +0.210/-0.003 in validation.
NZDJPY:+0.120/+0.063; +0.305/-0.191.
AUDJPY:+0.051/-0.297; +1.230/-0.079.
All three features improved observed averages in both periods, but sample size, multiple comparisons and previously examined history prevent a robust edge claim.

## Per-record checks
289 selected signals across discovery, embargo and validation passed stored-evidence checks: map knowledge before decision; matched sweep and pre-sweep levels for the touch candidate; three-pip stop arithmetic; fixed target arithmetic; fill not before decision; exit not before fill. No outcome was recalculated. There are no unknown outcomes in these three validation groups. Unfilled orders are retained, not counted as losses or wins.

Map conflict occurs in15/45 GBPUSD validation signals,12/37 NZDJPY,11/31 AUDJPY. Aligned-map presence does not mean unanimous direction. Do NOT add a conflict veto while quoting these results. H4/H2 touch does not require a daily map. Level/range detectors remain research interpretations.

## Recommendation
Freeze GBPUSD/1R/aligned-map/M5-confirmed H1 route as the PRIMARY candidate for prospective paper validation: larger resolved sample, fixed payout and less dependence on exceptional winners. AUDJPY remains a secondary research candidate requiring direct candle/execution checks of its largest winners; NZDJPY is a comparison candidate. This selection is itself based on observed validation outcomes, so a new prospective sample is required.

No live orders, notification changes or automated paper deployment were made. Candidate specification is saved beside this report; it records the historical definition and the need to reconcile the legacy engine with any future paper implementation. Do not silently substitute the full-context engine or add new filters.

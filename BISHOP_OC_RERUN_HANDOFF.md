# Corrected engulfing / H1-H2 rerun —2026-11-14

## Owner specification
- Three consecutive completed candles: first two opposing the intended trade, third in trade direction closes STRICTLY beyond the immediate open-close reference.
- Owner explicitly confirmed: third close need NOT clear candle1 open. It clears candle1-close/candle2-open junction.
- Entry is candle1 close, not the V/A vertex. Quote difference from candle2 open is recorded. This follows existing slk.user_alerts.oc_boundary reference policy; exact-match remains an explicit detector option. No gap tolerance was optimized.
- Only H1/H2 entries. H3/H4 are excluded as entry timeframes; H4 context remains.1R/2R/3R are still target variants, not timeframes.
- Keep an existing pending/open opportunity; do not replace it with another confirmation. One reservation per pair per strategy family. Earliest clock wins; simultaneous ties use H1 before H2 then existing deterministic IDs. Conflicting geometries retain the existing ambiguity rejection.
- Reserve a family until ALL its target variants are flat. KK-nearby and its paired RR rows share this conservative reservation; recognitionRR is a separate family. Thus target variants share entry cohorts instead of admitting different future trades depending on early exits.

## Findings
The mini-app Trade review archive is the original run42371042901, amended using42499187752 and42516446781. The OC audit42781498988 did NOT correct trading logic or rerun outcomes. Alerts already had the owner OC definition; the legacy Bishop engine still admitted generic OC crosses and two-candle A/V alternatives.

## Implementation
Research-only branch. New slk.bishop_oc_replay and slk.bishop_oc_jobs; optional engine/detector parameters leave default live behavior unchanged. Corrected route emits only confirmation_engulfed_oc from the precise three-bar pattern, with entry reference, first close, second open, quote gap, three protection candles and H4 parent ID. Generic crossed-old-OC and A/V engulf routes are disabled ONLY in this research mode. Breakout/4th-man logic, bias construction and target/risk policies remain inherited.

Risk is replanned at the corrected entry with the current confirmation-pattern evidence; no old trade geometry or outcome is transplanted onto the new entry.1R/2R/3R share each admitted study setup.

Unknowns remain unknown. Saved M1 evidence is hash-checked and used only when matching its original H1 OHLC; new trades without M1 data remain explicitly ambiguous. The existing causal occupancy proof may release unknown exposure only after all possible pending/filled paths are provably flat. No expiry-alone outcome inference.

H1-engulf/H2-fourth-man correspondence is measured by same decision clock, side and exact entry price. It is not assumed universal or equivalent in stop/context. Matched IDs are exported; the occupancy rule prevents overlapping orders even when levels differ.

## Run scope
Same frozen inputs and cutoff as the old comparison:2026-01-01 through2026-11-07 11:00UTC.30 original selected feeds;26 eligible matched comparison markets, other markets remain separate. No broker/DB credentials, new data acquisition, live orders or Telegram messages.

GitHub workflow bishop-oc-rerun.yml has prepare, a fresh physical-prefix/poisoned-future/runtime pilot, monthly checkpoint jobs, and final collection.330-minute per-month job cap; no single24-hour job. Pilot also checks a known EURUSD mini-app confirmation at2026-02-18 10:00UTC before enabling full replay. A failed source/reference check blocks the annual chain.

## Output and mini-app status
corrected-oc-report contains REPORT.md/JSON, monthly/session/cost reports, and review-bundle/ with the NEW outcome archive, entry evidence and cross-TF matches. Missing jobs are labelled partial and excluded. Review bundle is ready for a separately labelled import after completion; it does not automatically overwrite the deployed mini app. Old results and review flags are preserved. No new profitability result exists at launch.

Existing mini-app reports must not be reassigned to new order IDs. Any eventual UI import must keep the old dataset accessible and label the new run/version.

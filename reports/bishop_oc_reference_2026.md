# OC versus A/V reference audit

Recorded A/V decisions only, original capacity-limited cohort. Not a complete search for ungenerated setups or a new profit backtest.
Eligibility reconstructed on physical decision prefixes. Exact immediate two-candle OC junction, not any older crossed OC level.
Subsequent price touches use H1 BID within original cancellation/expiry (maximum 24 hours). Missing data remains unresolved. A touch is not a fill or a win.
An engine-eligible alternative is not proof that all portfolio/recognition admission gates would admit a second order.
Market artifacts: 26; incomplete: 0.

| Strategy | A/V orders audited | Engine-eligible immediate OC | OC-only touch | OC-only with no recorded OC order |
|---|---:|---:|---:|---:|
| kk_aligned | 89 | 6 | 0 | 0 |
| kk_aligned_1R | 89 | 6 | 0 | 0 |
| recognition_1R | 194 | 20 | 1 | 1 |
| standalone | 115 | 9 | 0 | 0 |

## OC junction gap exclusions

These references fail the current exact-junction rule. Their touches are diagnostic, not eligible trades.

- kk_aligned: excluded gap sizes (ticks): {'1': 5, '3': 2, '-1': 12, '-2': 4, '2': 5, '-3': 6, '-6': 1, '-7': 2, '14': 1, '-5': 2, '-8': 1, '4': 4, '6': 1, '-4': 1}; OC-only touches among these: 5
- kk_aligned_1R: excluded gap sizes (ticks): {'1': 5, '3': 2, '-1': 12, '-2': 4, '2': 5, '-3': 6, '-6': 1, '-7': 2, '14': 1, '-5': 2, '-8': 1, '4': 4, '6': 1, '-4': 1}; OC-only touches among these: 5
- recognition_1R: excluded gap sizes (ticks): {'-2': 9, '1': 26, '2': 14, '-5': 5, '9': 1, '3': 9, '-1': 19, '-8': 2, '5': 4, '6': 3, '-31': 1, '-65': 1, '-3': 7, '-7': 1, '4': 5, '-6': 2, '-67': 1, '10': 1, '-11': 1, '-9': 1, '-13': 1, '8': 1, '-73': 2}; OC-only touches among these: 13
- standalone: excluded gap sizes (ticks): {'2': 7, '3': 6, '-2': 6, '7': 1, '-3': 6, '-1': 13, '1': 14, '9': 1, '-4': 2, '-12': 1, '13': 1, '4': 1, '-5': 1, '-86': 1}; OC-only touches among these: 8

Detailed unresolved reasons and every examined order are in REPORT.json. Do not add these counts to the original P&L.

Source: https://github.com/thesolivag/Practice/actions/runs/42781498988

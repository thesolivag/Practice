# Seven-day paper pilot: 19–26 October 2026

Verified-code GitHub run: https://github.com/awujo/practicing/actions/runs/40485910721

Code: `de62885`. Regression run: 416 passed, 5 skipped. Saved IC Markets H1 candles, 35-day pre-window warmup; H1/H2/H3/H4 entry support only. The separate 28-day bias replay completed 122 checkpoints per pair and passed its future-price invariance probe. No claim of live Bishop agreement.

| Pair | Stop policy | Settled W/L | Zero-cost settled R | Illustrative cost-stress settled R | Unresolved | Trigger groups |
| --- | --- | --- | --- | --- | --- | --- |
| EURNZD | context_liquidity | 28/1 | +9.47 | +9.32 | 3 | 7 |
| EURNZD | owner_fixed11 | 6/4 | +28.01 | +28.55 | 8 | 35 |
| GBPUSD | context_liquidity | 2/8 | +8.43 | -8.27 | 8 | 12 |
| GBPUSD | owner_fixed11 | 12/6 | +31.54 | +15.15 | 9 | 38 |

These are separate pair books, not a combined portfolio return. Open, cancelled and expired orders are separate from settled returns. Cost stress assumes 1-pip spread, 0.1-pip entry slippage, 0.2-pip stop slippage and 0.5-pip commission; these are hypotheses, not measured IC Markets execution costs. The orders are frozen from baseline selection rather than reselecting a portfolio under costs. A changed fill can therefore remove a losing trade as well as a winner.

The positive figures are not acceptance evidence. Structural-stop EURNZD's 28 wins come from three same-price/time trigger groups, with eight to ten stop variants per trigger. GBPUSD structural stops produce seven losses within one such trigger group. Those are correlated alternatives, not separate teaching examples. The owner selector currently distinguishes geometry and level identities; the source must settle which protection episode should supply the canonical trade before these variants can represent a faithful one-idea execution policy.

GBPUSD structural-stop settled returns reverse from positive to negative under the cost hypothesis. H1 candles leave several fill/stop/target sequences unresolved; these are censored rather than assigned favorable outcomes. All four engine runs remain `PARTIAL_UNVALIDATED`; monthly context and lower entry timeframes are not validated by this bounded input.

The bias replay also exposes local/parent differences: GBPUSD's daily latest-break direction switched BUY while the tracked daily parent range stayed SELL. A local structural break is not evidence of a confirmed parent reversal. Neither subsequent market movement nor an ordinary simulated stop identifies a mentor mistake.

Per-order losses, simultaneous trigger variants, coverage and original compressed reports are saved beside this file. The full 28-day paper run was started separately: https://github.com/awujo/practicing/actions/runs/40486205631 . Its results are not included here.

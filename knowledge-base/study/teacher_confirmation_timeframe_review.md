Confirmation patterns across timeframes

Source review confirms the distinction raised by the owner: a lower-timeframe engulf and a higher-timeframe sweep/standing-extreme pattern can describe the same directional market idea, while remaining separate confirmation models.

E5 transcript591.9–595.7 says candle colour is immaterial.615.6–634.9 describes low swept / high standing, V retest and external-liquidity target.664.5–679.0 lists this separately from breakout and engulfed-OC confirmations.679–716.6 says lower/half-timeframe engulf often accompanies it, explicitly not always. Thus requiring both patterns would add an unsupported filter.

bishop/v2/entries.py512–518 currently implements a restricted adjacent-pair standing-extreme route. BUY requires the second low below the first low, second high below the first high, and second close above the first low; mapped V, reaction and context evidence remain prerequisites. SELL mirrors this with mapped A. No engulf or candle-colour prerequisite is imposed. The adjacency and strict inequalities are declared restricted_adjacent_E5_OUR_CHOICE, not proof of a universal source definition. No source-backed code correction was established by this review.

EURNZD p13 remains a separate identity problem: the observed H3 pair fails strict body engulf by two ticks. Lower-timeframe wins, an H3 standing pattern or an H3 breakout do not establish the drawing's H3 engulf. Do not fit a tolerance or relabel another confirmation to pass the fixture. Behavioral evaluation should show teacher timeframe, alternative timeframe, direction, protective evidence and outcome separately from exact chart-object identity.

# USDCHF confirmation-scope correction

Code9ac7a742d5ffc5b4694172559f9cec46e6f56cec; replay40583792823; regression40583792706(468passed,5skipped). Frozen before40538418605 and after use unchanged IC manifest/OHLC and replay window.

Same setup_03218dbc80d7f2b74e5dcb2a and order_a73ae1d586194eb3a34fed59: entry79838,target80063,stop79647→79803. Pattern bars are current reference bar_b171f0effbdc5b4eb8b3f801 and engulf bar_0b219a3c3cd483f0ec9720f6. Context low79652 is no longer a risk object. Nearby level79808 binds stop with5ticks buffer. Earlier context remains in qualification provenance.

Source stop79783 is2pips lower than corrected bot stop. Source entry79860 and target80113 are not copied or fitted. Teacher acceptance remains NOT_ESTABLISHED. See visual review README for corrected first/second engulfing interpretation.

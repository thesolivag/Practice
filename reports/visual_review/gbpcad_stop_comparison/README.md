# GBPCAD H2 confirmation-entry stop comparison

`comparison.png` displays an intact original frame from Bishop's own trade
breakdown above an actual-data IC Markets candlestick chart. This is an evidence
figure, not an AI-generated market image or a new simulation.

Source frame: canonical T3 video at sourcePTS420seconds (07:00), original1366×768
pixels, extracted with ffmpeg. Visible header:GBPCAD2h,FOREXCOM. Drawn entry
1.86183, stop1.86041 (14.2pips), target1.87039. The435s frame is a separate H4
view with slightly revised protection; it is not used for the H2 comparison.

Bot figure: frozen IC M5 aggregated to H2 with its declared calendar/anchor;
original report is primary_video_40531068022/video-t3-gbpcad-buy.json.gz.
The first eligible June9 H2 BO candidate becomes available03:00UTC, limit
1.86145, stop1.85847. Its order expired unfilled. All seven June9 H2 BO plans
share stop1.85847. No later winning candidate was selected for this figure.
The highlighted candle is01:00–03:00UTC, low1.86062. Earlier firsttake low1.85852
and later reaction low1.86026 are marked from actual frozen OHLC, with asserted
report/price identities inrender.py. Later candles are explicitly shaded as
unavailable at placement. The purple source price on the IC chart is only a
reference, not proof that the two feeds or source entry candles are identical.

`evidence.json` records the exact source video/report hashes and candidate ID.
`bishop_original_420s.png` and`bot_h2_actual_candles.png` are full-size separate
views;`comparison.png` is the combined report. No trading logic was changed.

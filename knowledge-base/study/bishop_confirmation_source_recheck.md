# Bishop confirmation-entry source recheck — 2026-10-25

Follow-up: the owner authorized three models only: Breakout (including sweep-and-break), Engulfing and 4th man. The correction replaces the mismatched definitions below; see WORKSPACE.md and tests/test_confirmation_models.py. The numbered code findings describe the pre-correction implementation.

Scope: user requested checking Bishop's actual confirmation-entry teaching, including **4th man confirmation**, after disputing the shipped definitions. This is an evidence review, not a detector correction or accuracy validation. No strategy code changed in this review.

## Sources actually inspected

Source branch `claude-bishop-aggressive`, commit `899be43cccb3e94d1739e346a1259973050d45da`; branch not modified or merged. Read both complete extracted transcripts; visually inspected the following sampled video frames alongside their corresponding spoken passages. These are extracted frames/transcripts, not continuous playback or exact broker OHLC labels.

- [Part 5: Approach to Direct and Confirmation Entries — transcript](https://github.com/awujo/practicing/blob/899be43cccb3e94d1739e346a1259973050d45da/knowledge-base/videos/bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/transcript.txt). Diagram sheets 007–012 (06:00–11:45); actual-chart sheets 018, 019, 023, 028 (17:00–18:45, 22:00–22:45, 27:00–27:30).
- [Part 1: Bias, Entries & Confirmation Entries Combined — transcript](https://github.com/awujo/practicing/blob/899be43cccb3e94d1739e346a1259973050d45da/knowledge-base/videos/bishop-defi-bishop-study-10-minute-series-part-1-bias-entries-amp-confirmation-entries-combined/transcript.txt). Visually inspected sheets 004, 006–012, including GBPAUD, JP225, US30 and EURGBP examples.
- Whisper mistranscribes names and terms. Use the user's corrected name **4th man confirmation**; the transcript's garbled rendering of its name is not a separate model.

## What the lesson separates

| Topic | Spoken evidence and visual reference | Supported finding |
|---|---|---|
| Context before entry confirmation | Part 5 04:54–06:15; [sheet 007](https://github.com/awujo/practicing/blob/899be43cccb3e94d1739e346a1259973050d45da/knowledge-base/frames/bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/sheets/sheet_007.jpg) | Wait for price to reach/react at the higher-timeframe key level, then look for lower-timeframe confirmation. The bias breakout and entry confirmation are distinct stages. |
| Breakout | Part 5 06:16–06:41; sheets 007–008 | Diagram shows the reaction creating lower-timeframe structure and an upside break in the BUY example. This is structural confirmation, not merely any close above the user's arbitrary alert price. |
| Sweep and break | Part 5 06:41–07:10; [sheet 008](https://github.com/awujo/practicing/blob/899be43cccb3e94d1739e346a1259973050d45da/knowledge-base/frames/bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/sheets/sheet_008.jpg) | Diagram adds a liquidity sweep followed by the structural break. It is shown separately from the simple breakout. He expresses a preference for these two approaches; that is not backtested performance evidence. |
| Engulfing | Part 5 07:28–09:18; [sheet 009](https://github.com/awujo/practicing/blob/899be43cccb3e94d1739e346a1259973050d45da/knowledge-base/frames/bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/sheets/sheet_009.jpg), [sheet 010](https://github.com/awujo/practicing/blob/899be43cccb3e94d1739e346a1259973050d45da/knowledge-base/frames/bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/sheets/sheet_010.jpg) | He draws two consecutive bearish candles creating an open-close key level, then invalidation of that bearish level and a bullish level to return to. He inverts the drawing for SELL. This is not established as the textbook two-body-coverage condition used in the shipped optional filter. |
| 4th man confirmation | Part 5 09:18–11:19; [sheet 011](https://github.com/awujo/practicing/blob/899be43cccb3e94d1739e346a1259973050d45da/knowledge-base/frames/bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/sheets/sheet_011.jpg) | BUY drawing: reference candle with a high/low; next candle sweeps its low while its high remains standing, closes back within that reference range, and forms the V-shaped key level for a later return. The drawn sweep candle is **bearish** in this BUY example. Reference candle colour is explicitly said not to matter (09:51–09:56). A bullish sweep-candle requirement is unsupported and excludes the drawn example. SELL must be specified with its own mirrored geometry, not inferred from a candle-colour label. |
| Lower-timeframe corroboration | Part 5 11:19–11:51; [sheet 012](https://github.com/awujo/practicing/blob/899be43cccb3e94d1739e346a1259973050d45da/knowledge-base/frames/bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/sheets/sheet_012.jpg) | He relates the last pattern to an engulfing on a lower timeframe, e.g. H1→M30, and explicitly says this does not occur every time. It is not a mandatory filter proved by this lesson. |

## Actual-chart cross-checks

- Part 5 17:00–18:45, XAUUSD: he switches H4→H3 for engulfing, then H1 for breakout and M45/M30 for sweep-and-break. These are alternative confirmations at the reaction, and a valid confirmation does not guarantee price will retest its entry level. Sheets 018–019 inspected.
- Part 5 27:07–27:33, GBPCAD: after H4 rejection he shows H2 engulfing, H3 engulfing/breakout with liquidity, and H1 breakout with liquidity. Sheet 028 inspected. This further contradicts reducing all confirmation types to one generic price-crossing rule.
- Part 1 03:15–03:45, GBPAUD: H4 reaction followed by H1 bearish breakout and the later entry. Sheet 004 inspected.
- Part 1 04:57–05:18, JP225: H4 reaction followed by H1 sweep-and-break confirmation. Sheet 006 inspected.
- Part 1 10:13–10:52, EURGBP: H4 reaction followed by H2 breakout; he separately states that he personally need not wait for the higher rejection candle to finish. Sheet 011 inspected. This is not permission to label a forming lower-timeframe confirmation as closed.

## Corrections to previous claims and shipped code

1. Earlier claim that preserving the reference high was entirely invented was too broad: Part 5 explicitly says **the high should be standing** at 10:15–10:22. The unsupported added condition is, in particular, requiring the sweep candle to be bullish for BUY. The range-close geometry, generated key level and subsequent retest also require explicit representation.
2. `slk/user_alerts.py:matches`, `pinbar_v1`, currently requires BUY `close > open` and SELL `close < open`; the BUY drawing fails this condition. It must not be advertised as verified 4th man confirmation.
3. `body_engulfing` currently checks generic consecutive candle-body coverage. Bishop's illustrated open-close-level invalidation is a different specification and cannot be replaced by that filter.
4. `cisd_v1` currently checks the open of the beginning of an opposing candle run. The reviewed Bishop lessons do not establish that this is his engulfing algorithm, breakout algorithm or a separately named CISD model. The code's eight-candle cap is an implementation constraint, not a teacher rule.
5. Simple `closed_crossing` through a user level does not by itself detect the illustrated structural breakout or sweep-and-break.
6. These code findings are specification mismatches, not repaired implementation. Existing tests validate the existing definitions; they do not validate fidelity to the teacher.

## Remaining before a faithful detector can be claimed

Use the illustrated sequences to define separate structural breakout, sweep-and-break, open-close engulfing and 4th man states, including how each reference/level is selected, when confirmation exists versus when its retest is an entry, and invalidation. Derive positive and negative fixtures from the source geometry; do not manufacture precise broker OHLC from screenshot pixels. Any unresolved equality/tolerance or multi-candle cases must be labeled implementation choices. Keep CISD separate unless its own source establishes it. This review does not silently patch, migrate or cancel existing user watches.

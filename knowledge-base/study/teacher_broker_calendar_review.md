# Current broker schedule → diagnostic calendar review

2026-10-24. The new offline adapter `bishop/teacher_calendar.py` derives separate
frozen replay inputs from raw collector files. It does not change source
fixtures, raw acquisition, engine behavior, historical outcomes, or market data.

## Protocol proof inspected

Read the official Spotware protobuf source directly on this date:
https://raw.githubusercontent.com/spotware/openapi-proto-messages/main/OpenApiModelMessages.proto

Retrieved full-source SHA256:
`56338dcac45a149227678b7c23637d64f4e2b607f6649af82394ce5c0957fedf`.
This URL tracks main; the hash identifies the actually inspected content.

`ProtoOAInterval.startSecond` is documented as seconds starting from
**SUNDAY 00:00 in the specified timezone, inclusive**. `endSecond` uses the
same origin and is **exclusive**. Therefore Monday00:00 is86400, not0.
`ProtoOAHoliday.holidayDate` is the amount of days from Jan1,1970;
`isRecurring=true` means yearly repetition. Required `scheduleTimeZone` applies
to that holiday. Optional `startSecond`/`endSecond` are seconds from midnight
of the holiday day when the holiday starts/finishes. These comments do not
provide omitted-field default hours or prove historical schedule applicability.

## Derived policy and limits

- Use only the provider's exact timezone string when `ZoneInfo` recognizes it.
  Unknown broker aliases are unsupported; no GMT offset or US DST substitution.
- Validate integer weekly seconds0…604800, strictly positive intervals, sorted
  disjoint geometry (touching is allowed), and separately0…86400 holiday limits.
  Weekly wraparound and holiday overnight/equal-boundary interpretations are
  unsupported rather than guessed.
- Missing schedule, timezone or holiday-list fields are unsupported. Every
  holiday needs explicit date, boolean recurrence, timezone and both optional
  limits to be usable. Missing limits do not become a full-day holiday.
- Expand weekly intervals from local Sunday using wall-clock arithmetic and
  convert via the declared IANA zone. Reject ambiguous/nonexistent boundaries.
  Also reject the entire requested range when an intersected local week
  changes UTC offset. Thus a May–August range can be usable, while a400-day
  history crossing November/March may be explicitly unsupported. This is a
  conservative automation policy, not proof that provider DST is unknowable.
- Explicit holiday intervals become exclusions within the weekly openings.
  Overlapping holiday records, unknown leap-day recurrence behavior and any
  unaligned calendar/base-bar boundary fail closed. No partial OHLC bar is
  split into presumed tradable and closed subintervals.
- Current schedules projected onto prior dates are always
  `CURRENT_SCHEDULE_BACKPROJECTION_HYPOTHESIS`, with
  `NOT_HISTORICAL_CALENDAR_CERTIFICATION`. Current symbol metadata and holidays
  are not a historical exchange calendar. Resulting inputs are alternate-feed
  diagnostics only; they cannot certify teacher-feed equivalence or a match.
- ETHUSDT→ETHUSD and any explicitly surrogate mapping remain blocked regardless
  of schedule availability. A calendar cannot fix quote-currency mismatch.

## Separate frozen artifacts and coverage

`build_calendar(record,start,end)` returns an explicit calendar/hashes only
with status `SUPPORTED_HYPOTHESIS`; otherwise `UNSUPPORTED` and a reason.

`derive_snapshot(raw_path,manifest_path,schedule_path,out_dir)` verifies the
raw hash and exact pair/broker-symbol evidence match. It creates a new gzip
CSV, separate manifest and JSON ledger under a content-derived ID, refusing
existing outputs. Raw files remain byte-identical. Every retained row's
original field values survive, including zero volume. Rows outside the declared
calendar/request are excluded with source line, interval, reason and row hash;
raw/source-manifest/schedule-file hashes preserve auditability. Expected
in-session missing slots remain missing and are enumerated in the ledger;
no candle or zero-volume row is fabricated, repaired or removed for appearance.
A parsed interval index keeps per-row calendar checks logarithmic.

Run offline with:

```sh
python -m bishop.teacher_calendar --raw SNAPSHOT.csv.gz \
  --manifest SNAPSHOT.csv.manifest.json --schedules symbol_schedules.json \
  --out DERIVED_DIRECTORY
```

The derived manifest keeps symbol/price/anchor metadata and changes only data
hash/coverage/calendar/derivation fields needed for the separate snapshot.
Its `replay_calendar_status` explicitly ends in `HYPOTHESIS_DIAGNOSTIC_ONLY`.
A consumer must continue to report that uncertainty instead of promoting it to
historical calendar certification.

Validation:10 offline synthetic tests pass covering Sunday origin and endpoint
semantics, invalid/overlapping intervals, exact timezone recognition, NY DST
transition rejection, epoch-day/yearly holiday exclusions, absent optional
holiday limits, immutable raw files, repeat-output refusal, retained zero volume,
visible in-session gaps, excluded closed-session rows, and surrogate refusal.
These are engineering checks, not acquired-data or teacher-example acceptance.

Explicit bounded subsets are supported: add `--start ISO --end ISO` or call
`derive_snapshot(..., start=..., end=...)`. Bounds must lie within the original
raw requested range. The calendar is expanded only for that declared subset;
the raw file hash still covers the entire original acquisition. Both raw and
derived ranges appear in the ledger/manifest; out-of-subset rows receive
`OUTSIDE_DERIVED_SUBSET` exclusions. Thus a caller can explicitly choose a
35-day May–August case window from a400-day H1 acquisition whose full current
schedule backprojection crosses unsupported DST weeks. This does not silently
certify or fill the unused historical context.

`derive_batch(inputs, schedule_path, out_dir)` accepts explicit dictionaries
`{path, manifest, start?, end?}` and returns a tuple of per-input
`DERIVED_HYPOTHESIS` artifact paths or `UNSUPPORTED` reasons. It does not infer
subsets from prices, source outcomes or fixture dates. The caller chooses
corresponding M5 bounds or an explicit case history/as-of interval. Ordinary
malformed files/hash errors and existing frozen outputs still fail loudly.
Two additional tests cover crop evidence/ledger, out-of-range refusal, whole
DST-context refusal, safe explicit subset and mixed supported/unsupported
batch outcomes: **12 offline tests now pass**.

## Optional disputed-slot observation policy

`withhold_disputed_slots=True` (CLI `--withhold-disputed-slots`) selects
`withhold_disputed_observations_v1`; default strict derivation is unchanged.
A nonzero/unknown-volume quote outside the current schedule is evidence of a
calendar conflict, not proof that the historical minute was tradable. In this
policy its OHLC remains withheld from the derived CSV and preserved byte-for-byte
in the raw acquisition. Its source line/hash and interval remain in the ledger.

The disputed base-bar intervals are added to a **required-observation calendar**
(union with the proposed openings; remove those intervals from closed masks).
This forces each disputed interval to remain a missing expected slot, rather
than silently treating it as harmless overnight closure. The machine semantics
are `REQUIRED_OBSERVATIONS_WITH_DISPUTED_SLOTS_HYPOTHESIS`, with
`disputed_slots_are_tradable=false`; no synthetic prices or fills are supplied.
Manifest `calendar_conflicts_handled_as_missing_observations=true`,
`calendar_conflict_required_missing_slots` and ledger
`disputed_observation_slots` expose the evidence. The new policy/version and
calendar hash give separate frozen derivation identities.

Existing feed coverage then reports the missing intervals and splits segments;
structure/story invalidation can consume that coverage, and existing simulation
censors exposure crossing missing active observations. Fully observed later
periods remain available for partial diagnostics. This never converts an
unresolved calendar conflict into a teacher match or historical calendar proof.
Missing/ambiguous schedule semantics, partial base-bar boundaries and surrogate
symbol refusal still fail closed. Two additional engineering tests prove an
explicit one-minute missing slot, retained raw quote/withheld CSV, segment split,
`MISSING_ACTIVE_DATA` censoring of pre-existing exposure, later-period evaluation,
and removal of the disputed interval from a holiday mask. **14 tests pass.**

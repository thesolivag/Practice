"""Offline current-schedule backprojection HYPOTHESIS, never history certification.

Protocol semantics: Spotware OpenApiModelMessages.proto ProtoOAInterval and
ProtoOAHoliday. Unknown optional holiday limits and DST transition weeks fail
closed. Raw acquisition files are never rewritten.
"""
import argparse
from bisect import bisect_right
import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import gzip
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bishop.v2.types import utc, stable_id
from bishop.v2.aggregation import minutes

CERTIFICATION = 'NOT_HISTORICAL_CALENDAR_CERTIFICATION'
SEMANTICS_URL = 'https://raw.githubusercontent.com/spotware/openapi-proto-messages/main/OpenApiModelMessages.proto'


class UnsupportedCalendar(ValueError):
    pass


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise UnsupportedCalendar('INVALID_' + name)
    return value


def _zone(name):
    if not isinstance(name, str) or not name:
        raise UnsupportedCalendar('MISSING_EXPLICIT_TIMEZONE')
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise UnsupportedCalendar('UNKNOWN_TIMEZONE:' + name) from exc


def _wall(naive, zone):
    values = []
    for fold in (0, 1):
        at = naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if at.astimezone(zone).replace(tzinfo=None) == naive:
            values.append(at)
    if len(set(values)) != 1:
        raise UnsupportedCalendar('AMBIGUOUS_OR_NONEXISTENT_LOCAL_BOUNDARY')
    return values[0]


def _disjoint(intervals, reason):
    ordered = sorted(intervals)
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise UnsupportedCalendar(reason)
    return ordered


def build_calendar(record, start, end):
    """Return SUPPORTED_HYPOTHESIS/calendar or UNSUPPORTED/reason; no guessing.

    record is one raw collector symbol record (not its surrounding wrapper).
    Sunday-based wall seconds are validated as disjoint; touching is allowed.
    An entire requested range is unsupported if any intersected week crosses
    a timezone offset transition, even if its individual session endpoints are
    otherwise unambiguous. This conservative policy is deliberately explicit.
    """
    start, end = utc(start), utc(end)
    if start >= end:
        raise ValueError('calendar start must precede end')
    base = {'certification': CERTIFICATION, 'historical_applicability': 'CURRENT_SCHEDULE_BACKPROJECTION_HYPOTHESIS',
            'semantics_url': SEMANTICS_URL, 'schedule_hash': stable_id('schedule', record),
            'requested_start': start.isoformat(), 'requested_end': end.isoformat(),
            'dst_policy': 'REJECT_OFFSET_TRANSITION_WEEKS_V1'}
    try:
        zone = _zone(record.get('scheduleTimeZone'))
        if 'schedule' not in record or not record['schedule']:
            raise UnsupportedCalendar('MISSING_OR_EMPTY_WEEKLY_SCHEDULE')
        weekly = []
        for item in record['schedule']:
            lo = _integer(item.get('startSecond'), 'WEEK_START', 0, 604800)
            hi = _integer(item.get('endSecond'), 'WEEK_END', 0, 604800)
            if lo >= hi:
                raise UnsupportedCalendar('WRAPPING_OR_EMPTY_WEEKLY_INTERVAL')
            weekly.append((lo, hi))
        weekly = _disjoint(weekly, 'OVERLAPPING_WEEKLY_INTERVALS')
        if 'holiday' not in record:
            raise UnsupportedCalendar('MISSING_HOLIDAY_FIELD')
        holidays = []
        for holiday in record['holiday']:
            if type(holiday.get('holidayDate')) is int and type(holiday.get('isRecurring')) is bool:
                day=(datetime(1970,1,1)+timedelta(days=holiday['holidayDate'])).date()
                years=range(start.year-1,end.year+2) if holiday['isRecurring'] else (day.year,)
                possibly_relevant=False
                for year in years:
                    try: date=day.replace(year=year)
                    except ValueError:
                        possibly_relevant=True;break
                    midnight=datetime.combine(date,datetime.min.time(),tzinfo=timezone.utc)
                    # Every legal UTC offset is strictly within one day. This
                    # bound proves irrelevance without choosing a missing zone.
                    if midnight-timedelta(days=1)<end and start<midnight+timedelta(days=2):
                        possibly_relevant=True;break
                if not possibly_relevant: continue
            # Unsettled intraday limits on a holiday outside this requested
            # calendar cannot affect its sessions. Determine date relevance
            # first; keep all validation for any potentially intersecting day.
            date_keys=('holidayDate','isRecurring','scheduleTimeZone')
            if all(key in holiday for key in date_keys):
                if type(holiday['holidayDate']) is not int or type(holiday['isRecurring']) is not bool:
                    raise UnsupportedCalendar('INVALID_HOLIDAY_DATE_OR_RECURRENCE')
                day=(datetime(1970,1,1)+timedelta(days=holiday['holidayDate'])).date()
                hzone=_zone(holiday['scheduleTimeZone'])
                years=range(start.year-1,end.year+2) if holiday['isRecurring'] else (day.year,)
                possible=False
                for year in years:
                    try: date=day.replace(year=year)
                    except ValueError:
                        possible=True;break
                    midnight=datetime.combine(date,datetime.min.time())
                    a,b=_wall(midnight,hzone),_wall(midnight+timedelta(days=1),hzone)
                    if a<end and start<b: possible=True;break
                if not possible: continue
            required = ('holidayDate', 'isRecurring', 'startSecond', 'endSecond', 'scheduleTimeZone')
            if any(key not in holiday for key in required):
                raise UnsupportedCalendar('UNKNOWN_OPTIONAL_HOLIDAY_LIMITS')
            if type(holiday['holidayDate']) is not int or type(holiday['isRecurring']) is not bool:
                raise UnsupportedCalendar('INVALID_HOLIDAY_DATE_OR_RECURRENCE')
            day = (datetime(1970, 1, 1) + timedelta(days=holiday['holidayDate'])).date()
            hzone = _zone(holiday['scheduleTimeZone'])
            lo = _integer(holiday['startSecond'], 'HOLIDAY_START', 0, 86400)
            hi = _integer(holiday['endSecond'], 'HOLIDAY_END', 0, 86400)
            if lo >= hi:
                raise UnsupportedCalendar('WRAPPING_OR_EMPTY_HOLIDAY')
            years = range(start.year-1, end.year+2) if holiday['isRecurring'] else (day.year,)
            for year in years:
                try:
                    date = day.replace(year=year)
                except ValueError as exc:
                    raise UnsupportedCalendar('UNSETTLED_LEAP_DAY_RECURRENCE') from exc
                midnight = datetime.combine(date, datetime.min.time())
                a, b = _wall(midnight+timedelta(seconds=lo), hzone), _wall(midnight+timedelta(seconds=hi), hzone)
                if a < end and start < b:
                    holidays.append((max(a, start), min(b, end)))
        holidays = _disjoint(holidays, 'OVERLAPPING_HOLIDAYS')
        first = start.astimezone(zone).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
        first -= timedelta(days=(first.weekday()+1) % 7)
        opened = []
        week = first
        while _wall(week, zone) < end:
            # Check every local day, including week end; no silent fold policy.
            offsets = {(_wall(week+timedelta(days=i), zone).astimezone(zone)).utcoffset() for i in range(8)}
            if len(offsets) != 1:
                raise UnsupportedCalendar('DST_TRANSITION_WEEK_UNSUPPORTED')
            for lo, hi in weekly:
                a, b = _wall(week+timedelta(seconds=lo), zone), _wall(week+timedelta(seconds=hi), zone)
                if a < end and start < b:
                    opened.append((max(a, start), min(b, end)))
            week += timedelta(days=7)
        opened = _disjoint(opened, 'OVERLAPPING_DERIVED_INTERVALS')
        calendar = {'id': 'explicit_intervals_v1',
                    'open_intervals': [[a.isoformat(), b.isoformat()] for a, b in opened],
                    'closed_intervals': [[a.isoformat(), b.isoformat()] for a, b in holidays]}
        return {**base, 'status': 'SUPPORTED_HYPOTHESIS', 'timezone': zone.key,
                'calendar': calendar, 'calendar_hash': stable_id('calendar', calendar)}
    except (UnsupportedCalendar, OverflowError) as exc:
        return {**base, 'status': 'UNSUPPORTED', 'reason': str(exc)}


def _required_observations(calendar, disputed):
    """Union required observation slots, never assert that they were tradable."""
    intervals = [(utc(a), utc(b)) for a, b in calendar['open_intervals']]
    intervals.extend((utc(item['start']), utc(item['end'])) for item in disputed)
    merged = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    closed = [(utc(a), utc(b)) for a, b in calendar['closed_intervals']]
    for slot in disputed:
        lo, hi = utc(slot['start']), utc(slot['end'])
        pieces = []
        for a, b in closed:
            if b <= lo or hi <= a:
                pieces.append((a, b))
            else:
                if a < lo:
                    pieces.append((a, lo))
                if hi < b:
                    pieces.append((hi, b))
        closed = pieces
    return {'id': 'explicit_intervals_v1',
            'open_intervals': [[a.isoformat(), b.isoformat()] for a, b in merged],
            'closed_intervals': [[a.isoformat(), b.isoformat()] for a, b in closed],
            'semantics': 'REQUIRED_OBSERVATIONS_WITH_DISPUTED_SLOTS_HYPOTHESIS',
            'disputed_slots_are_tradable': False}


def derive_snapshot(raw_path, manifest_path, schedule_path, out_dir, *, start=None, end=None, withhold_disputed_slots=False):
    """Write separate frozen filtered CSV, manifest and exclusion/gap ledger.

    Uses the raw manifest's requested range and exact broker symbol match.
    Every retained row is unchanged, including zero-volume rows. Expected
    in-session missing slots remain gaps and are listed, never synthesized.
    """
    if type(withhold_disputed_slots) is not bool:
        raise ValueError('withhold_disputed_slots must be boolean')
    raw_path, manifest_path, schedule_path = map(Path, (raw_path, manifest_path, schedule_path))
    raw = raw_path.read_bytes()
    metadata = json.loads(manifest_path.read_text())
    schedules_raw = schedule_path.read_bytes()
    schedules = json.loads(schedules_raw)
    if metadata.get('sha256') != sha256(raw).hexdigest():
        raise ValueError('raw snapshot hash mismatch')
    if metadata.get('asset_class') == 'CRYPTO_SURROGATE' or 'SURROGATE' in metadata.get('symbol_mapping_status', ''):
        raise UnsupportedCalendar('SURROGATE_MAPPING_REMAINS_BLOCKED')
    matches = [r for r in schedules.get('symbols', ()) if r.get('broker_symbol') == metadata.get('broker_symbol')
               and r.get('requested_pair') == metadata.get('symbol')]
    if len(matches) != 1:
        raise UnsupportedCalendar('SCHEDULE_SYMBOL_MATCH_NOT_UNIQUE')
    record = matches[0]['record']
    if record.get('name') != metadata.get('broker_symbol'):
        raise UnsupportedCalendar('SCHEDULE_RECORD_SYMBOL_MISMATCH')
    raw_start, raw_end = utc(metadata['requested_start']), utc(metadata['requested_end'])
    subset_start = utc(start) if start is not None else raw_start
    subset_end = utc(end) if end is not None else raw_end
    if not raw_start <= subset_start < subset_end <= raw_end:
        raise ValueError('derived subset must lie within the raw requested range')
    result = build_calendar(record, subset_start, subset_end)
    if result['status'] != 'SUPPORTED_HYPOTHESIS':
        raise UnsupportedCalendar(result['reason'])
    n = minutes(metadata['base_tf'])
    if n is None:
        raise UnsupportedCalendar('INTRADAY_INPUT_REQUIRED')
    step = timedelta(minutes=n)
    start, end = subset_start, subset_end
    calendar = result['calendar']
    # Partial base slots cannot be safely split into in/out-session extrema.
    boundaries = [utc(point) for key in ('open_intervals', 'closed_intervals') for interval in calendar[key] for point in interval]
    if any(point.timestamp() % step.total_seconds() for point in boundaries):
        raise UnsupportedCalendar('CALENDAR_BOUNDARIES_NOT_BASE_ALIGNED')
    opens = tuple((utc(lo), utc(hi)) for lo, hi in calendar['open_intervals'])
    closes = tuple((utc(lo), utc(hi)) for lo, hi in calendar['closed_intervals'])
    open_starts = tuple(a for a, _ in opens)
    close_ends = tuple(b for _, b in closes)
    def contained(a, b):
        index = bisect_right(open_starts, a)-1
        if index < 0 or b > opens[index][1]:
            return False
        closed = bisect_right(close_ends, a)
        return closed == len(closes) or closes[closed][0] >= b
    decoded = gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
    reader = csv.DictReader(io.StringIO(decoded.decode('utf-8-sig')))
    fields = reader.fieldnames
    if not fields or not set(('open','high','low','close')).issubset(fields):
        raise ValueError('OHLC CSV required')
    kept, exclusions, seen = [], [], set()
    observed_conflicts=0
    disputed = []
    previous = None
    for number, row in enumerate(reader, 2):
        a = utc(row.get('start') or row.get('time') or '')
        b = utc(row['end']) if row.get('end') else a+step
        if b-a != step or a.timestamp() % step.total_seconds():
            raise UnsupportedCalendar('INVALID_BASE_ROW_INTERVAL')
        if previous is not None and a < previous:
            raise ValueError('unordered, duplicate or overlapping rows')
        previous = b
        if not start <= a < b <= end or not contained(a, b):
            if start<=a<b<=end and row.get('volume','')!='0':
                observed_conflicts+=1
                if withhold_disputed_slots:
                    disputed.append({'start':a.isoformat(),'end':b.isoformat(),
                                     'csv_line':number,'row_hash':stable_id('csv_row',row),
                                     'reason':'CURRENT_SCHEDULE_CONFLICT_WITHHELD_NO_PRICE_ASSUMPTION'})
            exclusions.append({'csv_line': number, 'start': a.isoformat(), 'end': b.isoformat(),
                               'reason': 'OUTSIDE_DERIVED_SUBSET' if not start <= a < b <= end else 'OUTSIDE_DECLARED_CALENDAR',
                               'row_hash': stable_id('csv_row', row)})
        else:
            kept.append(row)
            seen.add(a)
    if withhold_disputed_slots:
        calendar = _required_observations(calendar, disputed)
        opens = tuple((utc(lo), utc(hi)) for lo, hi in calendar['open_intervals'])
        closes = tuple((utc(lo), utc(hi)) for lo, hi in calendar['closed_intervals'])
        open_starts = tuple(a for a, _ in opens)
        close_ends = tuple(b for _, b in closes)
    observation_hash = stable_id('calendar', calendar)
    # Boundaries were validated against this base grid. Enumerating each open
    # interval avoids reparsing every calendar interval for every minute.
    wanted=set()
    for lo,hi in opens:
        at=lo
        while at<hi:
            if contained(at,at+step):wanted.add(at)
            at+=step
    missing = sorted(wanted-seen)
    content = io.StringIO(newline='')
    writer = csv.DictWriter(content, fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(kept)
    frozen = gzip.compress(content.getvalue().encode(), mtime=0)
    identity = (metadata['sha256'], sha256(schedules_raw).hexdigest(), observation_hash)
    derivation_id = stable_id('calendar_derivation', *identity, 'withhold_disputed_observations_v1') if withhold_disputed_slots else stable_id('calendar_derivation', *identity)
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    csv_path = target/(derivation_id+'.csv.gz')
    derived_manifest_path = csv_path.with_suffix('.manifest.json')
    ledger_path = target/(derivation_id+'.calendar_ledger.json')
    if any(path.exists() for path in (csv_path, derived_manifest_path, ledger_path)):
        raise FileExistsError('frozen calendar derivation already exists')
    ledger = {'schema_version':'teacher_calendar_ledger_v1','derivation_id':derivation_id,
              'raw_sha256':metadata['sha256'],'schedule_file_sha256':sha256(schedules_raw).hexdigest(),
              'source_manifest_sha256':sha256(manifest_path.read_bytes()).hexdigest(),
              'schedule_evidence':result,'excluded_rows':exclusions,'retained_rows':len(kept),
              'missing_in_session_slots':[v.isoformat() for v in missing],
              'coverage_status':'INCOMPLETE' if missing else 'COMPLETE_UNDER_CURRENT_SCHEDULE_HYPOTHESIS',
              'historical_calendar_certification':CERTIFICATION,
              'calendar_conflict_nonzero_or_unknown_volume_rows':observed_conflicts,
              'calendar_conflicts_handled_as_missing_observations':withhold_disputed_slots,
              'disputed_observation_slots':disputed,
              'calendar_conflict_required_missing_slots':[item['start'] for item in disputed],
              'observation_calendar':calendar,
              'observation_calendar_hash':observation_hash,
              'derivation_policy':'withhold_disputed_observations_v1' if withhold_disputed_slots else 'strict_current_schedule_v1',
              'raw_requested_range':[raw_start.isoformat(),raw_end.isoformat()],
              'derived_subset_range':[start.isoformat(),end.isoformat()]}
    derived = {**metadata,'requested_start':start.isoformat(),'requested_end':end.isoformat(),
               'raw_requested_range':[raw_start.isoformat(),raw_end.isoformat()],'sha256':sha256(frozen).hexdigest(),'calendar_id':'explicit_intervals_v1',
               'calendar':calendar,'calendar_version':observation_hash,
               'replay_calendar_status':'CURRENT_SCHEDULE_BACKPROJECTION_HYPOTHESIS_DIAGNOSTIC_ONLY',
               'calendar_conflict_nonzero_or_unknown_volume_rows':observed_conflicts,
               'calendar_conflicts_handled_as_missing_observations':withhold_disputed_slots,
               'calendar_conflict_required_missing_slots':[item['start'] for item in disputed],
               'calendar_observation_semantics':'REQUIRED_OBSERVATIONS_WITH_DISPUTED_SLOTS_HYPOTHESIS' if withhold_disputed_slots else 'CURRENT_SCHEDULE_BACKPROJECTION_HYPOTHESIS',
               'raw_collection_status':'DERIVED_CALENDAR_FILTERED_DIAGNOSTIC',
               'coverage_status':ledger['coverage_status'],'rows':len(kept),
               'zero_volume_rows':sum(row.get('volume') is not None and float(row['volume']) == 0 for row in kept),
               'first_bar':min(seen).isoformat() if seen else None,'last_bar':max(seen).isoformat() if seen else None,
               'calendar_derivation':{'id':derivation_id,'ledger':str(ledger_path),'raw_path':str(raw_path),
                                      'raw_sha256':metadata['sha256'],'schedule_file_sha256':sha256(schedules_raw).hexdigest(),
                                      'certification':CERTIFICATION}}
    csv_path.write_bytes(frozen)
    derived_manifest_path.write_text(json.dumps(derived,indent=2)+'\n')
    ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
    return {'path':str(csv_path),'manifest':str(derived_manifest_path),'ledger':str(ledger_path)}


def derive_batch(inputs, schedule_path, out_dir, *, withhold_disputed_slots=False):
    """Offline batch, retaining per-input unsupported outcomes.

    Each input is {path, manifest, start?, end?}; optional subset boundaries
    must be explicitly chosen by the caller. No discovery or date inference.
    """
    results = []
    for item in inputs:
        raw = item.get('path', item.get('raw_path'))
        manifest = item.get('manifest', item.get('manifest_path'))
        if raw is None or manifest is None:
            raise ValueError('batch input requires path and manifest')
        evidence = {'raw_path': str(raw), 'source_manifest': str(manifest),
                    'subset_start': item.get('start'), 'subset_end': item.get('end')}
        try:
            paths = derive_snapshot(raw, manifest, schedule_path, out_dir,
                                    start=item.get('start'), end=item.get('end'),
                                    withhold_disputed_slots=withhold_disputed_slots)
            results.append({**evidence, 'status': 'DERIVED_HYPOTHESIS', **paths})
        except UnsupportedCalendar as exc:
            results.append({**evidence, 'status': 'UNSUPPORTED', 'reason': str(exc),
                            'certification': CERTIFICATION})
    return tuple(results)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('raw','manifest','schedules','out'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--start');parser.add_argument('--end')
    parser.add_argument('--withhold-disputed-slots',action='store_true')
    args=parser.parse_args(argv)
    try:
        print(json.dumps(derive_snapshot(args.raw,args.manifest,args.schedules,args.out,start=args.start,end=args.end,withhold_disputed_slots=args.withhold_disputed_slots),indent=2))
        return 0
    except UnsupportedCalendar as exc:
        print(json.dumps({'status':'UNSUPPORTED','reason':str(exc),'certification':CERTIFICATION}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

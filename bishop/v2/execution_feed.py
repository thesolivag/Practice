"""Validate a finer frozen feed for execution only, never strategy detection."""
from .aggregation import aggregate, minutes
from .feed import load_feed
from .types import utc, stable_id
from bisect import bisect_right


def prepare_execution_feed(spec, detection, base, scan_start, as_of):
    if not scan_start or not base:
        raise ValueError('execution refinement requires scan_start and detection bars')
    if set(spec) != {'path', 'manifest'}:
        raise ValueError('execution feed requires path and manifest only')
    fine = load_feed(spec['path'], spec['manifest'], as_of, scan_start)
    coarse_inst, fine_inst = detection['instrument'], fine['instrument']
    for key in ('symbol', 'tick_size', 'distance_unit', 'calendar_id', 'anchor_id', 'price_basis', 'venue'):
        if getattr(coarse_inst, key) != getattr(fine_inst, key):
            raise ValueError('execution instrument convention mismatch: ' + key)
    # source_id includes the timeframe, so compare the declared provider/symbol.
    for key in ('provider', 'broker_symbol', 'calendar', 'calendar_version', 'anchor_version'):
        if detection.get('manifest', {}).get(key) != fine['manifest'].get(key):
            raise ValueError('execution source convention mismatch: ' + key)
    if coarse_inst.venue == 'ICMARKETS':
        def environment(feed):
            meta=feed.get('manifest', {})
            if not meta.get('provider') or not meta.get('broker_symbol'):
                raise ValueError('execution source identity is incomplete')
            symbol_id=meta.get('symbol_metadata', {}).get('symbol_id')
            matches=[env for env in ('demo','live') if meta.get('source_id') == stable_id(
                'source','ICMARKETS',env,symbol_id,meta['broker_symbol'],meta.get('base_tf'))]
            if len(matches)!=1 or symbol_id is None:
                raise ValueError('execution source environment cannot be verified')
            return matches[0],symbol_id
        if environment(detection)!=environment(fine):
            raise ValueError('execution source environment or symbol differs')
    if not fine['bars']:
        raise ValueError('execution refinement requires finer bars')
    if any(a.available_at > b.available_at for a, b in zip(fine['bars'], fine['bars'][1:])):
        raise ValueError('nonmonotone execution publication requires receipt-order replay')
    coarse_tf = base[0].tf
    if minutes(fine['manifest']['base_tf']) >= minutes(coarse_tf):
        raise ValueError('execution feed must be finer than detection feed')
    calendar = detection.get('manifest', {}).get('calendar', coarse_inst.calendar_id)
    rolled = aggregate(fine['bars'], coarse_tf, fine_inst, as_of, calendar=calendar)['bars']
    expected = {b.start: b for b in base if b.start >= utc(scan_start)}
    actual = {b.start: b for b in rolled}
    if not actual or not actual.keys() <= expected.keys():
        raise ValueError('execution rollup coverage does not match detection window')
    fields = ('end', 'open_ticks', 'high_ticks', 'low_ticks', 'close_ticks')
    if any(any(getattr(b, k) != getattr(actual[start], k) for k in fields)
           for start, b in expected.items() if start in actual):
        raise ValueError('execution rollup OHLC differs from frozen detection input')
    # Incomplete bins cannot establish equality, but observed prices may not
    # contradict the frozen coarse range or a present boundary open/close.
    starts=sorted(expected)
    for bar in fine['bars']:
        i=bisect_right(starts,bar.start)-1
        if i<0: raise ValueError('finer bar outside detection window')
        coarse=expected[starts[i]]
        if (bar.end>coarse.end or bar.high_ticks>coarse.high_ticks
                or bar.low_ticks<coarse.low_ticks
                or (bar.start==coarse.start and bar.open_ticks!=coarse.open_ticks)
                or (bar.end==coarse.end and bar.close_ticks!=coarse.close_ticks)):
            raise ValueError('observed execution prices contradict frozen detection bar')
    incomplete=sorted(expected.keys()-actual.keys())
    return fine, dict(scope='EXECUTION_ONLY_DETECTION_UNCHANGED',
                      hashes=fine['hashes'], coverage=fine['coverage'],
                      rollup_status='EXACT_OHLC_MATCH' if not incomplete else 'EXACT_ON_COMPLETE_BINS_PARTIAL_COVERAGE',
                      compared_bars=len(actual), incomparable_bins=[t.isoformat() for t in incomplete],
                      missing_data_policy='CENSOR_ACTIVE_EXECUTION_NO_IMPUTATION_NO_FALLBACK')

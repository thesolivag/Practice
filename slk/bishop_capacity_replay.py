"""Capacity-corrected research fork. No live-table writes or messages.

Every decision receives only closed bars at its replay clock. Execution is a
separate consumer of frozen orders. Current rules/preferences are reconstructed
historically; these are not archived historical web-app decisions.
"""
import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import time

VERSION = 'bishop_capacity_replay_v2'
TERMINAL = {'WIN', 'LOSS', 'BREAK_EVEN', 'CANCELLED', 'REPLACED', 'EXPIRED', 'CENSORED'}
MODES = ('standalone', 'kk_aligned', 'recognition')


def dump(path, value):
    from bishop.v2.types import jsonable
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    value = {**value, 'seen_flows': sorted(value['seen_flows'])} if isinstance(value, dict) and 'seen_flows' in value else value
    content = json.dumps(jsonable(value), sort_keys=True, allow_nan=False)
    if str(path).endswith('.gz'):
        with gzip.open(path, 'wt') as f: f.write(content)
    else: path.write_text(content + '\n')


def load(path):
    with (gzip.open(path, 'rt') if str(path).endswith('.gz') else open(path)) as f:
        return json.load(f)


def prefix(feed, now, days=None):
    """The only detector input boundary; never return a forming/future bar."""
    bars = tuple(b for b in feed['bars'] if b.complete and b.available_at <= now
                 and (days is None or b.start >= now - timedelta(days=days)))
    return {**feed, 'bars': bars, 'hashes': {}}


def thaw_setup(s):
    from bishop.v2.types import Setup, Clock
    return Setup(**{**s, 'clock': Clock(**s['clock'])})


def thaw_structure(raw):
    from bishop.v2.types import Level, Event, Clock
    from bishop.v2.structure import StructureResult
    return StructureResult((), tuple(Level(**x) for x in raw['levels']), (),
        tuple(Event(**{**e, 'clock': Clock(**e['clock'])}) for e in raw['events']), ())


def historical_bias(pair, h1, now, config, memo):
    """Use the live KK projection on a physical prefix, never today's DB bias."""
    from slk import live, candles
    from slk.bishop_paper import confirmed_web_biases
    from bishop.v2.types import stable_id
    if h1.empty or h1.index[0] > now - timedelta(days=live.HISTORY_DAYS-4):
        return []  # insufficient live-equivalent higher-timeframe warmup
    h1 = h1[(h1.index + timedelta(hours=1) <= now) &
            (h1.index >= now - timedelta(days=live.HISTORY_DAYS))]
    with candles.market(pair):
        rows = live.pair_state(pair, h1, now, live.state_stories(config['stories'], config['cfg']), config['cfg'], memo)
    for row in rows:
        row['id'] = stable_id('reconstructed_kk', pair, row['story'], str(row['tap_time']), row['side'])
    rows.sort(key=lambda r: str(r.get('confirm_time') or r['tap_time']), reverse=True)
    return confirmed_web_biases(rows, config, now)


def detect(feed, now, later=False):
    from bishop.v2.engine import run
    from bishop.v2.types import StrategyPolicy
    from bishop.v2.simulation import Costs
    policy = StrategyPolicy(source_profile='bishop_confirmation', entry_tfs=('H4', 'H3', 'H2', 'H1'), research_later_kl_irl=later)
    # Only setups available NOW can be issued. A later discovery cannot backfill
    # an earlier signal, even if that signal would have won.
    result = run(prefix(feed, now, 35), as_of=now, scan_start=now, policy=policy,
                 costs=Costs(), include_diagnostics=True, compact_story_diagnostics=True,
                 entry_gate=lambda *_: 'REPLAY_DETECTION_ONLY')
    return result, policy


def select(setups, stories, policy, mode, active=0, gate=None):
    """Same source ambiguity/dedup/ranking rules; persistent per-market cap."""
    from bishop.v2.engine import _ambiguous_execution_groups, _owner_context_blocked, _opportunity_key
    from bishop.v2.types import Order, stable_id
    from types import SimpleNamespace
    candidates = [s for s in setups if gate is None or gate(s) is None]
    owners = {s['id']: SimpleNamespace(details=s['details']) for s in stories}
    ambiguous = _ambiguous_execution_groups(candidates, owners)
    out = []; seen = set(); rejected = Counter()
    for s in sorted(candidates, key=lambda s: (s.available_at, policy.entry_tfs.index(s.tf), s.id)):
        if s.status != 'ELIGIBLE': continue
        if _owner_context_blocked(s, owners[s.story_id]): rejected['COUNTERWEEKLY'] += 1; continue
        if _opportunity_key(s) in ambiguous: rejected['AMBIGUOUS_PLAN_OR_LEVEL'] += 1; continue
        key = stable_id('economic_signal', s.instrument, s.tf, s.side, s.model, s.level_id,
                        s.available_at, s.entry_ticks, s.stop_ticks, s.target_ticks, s.order_type, s.expires_at)
        if key in seen: continue
        if active + len(out) >= 10: rejected['EXPOSURE_CAP'] += 1; continue
        seen.add(key)
        order = Order(id=stable_id('year_order', VERSION, mode, key), setup_id=s.id,
            instrument=s.instrument, tf=s.tf, model=s.model, side=s.side, kind=s.order_type,
            clock=s.clock, entry_ticks=s.entry_ticks, stop_ticks=s.stop_ticks,
            target_ticks=s.target_ticks, expires_at=s.expires_at,
            details={'story_id': s.story_id, 'policy_id': policy.id, 'economic_signal_id': key})
        out.append((order, s))
    return out, dict(rejected)


def advance(book, known, now, instrument, biases, events):
    """Only already-observed execution can release capacity for this decision."""
    from bishop.v2.research_stop_simulation import simulate, Costs
    from bishop.v2.types import jsonable, utc
    for row in book.values():
        if row.get('observation', {}).get('outcome') in TERMINAL: continue
        o = row['order']; actions = row['actions']; existing = {(a['available_at'], a['reason']) for a in actions}
        for e in events.get(row['mode'], []):
            at = e['clock']['available_at']
            if (e['reference_id'] == o.details.get('story_id') and o.available_at <= utc(at) <= now and
                (e['kind'] in ('STORY_INVALIDATED','STORY_DESTINATION_REACHED','STORY_CANCELLED','STORY_FLIPPED') or
                 e.get('details', {}).get('pending_action') == 'CANCEL_DEPENDENT')):
                # Publication may be old when a rolling detector first sees it.
                # Cancel at first observation NOW, never backdate execution.
                if not any(a['reason'] == e['kind'] for a in actions):
                    actions.append(dict(order_id=o.id, kind='CANCEL', available_at=now.isoformat(), reason=e['kind']))
        parent = row.get('bias')
        if parent and not any(b['id'] == parent['id'] and b['side'] == parent['side'] for b in biases):
            at = now.isoformat(); reason = 'WEB_BIAS_NO_LONGER_ELIGIBLE'
            if (at, reason) not in existing:
                actions.append(dict(order_id=o.id, kind='CANCEL', available_at=at, reason=reason))
        result = simulate((o,), known, instrument, Costs(), now, actions, calendar=instrument.calendar_id)
        row['observation'] = jsonable(result['observations'][0])
        row['closed_at'] = next((e.available_at.isoformat() for e in reversed(result['events'])
            if e.kind.startswith('POSITION_') and row['observation']['outcome'] in ('WIN','LOSS','BREAK_EVEN')), None)


def add_order(book, order, setup, mode, bias=None, proof=None, source=None):
    from bishop.v2.types import jsonable
    if order.id in book: return
    book[order.id] = {'order': order, 'setup': jsonable(setup), 'mode': mode, 'bias': bias,
        'stop_proof': proof, 'source_order_id': source, 'actions': [],
        'observation': {'outcome': 'OPEN', 'status': 'PENDING', 'net_r': None}}


def enroll_rr(book, order, setup, frames, inst, mode, bias=None, proof=None):
    from slk.bishop_rr import logical_stop
    from bishop.v2.types import jsonable
    proof = proof or logical_stop(jsonable(setup), frames[setup.tf], inst)
    if proof['status'] != 'READY': return False
    risk = abs(order.entry_ticks - proof['stop_ticks']); sign = 1 if order.side == 'BUY' else -1
    for rr in (1, 2, 3):
        variant = replace(order, id=order.id + f'_r{rr}', stop_ticks=proof['stop_ticks'],
                          target_ticks=order.entry_ticks + sign * risk * rr)
        add_order(book, variant, setup, mode + f'_{rr}R', bias, proof, order.id)
    return True


def decision(feed, h1, now, start, config, state, memo):
    from bishop.v2.types import utc, jsonable
    from bishop.v2.aggregation import aggregate
    from slk.bishop_paper import web_bias_gate
    from slk.bishop_flow import recognize, merge
    known = prefix(feed, now)['bars']
    assert all(b.available_at <= now for b in known)
    biases = historical_bias(feed['instrument'].symbol, h1, now, config, memo)
    base, policy = detect(feed, now)
    # Production recognition skips detector work without an eligible KK bias.
    # It cannot admit a plan in that state; existing positions still advance.
    research, research_policy = detect(feed, now, later=True) if biases else ({'story_events': [], 'setups': [], 'stories': []}, policy)
    structures = {tf: thaw_structure(raw) for tf, raw in base['diagnostics']['structures'].items()}
    h4 = thaw_structure(research['diagnostics']['structures']['H4']) if biases else None
    events = {m: base['story_events'] if not m.startswith('recognition') else research['story_events']
              for m in (*MODES, 'kk_aligned_1R','kk_aligned_2R','kk_aligned_3R','recognition_1R','recognition_2R','recognition_3R')}
    execution = tuple(b for h in known for b in feed.get('minute_evidence', {}).get(h.start, (h,)))
    advance(state['book'], execution, now, feed['instrument'], biases, events)
    frames = {tf: aggregate(prefix(feed, now, 35)['bars'], tf, feed['instrument'], now,
                          calendar=feed['instrument'].calendar_id)['bars'] for tf in ('H4','H3','H2','H1')} if biases else {}
    setups = [thaw_setup(s) for s in base['setups'] if utc(s['clock']['available_at']) == now]
    emitted = []
    for mode in ('standalone', 'kk_aligned'):
        proofs = {}; gate = web_bias_gate(biases, proofs)
        from slk.bishop_capacity import occupies
        active = sum(occupies(r, execution, now) for r in state['book'].values() if r['mode'] == mode)
        orders, rejected = select(setups, base['stories'], policy, mode, active,
                                  (lambda s: gate(s, structures)) if mode == 'kk_aligned' else None)
        state['rejections'].update({mode + ':' + k: v for k, v in rejected.items()})
        for o, s in orders:
            bias = proofs.get(s.id, {}).get('bias')
            add_order(state['book'], o, s, mode, bias)
            emitted.append(jsonable(o))
            if mode == 'kk_aligned' and not enroll_rr(state['book'], o, s, frames, feed['instrument'], mode, bias):
                state['rejections']['kk_aligned:STOP_UNRESOLVED'] += 1
    flow = recognize(frames, h4, biases, research_policy, now, max(start, now-timedelta(days=7)),
                     research['setups'], feed['instrument'].calendar_id, feed['instrument']) if biases else {
                         'version': 'closed_break_later_liquidity_v1', 'as_of': now.isoformat(), 'flows': [], 'rejected_breaks': [],
                         'note': 'Recognition study only; no order, fill or profitability claim. Later approach geometry is experimental.'}
    flow = merge(state.get('flow'), flow); state['flow'] = flow
    rsetups = {s['id']: thaw_setup(s) for s in research['setups']}
    proposed = []; metadata = {}
    for row in flow['flows']:
        if row['status'] != 'CONFIRMED_PLAN' or row['id'] in state['seen_flows']: continue
        state['seen_flows'].add(row['id'])
        for plan in row['plans']:
            if utc(plan['at']) != now or plan['engine_status'] != 'ELIGIBLE' or plan['stop_proof']['status'] != 'READY': continue
            s = rsetups[plan['setup_id']]
            # A new research order is explicitly defined for the study. It keeps
            # the confirmation's original entry/type/expiry, with the study SL.
            s = replace(s, stop_ticks=plan['stop_proof']['stop_ticks'], target_ticks=plan['targets']['1'])
            proposed.append(s); metadata[s.id] = (row['bias'], plan['stop_proof'])
    # All three exits share ONE admitted entry cohort. Capacity/alternative
    # conflicts are resolved before any future outcome; no best-exit selection.
    orders, rejected = select(proposed, research['stories'], research_policy, 'recognition', 0)
    state['rejections'].update({'recognition:' + k: v for k,v in rejected.items()})
    for o, s in orders:
        bias, proof = metadata[s.id]
        enroll_rr(state['book'], o, s, frames, feed['instrument'], 'recognition', bias, proof)
        emitted.append(jsonable(o))
    # Hash the exact decision input and frozen output for reproducibility.
    audit = {'at': now.isoformat(), 'last_input_close': known[-1].available_at.isoformat() if known else None,
             'input_hash': base['input']['prefix'], 'biases': biases, 'orders': emitted}
    state['audit'].append(audit)
    return audit


def dataframe(feed):
    import pandas as pd
    tick = float(feed['instrument'].tick_size)
    return pd.DataFrame([[b.open_ticks*tick,b.high_ticks*tick,b.low_ticks*tick,b.close_ticks*tick] for b in feed['bars']],
        index=pd.DatetimeIndex([b.start for b in feed['bars']]), columns=['open','high','low','close'])


def new_state():
    return {'book': {}, 'flow': None, 'seen_flows': set(), 'rejections': Counter(), 'audit': []}


def replay(feed, config, start, end, state=None, limit=None, checkpoint=None):
    from bishop.v2.types import utc
    start, end = utc(start), utc(end); state = state or new_state(); memo = {}; h1 = dataframe(feed)
    # Advance at every observed H1 close, including quiet hours. Missing hours
    # remain gaps in execution/context; never manufacture candles.
    clocks = sorted({b.available_at for b in feed['bars'] if start <= b.available_at <= end and b.complete})
    if state['audit']: clocks = [c for c in clocks if c > utc(state['audit'][-1]['at'])]
    if limit is not None: clocks = clocks[:limit]
    began = time.monotonic()
    for i, now in enumerate(clocks):
        decision(feed, h1, now, start, config, state, memo)
        if checkpoint and (i % 24 == 0 or i == len(clocks)-1):
            dump(checkpoint, state)
            print(json.dumps({'pair':feed['instrument'].symbol,'clock':now.isoformat(),'hours':i+1,
                              'seconds':round(time.monotonic()-began,2),'orders':len(state['book'])}), flush=True)
    # Outcomes at the cutoff use only the last observed prefix, and cannot
    # feed into decisions already frozen above.
    return state


def thaw_state(raw):
    from slk.bishop_paper import thaw_order
    for r in raw['book'].values(): r['order'] = thaw_order(r['order'])
    raw['seen_flows'] = set(raw['seen_flows']); raw['rejections'] = Counter(raw['rejections'])
    return raw


def feed_file(path):
    from bishop.v2.types import Instrument, Bar
    d = load(path)
    return {'instrument':Instrument(**d['instrument']), 'bars':tuple(Bar(**{k:v for k,v in b.items() if k != 'id'}) for b in d['bars']),
            'manifest': d['manifest'], 'hashes': {}}


def summarize(rows):
    closed = [r for r in rows if r['observation']['outcome'] in ('WIN','LOSS','BREAK_EVEN') and r['observation'].get('net_r') is not None]
    values = [float(r['observation']['net_r']) for r in closed]
    gains = sum(max(v,0) for v in values); losses = -sum(min(v,0) for v in values)
    batches = Counter()
    for r in closed: batches[r.get('closed_at') or ''] += float(r['observation']['net_r'])
    eq = peak = dd = 0
    for at in sorted(batches): eq += batches[at]; peak = max(eq, peak); dd = max(dd, peak-eq)
    counts = Counter(r['observation']['outcome'] for r in rows)
    return {'orders':len(rows),'outcomes':dict(counts),'resolved':len(closed),
            'win_rate':100*counts['WIN']/len(closed) if closed else None,
            'total_R':sum(values),'expectancy_R':sum(values)/len(values) if values else None,
            'profit_factor':gains/losses if losses else None,'closed_drawdown_R':dd,
            'note':'Gross zero-cost R; closed-trade drawdown excludes floating losses. Unknown/open excluded, never counted as wins.'}


def report(state, feed, status, start, end):
    from bishop.v2.types import jsonable
    rows = list(state['book'].values()); modes = sorted({r['mode'] for r in rows} | {'standalone','kk_aligned','kk_aligned_1R','kk_aligned_2R','kk_aligned_3R','recognition_1R','recognition_2R','recognition_3R'})
    paired = {}
    for family in ('kk_aligned','recognition'):
        groups = {}
        for r in rows:
            if r['mode'].startswith(family+'_'): groups.setdefault(r['source_order_id'], []).append(r)
        resolved = [g for g in groups.values() if len(g)==3 and all(x['observation']['outcome'] in ('WIN','LOSS','BREAK_EVEN') for x in g)]
        paired[family] = {'cohort':len(groups),'all_exits_resolved':len(resolved),
            'total_R':{f'{rr}R':sum(float(x['observation']['net_r']) for g in resolved for x in g if x['mode']==family+f'_{rr}R') for rr in (1,2,3)}}
    # Cost hurdle, not an invented broker execution model: same gross fills,
    # minus a declared 1/2-pip round-trip cost per resolved trade.
    sensitivity = {}
    for mode in modes:
        resolved = [r for r in rows if r['mode']==mode and r['observation'].get('net_r') is not None]
        sensitivity[mode] = {str(pips)+'_pip_round_trip':sum(float(r['observation']['net_r']) -
            float(feed['instrument'].unit_ticks(Decimal(pips)))/abs(r['order'].entry_ticks-r['order'].stop_ticks) for r in resolved) for pips in (1,2)}
    return jsonable({'version':VERSION,'status':status,'pair':feed['instrument'].symbol,'start':start,'end':end,
        'last_decision':state['audit'][-1]['at'] if state['audit'] else None,'decision_count':len(state['audit']),
        'models':{m:summarize([r for r in rows if r['mode']==m]) for m in modes},'paired':paired,
        'by_confirmation':{m:{k:summarize([r for r in rows if r['mode']==m and r['order'].model==k]) for k in sorted({r['order'].model for r in rows if r['mode']==m})} for m in modes},
        'by_entry_timeframe':{m:{k:summarize([r for r in rows if r['mode']==m and r['order'].tf==k]) for k in sorted({r['order'].tf for r in rows if r['mode']==m})} for m in modes},
        'cost_hurdle_only':sensitivity,'rejections':dict(state['rejections']),
        'limitations':['Current rules/preferences replayed historically, not archived past web decisions or an out-of-sample validation.',
            'Hourly closed OHLC; simultaneous SL/TP and uncertain fills remain CENSORED. No finer intrabar path assumed.',
            'Two hypothetical round-trip cost deductions do not model spread-dependent fills or historical commissions.',
            'Recognition exits are independent full-exit study alternatives, not three simultaneous allocations or an account equity forecast.',
            'Original model means current baseline rules without the KK gate; older pre-correction software is not reconstructed.']})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--feed', required=True); p.add_argument('--config', required=True)
    p.add_argument('--start', required=True); p.add_argument('--end', required=True)
    p.add_argument('--out', required=True); p.add_argument('--limit', type=int); p.add_argument('--resume')
    args = p.parse_args(); feed = feed_file(args.feed); config = load(args.config)
    root = Path(args.out); root.mkdir(parents=True,exist_ok=True)
    state = thaw_state(load(args.resume)) if args.resume else new_state()
    try:
        state = replay(feed, config, args.start, args.end, state, args.limit, root/'checkpoint.json.gz')
        status = 'PILOT_ONLY' if args.limit else 'COMPLETED'
    except Exception as exc:
        dump(root/'checkpoint.json.gz', state)
        dump(root/'failure.json', {'error_type':type(exc).__name__,'message':str(exc)[:300]})
        raise
    dump(root/'summary.json', report(state, feed, status, args.start, args.end))


if __name__ == '__main__': main()

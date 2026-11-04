"""Rolling closed-candle bias replay and bounded paper-system backtest.

Offline saved IC Markets data only. No broker orders, credentials, database or
Telegram calls. Forward movement is a diagnostic, not mentor accuracy or P&L.
"""
import argparse
from collections import Counter
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import time

from bishop import settings
from bishop.bias_snapshot import snapshot, changes
from bishop.v2.aggregation import aggregate
from bishop.v2.engine import run
from bishop.v2.feed import load_feed
from bishop.v2.simulation import Costs, simulate
from bishop.v2.types import utc, jsonable, Order, Clock


def settled_summary(observations, events):
    counts = Counter(o['outcome'] for o in observations)
    closed = [o for o in observations if o.get('net_r') is not None]
    closing = {}
    for e in events:
        if e['kind'] in ('POSITION_STOPPED', 'POSITION_TARGET', 'POSITION_MANUAL_CLOSE'):
            closing[e['reference_id']] = e['clock']['available_at']
    pnl = [Decimal(o['net_r']) for o in closed]
    equity = sum(pnl, Decimal(0))
    boundaries = {}
    for o in closed:
        boundary = closing.get(o['id'])
        if boundary is not None:
            boundaries[boundary] = boundaries.get(boundary, Decimal(0)) + Decimal(o['net_r'])
    running = peak = drawdown = Decimal(0)
    for boundary in sorted(boundaries):
        running += boundaries[boundary]
        peak = max(peak, running)
        drawdown = max(drawdown, peak-running)
    drawdown_known = all(o['id'] in closing for o in closed)
    gross_gain = sum((v for v in pnl if v > 0), Decimal(0))
    gross_loss = -sum((v for v in pnl if v < 0), Decimal(0))
    settled_counts = Counter(o['outcome'] for o in closed)
    decisions = settled_counts['WIN'] + settled_counts['LOSS']
    return dict(orders=len(observations), outcomes=dict(counts), settled=len(closed),
                filled=sum(o.get('fill_ticks') is not None for o in observations),
                censored=sum(bool(o.get('censor_reason')) for o in observations),
                censor_reasons=dict(Counter(o['censor_reason'] for o in observations if o.get('censor_reason'))),
                settled_net_r=str(equity), settled_close_boundary_drawdown_r=str(drawdown) if drawdown_known else None,
                settled_mean_r=str(equity/len(closed)) if closed else None,
                resolved_win_rate=settled_counts['WIN']/decisions if decisions else None,
                settled_profit_factor=str(gross_gain/gross_loss) if gross_loss else None,
                qualification='Settled trades only; open/censored/expired orders are separate. Drawdown groups simultaneous closing boundaries; intrabar and mark-to-market drawdown are unknown. No combined multi-pair portfolio claim.')


def assert_causal(result, clock):
    for row in (*result.get('stories', []), *result.get('setups', []), *result.get('orders', []),
                *result.get('story_events', []), *result.get('execution_events', [])):
        assert utc(row['clock']['available_at']) <= clock, 'Future record leaked into replay'
    stories = {s['id']: s for s in result.get('stories', [])}
    for setup in result.get('setups', []):
        assert utc(stories[setup['story_id']]['clock']['available_at']) <= utc(setup['clock']['available_at'])
    for context in result['structural_context'].values():
        for event in context['recent_breaks']:
            assert utc(event['clock']['available_at']) <= clock
            reference = event.get('details', {}).get('reference_available_at')
            if reference:
                assert utc(reference) <= clock


def future_probe(path, manifest, clock, expected, policy):
    """Changing every not-yet-available price must leave the past bias unchanged."""
    import csv, io
    with gzip.open(path, 'rt', newline='') as f:
        source = list(csv.DictReader(f))
    changed = 0
    for row in source:
        if utc(row['time']) >= clock:
            for key in ('open', 'high', 'low', 'close'):
                row[key] = format(Decimal(row[key])*3, 'f')
            changed += 1
    assert changed, 'Future-leak probe requires withheld future candles'
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=source[0].keys(), lineterminator='\n')
    writer.writeheader(); writer.writerows(source)
    raw = gzip.compress(stream.getvalue().encode(), mtime=0)
    altered = {**manifest, 'sha256': sha256(raw).hexdigest()}
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)/'adversarial_future_NOT_MARKET_DATA.csv.gz'
        target.write_bytes(raw)
        result = run(target, altered, as_of=clock, policy=policy, costs=Costs(), bias_only=True)
        assert snapshot(result)['rows'] == expected['rows'], 'Future prices changed past bias'
    return dict(status='PASS', future_bars_changed=changed, tested_at=clock.isoformat())


def rolling_bias(path, manifest, end, start, out):
    policy = settings.strategy_policy(settings.DEFAULTS)
    feed = load_feed(path, manifest, end)
    h4 = aggregate(feed['bars'], 'H4', feed['instrument'], end, calendar=manifest['calendar_id'])['bars']
    clocks = [start] + [b.end for b in h4 if start < b.end <= end]
    if not clocks or clocks[-1] != end:
        clocks.append(end)
    previous = None; timeline = []; transitions = []; first = None
    for clock in clocks:
        result = run(path, manifest, as_of=clock, policy=policy, costs=Costs(), bias_only=True)
        assert_causal(result, clock)
        view = snapshot(result)
        if first is None:
            first = view
        for change in changes(previous, view):
            row = next(r for r in view['rows'] if r['tf'] == change['tf'])
            context = row['structural_context']
            change['parent_ranges'] = context['active_root_ranges']
            # Forward returns are measured AFTER the recorded decision; never used to select it.
            at_bar = next(b for b in reversed(feed['bars']) if b.end <= clock)
            change['forward_h4_movement'] = []
            future = [b for b in h4 if b.end > clock]
            for horizon in (1, 3, 6):
                if len(future) >= horizon and change['side'] in ('BUY', 'SELL'):
                    delta = future[horizon-1].close_ticks - at_bar.close_ticks
                    signed = delta if change['side'] == 'BUY' else -delta
                    change['forward_h4_movement'].append(dict(bars=horizon, direction_adjusted_ticks=signed,
                                                             status='ALIGNED' if signed>0 else 'OPPOSED' if signed<0 else 'FLAT'))
            transitions.append(change)
        timeline.append(view)
        previous = view
    probe = future_probe(path, manifest, utc(first['as_of']), first, policy)
    output = dict(scope='CLOSED_H4_BOUNDARY_WALK_FORWARD', start=start.isoformat(), end=end.isoformat(),
                  checkpoints=len(timeline), future_price_invariance=probe,
                  state_transitions=len(transitions), confirmed_direction_flips=sum(c['side'] in ('BUY','SELL') and c['previous_side'] in ('BUY','SELL') and c['side']!=c['previous_side'] for c in transitions), changes_by_tf=dict(Counter(r['tf'] for r in transitions)),
                  initial_states_included=True, timeline=timeline, transitions=transitions,
                  mentor_comparison='Documented source snapshot agreement is separate; no live Bishop commentary feed is available.',
                  qualification='M/W/D/H4 context can update only on closed bars. Forward movement is not entry P&L or proof of a parent-story reversal.')
    (out/'rolling_bias.json').write_text(json.dumps(output, indent=2)+'\n')
    return output


def paper_backtest(path, manifest, end, start, out, timeline, risks=('owner_fixed11','context_liquidity')):
    feed = load_feed(path, manifest, end, start-timedelta(days=35))
    instrument = feed['instrument']
    # Explicit H1-input pilot. No invented M5/M15/M30/M45 confirmations.
    policy = replace(settings.strategy_policy(settings.DEFAULTS), entry_tfs=('H4','H3','H2','H1'))
    reports = []
    stress = Costs(spread_ticks=instrument.unit_ticks('1'), entry_slippage_ticks=instrument.unit_ticks('0.1'),
                   stop_slippage_ticks=instrument.unit_ticks('0.2'), commission_ticks=instrument.unit_ticks('0.5'))
    for risk in risks:
        began=time.monotonic()
        print(manifest['symbol'],risk,'paper engine started',flush=True)
        current = replace(policy, risk_profile=risk)
        result = run(path, manifest, as_of=end, history_start=start-timedelta(days=35),
                     scan_start=start, policy=current, costs=Costs(), max_open_orders=10)
        assert_causal(result, end)
        # Freeze the engine's prospective capped selections before cost stress.
        orders = tuple(Order(**{**r, 'clock': Clock(**r['clock'])}) for r in result['orders'])
        stressed = jsonable(simulate(orders, feed['bars'], instrument, stress, end,
                                    result['actions'], calendar=manifest['calendar_id']))
        setups = {s['id']:s for s in result['setups']}
        trade_rows = []
        observations = {o['id']:o for o in result['observations']}
        for order in result['orders']:
            observation = observations[order['id']]
            known = [v for v in timeline if utc(v['as_of']) <= utc(order['clock']['available_at'])]
            directions = {r['tf']:r['side'] for r in known[-1]['rows']} if known else {}
            trade_rows.append(dict(order=order, observation=observation,
                                   structural_directions_known_at_entry=directions,
                                   setup=setups[order['setup_id']]))
        report = dict(risk_profile=risk, status=result['status'], policy=result['policy'],
                      period=dict(history_start=(start-timedelta(days=35)).isoformat(),
                                  scan_start=start.isoformat(), as_of=end.isoformat()),
                      input=result['input'], coverage=result['coverage'],
                      baseline_zero_cost=settled_summary(result['observations'],result['execution_events']),
                      frozen_orders_cost_stress=settled_summary(stressed['observations'],stressed['events']),
                      cost_stress=jsonable(stress),
                      cost_qualification='Illustrative 1-pip spread,0.1 entry/0.2 stop slippage,0.5 commission stress; not broker-measured. Fixed baseline selections, not a cost-reselected portfolio.',
                      selection=result['selection'], summary=result['summary'], trades=trade_rows,
                      elapsed_seconds=time.monotonic()-began,
                      loss_assessment='Loss is not labeled mentor error. Review pre-entry model/context/protection; unresolved intrabar paths remain censored.',
                      limitations=['Two FX pairs, separate capped books; no pooled portfolio return.',
                                   'Only H1/H2/H3/H4 entries supported by H1 input; lower entry timeframes untested.',
                                   '35-day pre-window warmup limits monthly context; complete-bar coverage is retained.',
                                   'H1 execution can leave stop/target ordering unresolved; no favorable path is assumed.'])
        (out/(risk+'.json')).write_text(json.dumps(report,indent=2)+'\n')
        reports.append({k:report[k] for k in ('risk_profile','status','baseline_zero_cost','frozen_orders_cost_stress','summary')})
        print(manifest['symbol'],risk,json.dumps(report['baseline_zero_cost']),flush=True)
    return reports


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',required=True);p.add_argument('--pair',required=True);p.add_argument('--out',required=True)
    p.add_argument('--days',type=int,default=28)
    p.add_argument('--stage',choices=('all','paper'),default='all')
    p.add_argument('--rolling',help='Completed saved rolling-bias JSON for paper-only replay')
    p.add_argument('--risk',choices=('owner_fixed11','context_liquidity'))
    a=p.parse_args()
    if not 7 <= a.days <= 90: raise ValueError('Bounded 7–90 day evaluation required')
    candidates=list(Path(a.inputs).rglob(a.pair+'.csv.manifest.json'))
    if len(candidates)!=1: raise ValueError('Exactly one frozen current-data manifest required')
    manifest=json.loads(candidates[0].read_text())
    path=candidates[0].with_name(a.pair+'.csv.gz')
    assert manifest['symbol']==a.pair and manifest['venue']=='ICMARKETS' and manifest['base_tf']=='H1'
    end=utc(manifest['requested_end']);start=end-timedelta(days=a.days)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    if a.stage=='paper':
        if not a.rolling:raise ValueError('Paper-only replay requires saved rolling bias')
        rolling=json.loads(Path(a.rolling).read_text())
        if utc(rolling['start'])>start or utc(rolling['end'])!=end:
            raise ValueError('Saved bias replay window mismatch')
        if any(v['instrument']!=a.pair for v in rolling['timeline']):
            raise ValueError('Saved bias replay instrument mismatch')
    else:
        rolling=rolling_bias(path,manifest,end,start,out)
    risks=(a.risk,) if a.risk else ('owner_fixed11','context_liquidity')
    paper=paper_backtest(path,manifest,end,start,out,rolling['timeline'],risks)
    summary=dict(pair=a.pair,as_of=end.isoformat(),evaluation_days=a.days,
                 input_sha256=sha256(path.read_bytes()).hexdigest(),
                 rolling_source_period={k:rolling[k] for k in ('start','end')},rolling_bias={k:rolling[k] for k in ('checkpoints','future_price_invariance','changes_by_tf','confirmed_direction_flips')},paper=paper,
                 teacher_acceptance='NOT_ESTABLISHED_BY_MARKET_BACKTEST')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()

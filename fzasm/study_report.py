"""Cohort reports for independent entry/stop/target counterfactuals.

Months are setup months in UTC, not exit months. Never sum model alternatives.
Only explicitly complete coverage permits zero-signal rows.
"""
from pathlib import Path
import math
import pandas as pd

TARGETS = ('1R', '2R', '3R', '4R', 'ASIAN_EXTREME', 'FZ_RESEARCH')
STOPS = ('sweep_exact', 'sweep_plus_3p')
STATUSES = ('CLOSED', 'UNKNOWN', 'UNFILLED', 'UNAVAILABLE', 'OPEN', 'PENDING')
DIMENSIONS = ['symbol', 'entry_policy', 'stop_variant', 'target']
METRICS = ['setups', 'closed', 'wins', 'losses', 'flat', 'unknown', 'unfilled',
           'unavailable', 'open', 'pending', 'gross_resolved_r', 'gross_profit_r', 'gross_loss_r']
COLUMNS = ['signal_id', 'symbol', 'entry_policy', 'stop_variant', 'target',
           'timestamp', 'status', 'result_r', 'exit_time']


def _group(symbol):
    if symbol.endswith('JPY'):
        return 'JPY'
    return 'Gold' if symbol in ('XAUUSD', 'GOLD') else 'Majors'


def _ratios(frame):
    if frame.empty:
        return frame.assign(win_rate_pct=pd.Series(dtype=float),
                            expectancy_r=pd.Series(dtype=float),
                            profit_factor=pd.Series(dtype=float))
    frame = frame.copy()
    frame['win_rate_pct'] = frame['wins'].div(frame['closed'].replace(0, float('nan'))) * 100
    frame['expectancy_r'] = frame['gross_resolved_r'].div(frame['closed'].replace(0, float('nan')))
    # Undefined with no losing trades; do not invent a finite profit factor.
    frame['profit_factor'] = frame['gross_profit_r'].div(frame['gross_loss_r'].replace(0, float('nan')))
    return frame


def _rollup(monthly, keys):
    if monthly.empty:
        return _ratios(pd.DataFrame(columns=keys + METRICS + ['coverage_status']))
    result = monthly.groupby(keys, dropna=False)[METRICS].sum().reset_index()
    coverage = monthly.groupby(keys, dropna=False)['coverage_status'].agg(
        lambda values: 'complete' if all(v == 'complete' for v in values) else 'partial_or_unverified').reset_index()
    return _ratios(result.merge(coverage, on=keys, validate='one_to_one'))


def write_study_report(records, out_dir, coverage=None, stop_variants=None):
    """Write CSVs plus STUDY_REPORT.md; return the six aggregate DataFrames.

    Coverage rows need symbol, entry_policy, month, status. 'complete' means
    the requested replay for that pair/model/month completed, not that every
    minute exists. Input-source gaps must remain explicit in outcome reasons.
    Non-complete coverage is preserved in coverage.csv, without zero filling.
    """
    expected_stops = tuple(stop_variants) if stop_variants is not None else STOPS
    if not expected_stops or len(set(expected_stops)) != len(expected_stops) or any(s not in STOPS for s in expected_stops):
        raise ValueError('Invalid requested stop variants')
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = [dict(r) for r in records]
    seen = set()
    for row in rows:
        for key in COLUMNS[:-1]:
            if key not in row:
                raise ValueError(f'Missing outcome field: {key}')
        if row['target'] not in TARGETS or row['stop_variant'] not in expected_stops:
            raise ValueError('Unknown target or stop scenario')
        if row['status'] not in STATUSES:
            raise ValueError('Unknown outcome status')
        value = row['result_r']
        if row['status'] == 'CLOSED':
            if value is None or not math.isfinite(float(value)):
                raise ValueError('Closed outcome requires a finite R result')
            row['result_r'] = float(value)
        elif value is not None and not pd.isna(value):
            raise ValueError('Unresolved/unfilled/unavailable outcome cannot have an R result')
        else:
            row['result_r'] = None
        row['timestamp'] = pd.Timestamp(row['timestamp'])
        if row['timestamp'].tzinfo is None:
            raise ValueError('Setup timestamp must be timezone-aware')
        row['timestamp'] = row['timestamp'].tz_convert('UTC')
        row['month'] = row['timestamp'].strftime('%Y-%m')
        identity = tuple(row[key] for key in ['signal_id'] + DIMENSIONS)
        if identity in seen:
            raise ValueError('Duplicate signal/scenario outcome')
        seen.add(identity)
    outcomes = pd.DataFrame(rows) if rows else pd.DataFrame(columns=COLUMNS + ['month'])
    outcomes.to_csv(out / 'outcomes.csv', index=False)

    covered = {}
    coverage_rows = [dict(c) for c in (coverage or [])]
    for c in coverage_rows:
        # Parse month to reject malformed strings; normalize without inventing dates.
        month = pd.Period(c['month'], freq='M').strftime('%Y-%m')
        key = (c['symbol'], c['entry_policy'], month)
        if key in covered and covered[key] != c['status']:
            raise ValueError('Conflicting coverage status')
        covered[key] = c['status']
    pd.DataFrame(coverage_rows, columns=list(dict.fromkeys(
        ['symbol', 'entry_policy', 'month', 'status'] + [k for c in coverage_rows for k in c]))).to_csv(out / 'coverage.csv', index=False)

    monthly_rows = []
    if not outcomes.empty:
        for keys, cohort in outcomes.groupby(['month'] + DIMENSIONS, sort=True):
            month, symbol, policy, stop, target = keys
            resolved = cohort.loc[cohort.status == 'CLOSED', 'result_r'].astype(float)
            counts = cohort.status.value_counts()
            monthly_rows.append(dict(month=month, symbol=symbol, entry_policy=policy,
                stop_variant=stop, target=target, asset_group=_group(symbol),
                setups=len(cohort), closed=len(resolved), wins=int((resolved > 0).sum()),
                losses=int((resolved < 0).sum()), flat=int((resolved == 0).sum()),
                unknown=int(counts.get('UNKNOWN', 0)), unfilled=int(counts.get('UNFILLED', 0)),
                unavailable=int(counts.get('UNAVAILABLE', 0)),
                open=int(counts.get('OPEN', 0)), pending=int(counts.get('PENDING', 0)),
                gross_resolved_r=float(resolved.sum()), gross_profit_r=float(resolved[resolved > 0].sum()),
                gross_loss_r=float(-resolved[resolved < 0].sum()),
                coverage_status=covered.get((symbol, policy, month), 'unverified')))
    existing = {tuple(r[k] for k in ['month'] + DIMENSIONS) for r in monthly_rows}
    for (symbol, policy, month), status in covered.items():
        if status != 'complete':
            continue
        # A month with any outcomes must have every scenario represented for every
        # signal, rather than silently treating a dropped variant as zero trades.
        selected = [r for r in rows if r['symbol'] == symbol and r['entry_policy'] == policy and r['month'] == month]
        if selected:
            signals = {r['signal_id'] for r in selected}
            for signal in signals:
                scenarios = {(r['stop_variant'], r['target']) for r in selected if r['signal_id'] == signal}
                if scenarios != {(s, t) for s in expected_stops for t in TARGETS}:
                    raise ValueError('Complete coverage requires all stop/target outcomes for each signal')
        for stop in expected_stops:
            for target in TARGETS:
                key = (month, symbol, policy, stop, target)
                if key not in existing:
                    monthly_rows.append(dict(zip(['month'] + DIMENSIONS, key),
                        asset_group=_group(symbol), coverage_status='complete', **dict.fromkeys(METRICS, 0)))
    monthly = pd.DataFrame(monthly_rows, columns=['month'] + DIMENSIONS + ['asset_group'] + METRICS + ['coverage_status'])
    monthly = _ratios(monthly.sort_values(['month'] + DIMENSIONS).reset_index(drop=True))
    annual_input = monthly.assign(year=monthly['month'].str[:4])
    yearly = _rollup(annual_input, ['year'] + DIMENSIONS + ['asset_group'])
    monthly_groups = _rollup(monthly, ['month', 'asset_group', 'entry_policy', 'stop_variant', 'target'])
    yearly_groups = _rollup(annual_input, ['year', 'asset_group', 'entry_policy', 'stop_variant', 'target'])
    monthly_all = _rollup(monthly, ['month', 'entry_policy', 'stop_variant', 'target'])
    yearly_all = _rollup(annual_input, ['year', 'entry_policy', 'stop_variant', 'target'])
    # A missing requested month/pair must taint the corresponding aggregate even
    # when it has no outcome rows and therefore contributes no invented zeros.
    for (symbol, policy, month), status in covered.items():
        if status == 'complete':
            continue
        if not yearly.empty:
            mask = (yearly.symbol == symbol) & (yearly.entry_policy == policy) & (yearly.year == month[:4])
            yearly.loc[mask, 'coverage_status'] = 'partial_or_unverified'
        if not monthly_groups.empty:
            mask = (monthly_groups.asset_group == _group(symbol)) & (monthly_groups.entry_policy == policy) & (monthly_groups.month == month)
            monthly_groups.loc[mask, 'coverage_status'] = 'partial_or_unverified'
        if not yearly_groups.empty:
            mask = (yearly_groups.asset_group == _group(symbol)) & (yearly_groups.entry_policy == policy) & (yearly_groups.year == month[:4])
            yearly_groups.loc[mask, 'coverage_status'] = 'partial_or_unverified'
        if not monthly_all.empty:
            mask = (monthly_all.entry_policy == policy) & (monthly_all.month == month)
            monthly_all.loc[mask, 'coverage_status'] = 'partial_or_unverified'
        if not yearly_all.empty:
            mask = (yearly_all.entry_policy == policy) & (yearly_all.year == month[:4])
            yearly_all.loc[mask, 'coverage_status'] = 'partial_or_unverified'
    tables = dict(monthly=monthly, yearly=yearly, monthly_groups=monthly_groups,
                  yearly_groups=yearly_groups, monthly_all=monthly_all, yearly_all=yearly_all)
    for name, table in tables.items():
        table.to_csv(out / f'{name}.csv', index=False)
    lines = ['# ASM entry, stop and target study', '',
        'Gross research returns exclude spread, commission, financing and slippage.',
        'Months use setup time in UTC. Unknown, unfilled, unavailable, open and pending outcomes are not wins or zero-return trades.',
        'Win rate = positive resolved outcomes / all resolved outcomes (including flat). Yearly rates use trade counts, not averages of monthly rates.',
        'Each entry/stop/target combination is a separate counterfactual. Do not add their returns together.',
        '**Coverage:** complete means the requested replays completed; partial_or_unverified means some requested work is missing or unverified. Neither certifies uninterrupted market data or a complete calendar year.', '',
        'Files: outcomes.csv, coverage.csv, monthly.csv, yearly.csv, monthly_groups.csv, yearly_groups.csv, monthly_all.csv, yearly_all.csv.', '',
        'Entry labels: h1_av = direct H1 A/V retest; h1_av_m5 = H1 A/V retest gated by M5 change of character; swing_ob = provisional M5 order-block retest; swing_fvg = provisional M5 FVG with overlapping A/V level.', '',
        'Stops: sweep_exact = at the H1 sweep extreme; sweep_plus_3p = three broker-defined pips beyond it. These are independent alternatives on the same signals.', '',
        'ASIAN_EXTREME is the opposite session extreme known when the order was placed, frozen thereafter. FZ_RESEARCH retains the existing half-at-equilibrium / remainder-at-map-target exit with break-even, not a newly verified teacher target rule.', '',
        'Context filters and warmup depend on the run configuration; see manifest.json and the run handoff. M5 interpretations remain provisional. Pending limits expire at 06:00 UTC; filled positions retain the existing 120-hour maximum hold. Source-data gaps stay unknown.', '',
        '## Yearly results across all selected symbols', '',
        'Totals sum independent trade R across selected symbols. They do not model portfolio sizing, exposure limits or compound returns.', '',
        '| Year | Entry | Stop | Target | Coverage | Setups | Closed | Unknown | Unfilled | Unavailable | Open | Pending | Win % | Gross resolved R |',
        '|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in yearly_all.to_dict('records'):
        wr = '—' if pd.isna(row['win_rate_pct']) else f"{row['win_rate_pct']:.2f}"
        lines.append('| ' + ' | '.join(str(row[k]) for k in ['year','entry_policy','stop_variant','target','coverage_status','setups','closed','unknown','unfilled','unavailable','open','pending']) + f" | {wr} | {row['gross_resolved_r']:.4f} |")
    lines.extend(['', '## Yearly results by asset group', '',
        '| Year | Group | Entry | Stop | Target | Coverage | Setups | Closed | Unknown | Unfilled | Unavailable | Open | Pending | Win % | Gross resolved R |',
        '|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|'])
    for row in yearly_groups.to_dict('records'):
        wr = '—' if pd.isna(row['win_rate_pct']) else f"{row['win_rate_pct']:.2f}"
        lines.append('| ' + ' | '.join(str(row[k]) for k in ['year','asset_group','entry_policy','stop_variant','target','coverage_status','setups','closed','unknown','unfilled','unavailable','open','pending']) + f" | {wr} | {row['gross_resolved_r']:.4f} |")
    (out / 'STUDY_REPORT.md').write_text('\n'.join(lines) + '\n')
    return tables

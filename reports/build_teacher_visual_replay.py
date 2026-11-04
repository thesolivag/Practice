"""Build a self-contained visual comparison from frozen source and replay files."""
import base64
import gzip
import json
from pathlib import Path
from bishop.v2.feed import load_feed
from bishop.v2.aggregation import aggregate
from bishop.v2.types import utc
from reports.replay_collected_teacher_examples_v2 import digest

CASES = [
    ('pdf-p13-eurnzd-sell-1', 13, '2026-07-16T00:00:00Z', '2026-07-21T00:00:00Z',
     [1.96156, 1.96472, 1.94902], 'H3 engulf',
     'Daily bearish breakout → H4 breakout with inducement → H3 engulf confirmation.',
     'The screenshot shows a sell plan, with price still above its drawn target. It does not establish a completed winning trade.',
     'The observed H3 candle pair misses strict body engulf by two ticks. The bot found standing-extreme and breakout alternatives; neither verifies the illustrated engulf.'),
    ('pdf-p27-gbpusd-sell-1', 27, '2026-06-23T00:00:00Z', '2026-06-27T00:00:00Z',
     [1.31932, 1.31999, 1.31594], 'H1 breakout',
     'Daily recent bearish breakout → H4 breakout with inducement → H1 breakout confirmation.',
     'The page includes a later trade screenshot showing the downward move. Exact source setup and fill clocks have not been aligned with this feed.',
     'The bot detects sell confirmations on H1, but its candle/level, protective wick and objective differ from the drawing. The actual capped portfolio selected no sell orders; outcomes here test candidates independently.'),
]


def main():
    payload = []
    refined = json.loads(Path('reports/teacher_execution_refinement/gbpusd_refined_execution.json').read_text())
    replacement = {r['order_id']: r['refined'] for r in refined['records']}
    for cid, page, start, end, prices, model, flow, source_note, mismatch in CASES:
        report = json.loads(Path('reports/teacher_isolated_candidates', cid + '.json').read_text())
        trace_path = Path('reports/teacher_later_irl_results', cid, 'research_later_kl_irl.json.gz')
        with gzip.open(trace_path, 'rt') as stream:
            saved = json.load(stream)
        plan = saved['plan']
        if digest(plan['input_path']) != report['input_sha256']:
            raise ValueError('Frozen chart input changed')
        metadata = json.loads(Path(plan['manifest_path']).read_text())
        feed = load_feed(plan['input_path'], metadata, end, start)
        frames = {}
        for tf in sorted(report['plan_counts_by_timeframe']):
            bars = aggregate(feed['bars'], tf, feed['instrument'], end, calendar=metadata['calendar_id'])['bars']
            frames[tf] = [dict(t=b.start.isoformat(), end=b.end.isoformat(), o=b.open_ticks,
                h=b.high_ticks, l=b.low_ticks, c=b.close_ticks) for b in bars]
        plans = []
        for item in report['plans']:
            item = dict(item)
            observations = [replacement.get(o['order_id'], o['observation']) if 'gbpusd' in cid else o['observation']
                            for o in item['selected_orders']]
            item['outcomes'] = [o['outcome'] for o in observations if o]
            item['fills'] = [o['fill_window'] for o in observations if o and o.get('fill_window')]
            item['protection'] = list({(obj[1], obj[2]) for order in item['selected_orders'] for obj in order['protected_objects']})
            plans.append(item)
        plans.sort(key=lambda p: (p['available_at'], p['model'], p['entry_ticks'], str(p['target_ticks'])))
        image = base64.b64encode(Path('/tmp', f'bishop-page-{page}.png').read_bytes()).decode()
        payload.append(dict(id=cid, pair=saved['case']['pair'], teacher_tf=report['teacher_tf'],
            teacher_prices=prices, teacher_model=model, flow=flow, source_note=source_note,
            mismatch=mismatch, image='data:image/png;base64,' + image, frames=frames, plans=plans,
            tick=float(saved['result']['instrument']['tick_size']), input_sha256=report['input_sha256']))
    template = Path('reports/visual_replay/template.html').read_text()
    Path('reports/visual_replay/bishop_examples.html').write_text(template.replace('__PAYLOAD__', json.dumps(payload).replace('</', '<\\/')))
    print('Built two source comparisons; all available timeframe plans included. No detector rerun.')


if __name__ == '__main__':
    main()

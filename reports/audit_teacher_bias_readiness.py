"""Inventory source bias evidence without running detection or inferring bias from trades."""
import hashlib
import json
from pathlib import Path


def audit(path, annotations_path=None):
    raw = Path(path).read_bytes()
    examples = json.loads(raw)['examples']
    annotations = {}
    if annotations_path:
        annotations = {r['case_id']: r for r in json.loads(Path(annotations_path).read_text())['examples']}
    rows = []
    for case in examples:
        source = annotations.get(case['id'], {})
        bias = dict(side=source['side'], tf=source['bias_tf'], reason=source['reason']) if source.get('side') and source.get('bias_tf') else case.get('bias')
        missing = []
        if not bias:
            missing.append('Verified source bias direction, timeframe and supporting chart evidence')
        assessment = source.get('assessment_time') or case.get('setup_time')
        if not assessment:
            missing.append('Verified setup time; chart creation time cannot substitute')
        rows.append(dict(case_id=case['id'], pair=case['pair'],
                         trade_side=case.get('side'), source_bias=bias,
                         setup_time=assessment,
                         status='SOURCE_EVIDENCE_PENDING' if missing else 'READY_FOR_REPLAY_REVIEW',
                         missing=missing, evidence=case.get('evidence', [])))
    return dict(fixture_sha256=hashlib.sha256(raw).hexdigest(),
                qualification='Readiness inventory only; no engine comparison or matching claim.',
                total=len(rows), source_bias_annotated=sum(bool(r['source_bias']) for r in rows),
                examples=rows)


def main():
    result = audit('tests/bishop_examples.json', 'reports/bias_validation/source_annotations.json')
    out = Path('reports/bias_validation')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'source_readiness.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['total']} examples; {result['source_bias_annotated']} source bias annotations. No replay executed.")


if __name__ == '__main__':
    main()

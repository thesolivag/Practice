"""Audit regressions moved to test_fzasm_repaired.py; no expected failures remain.

The original audit at commit 5523560 preserves the seven defect reproductions.
"""
from pathlib import Path
import pandas as pd
import pytest

def test_archived_report_is_preserved():
    p=Path('reports/fzasm_trades.csv')
    if not p.exists():
        pytest.skip('Archived report not installed')
    rows=pd.read_csv(p)
    assert len(rows)==1389
    assert set(rows.entry_model)=={'MODEL_A_CHOCH_RETEST'}

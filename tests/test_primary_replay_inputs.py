"""The declared full-context replay inputs must satisfy their actual loader contract."""
import json
from pathlib import Path
import pytest
from reports.replay_primary_video_case import JOBS


@pytest.mark.parametrize('case,pair,stem,run',[(case,*job) for case,job in JOBS.items() if job[1]])
def test_committed_full_context_inputs_are_real_h1_snapshots(case,pair,stem,run):
    manifest=Path('data/teacher_icmarkets_runs')/run/'data/teacher_icmarkets'/(stem+'.csv.manifest.json')
    data=json.loads(manifest.read_text())
    assert data['symbol']==pair and data['venue']=='ICMARKETS'
    assert data['base_tf']=='H1'
    assert manifest.with_name(stem+'.csv.gz').is_file()
    assert data['requested_start']<'2026-01-01'


def test_aborted_historical_replay_preserves_report_and_returns_failure(tmp_path,monkeypatch):
    from reports import replay_primary_video_case as replay
    def timeout(*args,**kwargs):
        raise TimeoutError('bounded historical replay')
    monkeypatch.setattr(replay,'OUT',tmp_path)
    monkeypatch.setattr(replay,'run',timeout)
    code=replay.main(['--case','video-t3-gbpcad-buy','--full-context','--detection-only'])
    assert code==1
    summary=json.loads((tmp_path/'summary.json').read_text())
    assert summary['execution_status']=='ABORTED_RUNTIME'
    assert summary['teacher_acceptance']=='NOT_ESTABLISHED'
    assert not (tmp_path/'video-t3-gbpcad-buy.json.gz').exists()

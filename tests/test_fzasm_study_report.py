import math
from pathlib import Path
import pandas as pd
import pytest
from fzasm.study_report import write_study_report, TARGETS, STOPS


def outcome(signal='a', symbol='USDJPY', month='2026-01', status='CLOSED', result=1., policy='h1_av', stop='sweep_exact', target='1R'):
    return dict(signal_id=signal, symbol=symbol, entry_policy=policy, stop_variant=stop,
                target=target, timestamp=month+'-03T00:00:00Z', status=status,
                result_r=result, exit_time=month+'-04T00:00:00Z')


def test_weighted_yearly_rates_unresolved_and_pair_groups(tmp_path):
    rows=[outcome('jan-win'),outcome('unknown',status='UNKNOWN',result=None),
          outcome('pending',status='PENDING',result=None),outcome('open',status='OPEN',result=None),
          outcome('feb-win',month='2026-02')]
    rows += [outcome(f'loss-{i}',month='2026-02',result=-1.) for i in range(3)]
    rows += [outcome('flat',month='2026-02',result=0.)]
    rows += [outcome('gold',symbol='XAUUSD',result=2.)]
    got=write_study_report(rows,tmp_path)
    yearly=got['yearly'].query("symbol == 'USDJPY'").iloc[0]
    assert yearly.closed==6 and yearly.setups==9
    assert yearly.win_rate_pct==pytest.approx(100/3)
    assert yearly.gross_resolved_r==-1
    assert yearly.unknown==1 and yearly.pending==1 and yearly.open==1
    assert yearly['flat']==1
    january=got['monthly'].query("symbol == 'USDJPY' and month == '2026-01'").iloc[0]
    assert january.win_rate_pct==100
    assert got['yearly_groups'].query("asset_group == 'JPY'").iloc[0].gross_resolved_r==-1
    csv=pd.read_csv(tmp_path/'outcomes.csv')
    assert csv.loc[csv.status=='UNKNOWN','result_r'].isna().all()
    assert all((tmp_path/f).exists() for f in ['monthly.csv','yearly.csv','monthly_groups.csv','yearly_groups.csv','STUDY_REPORT.md','coverage.csv'])


def test_complete_empty_month_zero_signals_missing_not_zero(tmp_path):
    coverage=[dict(symbol='EURUSD',entry_policy='h1_av',month='2026-01',status='complete'),
              dict(symbol='EURUSD',entry_policy='h1_av',month='2026-02',status='missing')]
    got=write_study_report([],tmp_path,coverage)
    assert len(got['monthly'])==12
    assert set(got['monthly'].month)=={'2026-01'}
    assert got['monthly'].setups.sum()==0
    assert got['monthly'].win_rate_pct.isna().all()
    assert len(pd.read_csv(tmp_path/'coverage.csv'))==2
    assert set(got['yearly'].coverage_status)=={'partial_or_unverified'}
    assert set(got['yearly_groups'].coverage_status)=={'partial_or_unverified'}


def test_complete_cohorts_match_for_every_stop_target_and_reconcile(tmp_path):
    rows=[outcome(signal,stop=stop,target=target,result=1. if signal=='a' else -1.)
          for signal in ['a','b'] for stop in STOPS for target in TARGETS]
    coverage=[dict(symbol='USDJPY',entry_policy='h1_av',month='2026-01',status='complete')]
    got=write_study_report(rows,tmp_path,coverage)
    assert len(got['monthly'])==12
    assert set(got['monthly'].setups)=={2}
    assert set(got['yearly'].win_rate_pct)=={50.}
    assert set(got['yearly'].gross_resolved_r)=={0.}
    with pytest.raises(ValueError,match='all stop/target'):
        write_study_report(rows[:-1],tmp_path/'bad',coverage)


@pytest.mark.parametrize('change',[
    dict(status='UNKNOWN',result_r=0.),dict(status='CLOSED',result_r=None),
    dict(status='CLOSED',result_r=float('inf')),dict(timestamp='2026-01-03'),
    dict(target='invented')])
def test_invalid_accounting_rejected(tmp_path,change):
    row=outcome();row.update(change)
    with pytest.raises(ValueError):write_study_report([row],tmp_path)


def test_duplicate_signal_is_not_double_counted(tmp_path):
    with pytest.raises(ValueError,match='Duplicate'):
        write_study_report([outcome(),outcome()],tmp_path)


def test_alternative_models_never_summed_and_utc_month(tmp_path):
    first=outcome();first['timestamp']='2026-02-01T00:30:00+01:00'
    got=write_study_report([first,outcome(policy='h1_av_m5',result=3.)],tmp_path)
    assert len(got['yearly_groups'])==2
    assert set(got['yearly_groups'].gross_resolved_r)=={1.,3.}
    assert set(got['monthly'].month)=={'2026-01'}


def test_all_symbol_totals_preserve_models_and_missing_coverage(tmp_path):
    rows=[outcome('jpy',result=1.),outcome('gold',symbol='XAUUSD',result=-1.),
          outcome('major',symbol='EURUSD',result=2.),outcome('different-policy',policy='h1_av_m5',result=3.)]
    coverage=[dict(symbol='GBPUSD',entry_policy='h1_av',month='2026-01',status='missing')]
    got=write_study_report(rows,tmp_path,coverage)
    total=got['yearly_all'].query("entry_policy == 'h1_av'").iloc[0]
    assert total.setups==3 and total.closed==3
    assert total.gross_resolved_r==2.
    assert total.win_rate_pct==pytest.approx(200/3)
    assert total.coverage_status=='partial_or_unverified'
    assert len(got['yearly_all'])==2
    assert got['monthly_all'].query("entry_policy == 'h1_av'").iloc[0].coverage_status=='partial_or_unverified'
    assert (tmp_path/'monthly_all.csv').exists() and (tmp_path/'yearly_all.csv').exists()
    markdown=(tmp_path/'STUDY_REPORT.md').read_text()
    assert '## Yearly results across all selected symbols' in markdown
    assert '| Coverage |' in markdown and 'partial_or_unverified' in markdown


def test_complete_buffer_only_month_and_missing_target_guard(tmp_path):
    coverage=[dict(symbol='USDJPY',entry_policy='h1_av',month='2026-01',status='complete')]
    rows=[outcome(stop='sweep_plus_3p',target=t) for t in TARGETS]
    got=write_study_report(rows,tmp_path/'valid',coverage,stop_variants=('sweep_plus_3p',))
    assert len(got['monthly'])==6
    assert set(got['monthly'].stop_variant)=={'sweep_plus_3p'}
    assert got['monthly'].setups.sum()==6
    with pytest.raises(ValueError,match='Complete coverage requires'):
        write_study_report(rows[:-1],tmp_path/'missing',coverage,stop_variants=('sweep_plus_3p',))
    with pytest.raises(ValueError,match='Complete coverage requires'):
        write_study_report(rows,tmp_path/'default',coverage)
    empty=write_study_report([],tmp_path/'empty',coverage,stop_variants=('sweep_plus_3p',))
    assert len(empty['monthly'])==6

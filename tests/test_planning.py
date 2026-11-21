import csv
import hashlib
import itertools
import json

import numpy as np
import pytest

from sebekekalkan_core.planning import compare, objective, oracle_schedule, schedule


@pytest.mark.parametrize('crews',[1,2,3])
def test_independent_assignment_and_no_overlap(scenario,crews):
    scenario.crews=crews
    for order in itertools.permutations([f.pipe_id for f in scenario.failures]):
        product=schedule(scenario,order)
        assert product==oracle_schedule(scenario,order)
        for crew in range(1,crews+1):
            jobs=sorted([a for a in product if a['crew']==crew],key=lambda x:x['starts_at_h'])
            assert all(a['ends_at_h']<=b['starts_at_h'] for a,b in zip(jobs,jobs[1:]))


def test_all_six_physical_candidates_independent_oracle(comparison):
    result,folder=comparison
    assert result['search']['candidate_count']==6
    assert result['search']['oracle_verified']
    candidates={tuple(x['order']):x['objective'] for x in result['search']['candidates']}
    for reference in result['search']['oracle']:
        assert np.allclose(candidates[tuple(reference['order'])],reference['objective'],rtol=1e-8,atol=1e-6)
    best=min(candidates.values())
    assert np.allclose(objective(result['methods']['proposal']),best)
    assert result['leakage_volume_m3'] is None
    assert set(result['methods'])=={'fifo','greedy','proposal'}
    assert result['methods']['fifo']['metrics']['unmet_demand_volume_m3']>result['baseline']['metrics']['unmet_demand_volume_m3']
    assert result['input_sha256']==hashlib.sha256((folder/'input.json').read_bytes()).hexdigest()


def test_export_trace_and_numeric_consistency(comparison):
    result,folder=comparison
    with (folder/'summary.csv').open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream,delimiter=';'))
    assert rows[0]['Yöntem']=='Bildirim sırası'
    assert float(rows[0]['Toplam karşılanamayan hacim (m³)'])==result['methods']['fifo']['metrics']['unmet_demand_volume_m3']
    assert rows[0]['Girdi SHA-256']==result['input_sha256']
    for name,digest in json.loads((folder/'output-hashes.json').read_text()).items():
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest


def test_equal_gains_are_reported_and_manual_order(scenario,tmp_path):
    scenario.crews=3
    scenario.manual_order=['233','247','137']
    value=compare(scenario,tmp_path/'ties')
    assert value['search']['optimal_ties']==6
    assert abs(value['unmet_reduction_vs_fifo_m3'])<1e-5
    assert objective(value['methods']['manual'])==pytest.approx(objective(value['methods']['proposal']))


def test_critical_weight_changes_target(scenario,tmp_path,comparison):
    scenario.critical_weights={'203':10,'215':10}
    result=compare(scenario,tmp_path/'weights')
    original=comparison[0]
    assert result['methods']['fifo']['metrics']['weighted_unmet_volume_m3']!=pytest.approx(original['methods']['fifo']['metrics']['weighted_unmet_volume_m3'])
    assert result['search']['oracle_verified']

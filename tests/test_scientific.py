import hashlib
import itertools
import json
from pathlib import Path

import pytest

from sebekekalkan_core.contracts import Scenario
from sebekekalkan_core.networks import ROOT,eligible_pipes,load_model
from sebekekalkan_core.scientific import close,dispatch_with_access,equal_objective,lex_compare,registered


def test_registration_precedes_all_new_main_runs():
    protocol,lock,frozen=registered()
    assert not lock['main_results_exist']
    assert lock['planned_main']==36
    assert len(protocol['cases'])==36
    assert len({tuple(sorted(x['pipes'])) for x in protocol['triples']})==12
    assert protocol['seed']==20261030
    assert len(frozen)==5
    execution=ROOT/'experiments/results/build02/execution.json'
    if execution.exists():
        data=json.loads(execution.read_text(encoding='utf-8'))
        assert data['started_utc']>lock['lock_written_utc']
        assert all(j['started_utc']>lock['lock_written_utc'] for j in data['jobs'])


def test_fixed_paired_matrix_and_supported_model():
    protocol,_,_=registered();eligible=eligible_pipes(load_model())
    for triple in protocol['triples']:
        cases=[c for c in protocol['cases'] if c['cluster_id']==triple['cluster_id']]
        assert [c['scenario']['crews'] for c in cases]==[1,2,3]
        assert set(triple['pipes'])<=eligible
        normalized=[]
        for c in cases:
            config=dict(c['scenario']);config.pop('crews');config.pop('name');normalized.append(config)
        assert normalized[0]==normalized[1]==normalized[2]


def test_sensitivity_was_fixed_and_events_align():
    protocol,_,_=registered()
    assert protocol['sensitivity']['case_ids']==['T01_C1','T05_C2','T12_C3']
    for c in protocol['cases']:
        if c['case_id'] in protocol['sensitivity']['case_ids']:
            for step in protocol['sensitivity']['alternatives_minutes']:
                s=Scenario.model_validate({**c['scenario'],'step_minutes':step})
                assert s.failure_start_hour*60%step==0
                assert all(f.repair_hours*60%step==0 for f in s.failures)


@pytest.mark.parametrize('a,b,expected',[
    ([10,5,8],[10,6,7],-1),([10,5,8],[10,5,7],1),
    ([0,0,0],[.0000001,0,0],0),([.00001,0,0],[0,100,100],1),
])
def test_preregistered_lexicographic_tolerance(a,b,expected):
    assert lex_compare(a,b)==expected
    assert lex_compare(b,a)==-expected


def test_access_delays_do_not_overlap_and_change_actual_completion(scenario):
    scenario.crews=2
    out=dispatch_with_access(scenario,['137','247','233'],[.5,0,0])
    assert out[0]['crew']==2 and out[0]['starts_at_h']==2
    assert out[1]['crew']==1 and out[1]['starts_at_h']==2.5
    assert out[2]['crew']==2 and out[2]['starts_at_h']==4
    for crew in (1,2):
        jobs=[x for x in out if x['crew']==crew]
        assert all(x['ends_at_h']<=y['starts_at_h'] for x,y in zip(jobs,jobs[1:]))


def test_failed_plan_does_not_hide_other_real_hydraulic_runs(scenario,tmp_path,monkeypatch):
    from sebekekalkan_core import scientific
    from sebekekalkan_core.networks import AnalysisError
    real=scientific.simulate
    def one_failure(value,assignments,folder,solver='epanet'):
        if folder.name=='single-1':raise AnalysisError('Olumsuz test: tekli aşama hata verdi.')
        return real(value,assignments,folder,solver=solver)
    scenario.manual_order=['233','247','137']
    monkeypatch.setattr(scientific,'simulate',one_failure)
    result=scientific.compare_case(scenario,tmp_path)
    assert result['status']=='partial_or_failed'
    assert result['methods']['greedy']['status']=='not_computable'
    assert result['methods']['fifo']['status']=='completed'
    assert result['methods']['proposal']['status']=='completed'
    assert result['methods']['manual']['status']=='completed'
    assert result['search']['oracle_verified']
    assert (tmp_path/'single-1/exception.log').exists()


def test_frozen_engine_and_model_still_match_initial_inventory():
    _,_,frozen=registered()
    for name,sha in frozen.items():
        assert hashlib.sha256((ROOT/'backend'/name).read_bytes()).hexdigest()==sha

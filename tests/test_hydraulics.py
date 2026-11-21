import hashlib
import json
import math

import numpy as np
import pandas as pd
import pytest
import wntr

from sebekekalkan_core.contracts import Scenario
from sebekekalkan_core.hydraulics import integrate, model_for, simulate, validate_network
from sebekekalkan_core.networks import MODEL, MANIFEST, AnalysisError, load_model, eligible_pipes
from sebekekalkan_core.planning import schedule


def test_complete_original_model_and_provenance():
    model = load_model()
    meta = json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == meta['sha256']
    assert MODEL.read_bytes() == open(wntr.library.model_library.get_filepath('Net3'),'rb').read()
    assert hashlib.sha256((MODEL.parent/'LICENSE_WNTR.md').read_bytes()).hexdigest() == meta['license_sha256']
    assert (model.num_nodes,model.num_pipes,model.num_pumps,model.num_tanks,model.num_reservoirs,model.num_controls,model.num_patterns)==(97,117,2,3,2,18,5)
    assert model.options.time.duration == 604800
    assert not {'10','330','335'} & eligible_pipes(model)


def test_independent_expected_pattern_formula_and_pdd(comparison, scenario):
    result, folder = comparison
    model = model_for(scenario, [])
    expected = pd.read_csv(folder/'baseline/expected-demand.csv',index_col=0)
    # Independent sum of base demand * original pattern(t+pattern_start) * global multiplier.
    for at in (0,3600,7200):
        for name in ('101','203','215'):
            total=0
            for ts in model.get_node(name).demand_timeseries_list:
                factor=ts.pattern.at(at+model.options.time.pattern_start) if ts.pattern is not None else 1
                total+=ts.base_value*factor*model.options.hydraulic.demand_multiplier
            assert expected.loc[at,name] == pytest.approx(total,abs=1e-12)
    raw = result['baseline']
    p=np.asarray(raw['pressure_m'])[:,[raw['node_ids'].index(n) for n in model.junction_name_list]]
    delivered=np.asarray(raw['demand_m3s'])[:,[raw['node_ids'].index(n) for n in model.junction_name_list]]
    wanted=expected[model.junction_name_list].to_numpy()
    predicted=wanted*np.sqrt(np.clip(p/20,0,1))
    mask=(wanted>0)&(p>.01)
    assert np.allclose(delivered[mask],predicted[mask],rtol=1e-3,atol=2e-6)


def test_isolate_reopen_and_fresh_reset(tmp_path, scenario):
    baseline=simulate(scenario,[],tmp_path/'base')
    assigned=schedule(scenario,['137','247','233'])
    fault=simulate(scenario,assigned,tmp_path/'fault')
    fresh=simulate(scenario,[],tmp_path/'fresh')
    at=fault['times_seconds'].index(7200)
    for assignment in assigned:
        j=fault['link_ids'].index(assignment['pipe_id'])
        end=fault['times_seconds'].index(round(assignment['ends_at_h']*3600))
        assert all(row[j]==0 for row in fault['link_status'][at:end])
        assert np.max(np.abs(np.asarray(fault['flowrate_m3s'])[at:end,j]))<1e-8
        assert fault['link_status'][end][j] != 0
    assert np.allclose(fault['pressure_m'][:at],baseline['pressure_m'][:at])
    assert not np.allclose(fault['pressure_m'][at],baseline['pressure_m'][at])
    assert np.allclose(fresh['pressure_m'],baseline['pressure_m'],atol=1e-9)
    assert np.max(np.abs(np.asarray(fault['flowrate_m3s'])[-1,[fault['link_ids'].index(a['pipe_id']) for a in assigned]]))>0
    # Tank trajectories retain the interruption history; only the link state is restored.
    assert model_for(scenario,[]).num_controls == 18
    assert model_for(scenario,assigned).num_controls == 24


def test_real_cross_solver_and_signed_values(tmp_path):
    s=Scenario(failures=[{'pipe_id':'137','repair_hours':1}],horizon_hours=4,step_minutes=60)
    a=simulate(s,[],tmp_path/'epanet')
    b=simulate(s,[],tmp_path/'wntr',solver='wntr')
    assert a['node_ids']==b['node_ids']
    assert np.allclose(a['pressure_m'],b['pressure_m'],atol=.002)
    assert np.allclose(a['flowrate_m3s'],b['flowrate_m3s'],atol=1e-4)
    assert np.min(a['flowrate_m3s']) < 0
    assert np.isfinite(a['pressure_m']).all()


def test_real_solver_failure_not_zero_filled(tmp_path, scenario):
    scenario.hydraulic_trials=1
    with pytest.raises(AnalysisError,match='EPANET|yakınsamadı|eksik zaman'):
        simulate(scenario,[],tmp_path/'nonconvergence')
    assert (tmp_path/'nonconvergence/epanet.rpt').exists()
    assert not (tmp_path/'nonconvergence/pressure.csv').exists()


def test_units_integral_and_terminal_sample():
    assert integrate([1,1,999],[0,1800,3600])==3600
    assert integrate([0,2,9],[0,900,1800])==1800


@pytest.mark.parametrize('corruption',['nan','missing_time'])
def test_corrupt_solver_output_is_rejected_not_imputed(tmp_path,scenario,monkeypatch,corruption):
    original=wntr.sim.EpanetSimulator.run_sim
    def damaged(self,*args,**kwargs):
        raw=original(self,*args,**kwargs)
        if corruption=='nan':
            raw.node['pressure'].iloc[0,0]=np.nan
        else:
            raw.node['pressure']=raw.node['pressure'].iloc[:-1]
        return raw
    monkeypatch.setattr(wntr.sim.EpanetSimulator,'run_sim',damaged)
    with pytest.raises(AnalysisError,match='sonlu olmayan|eksik zaman'):
        simulate(scenario,[],tmp_path/'damaged')
    assert not (tmp_path/'damaged/pressure.csv').exists()


def test_changed_model_is_rejected(tmp_path,monkeypatch):
    from sebekekalkan_core import networks
    altered=tmp_path/'Net3.inp'
    altered.write_bytes(MODEL.read_bytes()+b'\n;changed')
    monkeypatch.setattr(networks,'MODEL',altered)
    with pytest.raises(AnalysisError,match='özeti değişmiş'):
        networks.load_model()


@pytest.mark.parametrize('patch',[
    {'crews':0},{'crews':True},{'crews':4},{'horizon_hours':1},{'step_minutes':7},
    {'failures':[{'pipe_id':'137','repair_hours':-1}]},
    {'failures':[{'pipe_id':'137','repair_hours':math.inf}]},
    {'failures':[{'pipe_id':'137','repair_hours':.1}]},
    {'failures':[{'pipe_id':'137','repair_hours':1}]*2},
    {'failures':[]},{'manual_order':['137']},{'critical_weights':{'101':11}},
])
def test_invalid_contracts(scenario,patch):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Scenario.model_validate({**scenario.model_dump(),**patch})


@pytest.mark.parametrize('patch',[
    {'failures':[{'pipe_id':'missing','repair_hours':1}]},
    {'failures':[{'pipe_id':'330','repair_hours':1}]},
    {'critical_weights':{'unknown':2}},
])
def test_invalid_real_network(scenario,patch):
    s=Scenario.model_validate({**scenario.model_dump(),**patch})
    with pytest.raises(AnalysisError):
        validate_network(s,load_model())

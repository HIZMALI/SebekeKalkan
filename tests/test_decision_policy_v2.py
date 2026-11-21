import copy,itertools,json,math
from pathlib import Path
import pytest
from sebekekalkan_core.networks import ROOT,AnalysisError
from sebekekalkan_core.decision_policy_v2 import select,evaluate_methods,DecisionPolicyError

R1=ROOT/'experiments/results/build02_r1'
@pytest.fixture
def candidates():
    return json.loads((R1/'analysis_v2/T11_C2/epanet/result.json').read_text(encoding='utf-8'))['decision']['candidates']

def test_actual_six_recomputed_candidates_and_T11_C2(candidates):
    decision=select(candidates)
    assert decision['legacy_raw_minimum']['objective'][2]==8
    assert decision['selected']['objective'][2]==7
    assert decision['selected']['order']==['153','193','112']
    for i in range(6):
        status=json.loads((R1/f'analysis_v2/T11_C2/epanet/candidate-{i}/status.json').read_text(encoding='utf-8'))
        assert status['status']=='completed'

def test_all_720_candidate_permutations_same_decision(candidates):
    expected=select(candidates)
    for order in itertools.permutations(candidates):assert select(order)==expected

def test_global_minimum_anchor_avoids_nontransitive_chain(candidates):
    data=copy.deepcopy(candidates)
    for i,c in enumerate(data):c['objective']=[100 if i>2 else i*9e-7,0,8-i]
    selected=select(data)
    assert selected['selected']['order']==data[1]['order']
    assert data[2]['order'] not in selected['stages'][0]['retained_orders']

def test_second_component_is_also_minimum_anchored(candidates):
    data=copy.deepcopy(candidates)
    for i,c in enumerate(data):c['objective']=[0,100 if i>2 else i*9e-7,8-i]
    assert select(data)['selected']['order']==data[1]['order']

def test_actual_one_crew_and_three_crew_cases():
    for solver in ['epanet','wntr']:
        one=json.loads((R1/f'analysis_v2/T11_C1/{solver}/result.json').read_text(encoding='utf-8'))
        three=json.loads((R1/f'analysis_v2/T11_C3/{solver}/result.json').read_text(encoding='utf-8'))
        assert select(one['decision']['candidates'])['selected']['objective'][2]==11
        assert len(select(three['decision']['candidates'])['equivalent_best_orders'])==6

@pytest.mark.parametrize('component',[0,1,2])
@pytest.mark.parametrize('value',[float('nan'),float('inf')])
def test_nan_or_inf_target_is_rejected(candidates,component,value):
    data=copy.deepcopy(candidates);data[0]['objective'][component]=value
    with pytest.raises(DecisionPolicyError,match='sonlu'):select(data)

@pytest.mark.parametrize('corruption',['missing','duplicate','failed'])
def test_incomplete_or_failed_candidate_not_silently_dropped(candidates,corruption):
    data=copy.deepcopy(candidates)
    if corruption=='missing':data.pop()
    elif corruption=='duplicate':data[-1]=data[0]
    else:data[0]['status']='failed'
    with pytest.raises(DecisionPolicyError):select(data)

def test_real_solver_failure_is_not_a_selectable_target(tmp_path,candidates):
    from sebekekalkan_core.scientific import Recorder
    from sebekekalkan_core.contracts import Scenario
    config=json.loads((R1/'analysis_v2/T11_C2/epanet/input.json').read_text(encoding='utf-8'));config['hydraulic_trials']=1
    plan=Recorder(tmp_path,Scenario.model_validate(config)).run('fails',[])
    assert plan['status']=='failed'
    data=copy.deepcopy(candidates);data[0].update(status=plan['status'],objective=plan.get('objective'))
    with pytest.raises(DecisionPolicyError):select(data)

def test_all_methods_share_single_policy_pool(candidates):
    result=evaluate_methods(candidates,{'fifo':candidates[0]['order'],'other':candidates[1]['order']})
    assert {x['policy'] for x in result['methods'].values()}=={'decision_policy_v2'}
    assert {x['decision_sha256'] for x in result['methods'].values()}=={result['decision']['decision_sha256']}

def test_records_do_not_change_immutable_scientific_decision():
    old=json.loads((ROOT/'experiments/results/build02/scientific-gate.json').read_text(encoding='utf-8'))
    assert old['decision']=='NO-GO-BILIMSEL'

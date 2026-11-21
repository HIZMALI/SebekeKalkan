"""Four-failure research is isolated from the product's three-failure contract."""
from itertools import permutations
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
import wntr

from sebekekalkan_core import s02_comparison as comparison
from sebekekalkan_core.contracts_v2 import ScenarioV2
from sebekekalkan_core.planning import oracle_schedule, schedule
from sebekekalkan_core.s02_evidence import audit_case, verdict, verified_card
from sebekekalkan_core.s02_physics import METRICS, OUT, ROOT, SOURCE, ScenarioS02, identity, load, model_for_entry, sha
from sebekekalkan_core.s02_search import candidates, greedy_order, rank_schedules, select_verified, signature


@pytest.fixture
def inputs():
    return load(OUT/"PROTOKOL_GIRDILERI.json")["cases"]


def test_registered_files_and_models_are_content_addressed(inputs):
    for name,digest in load(OUT/"PROTOKOL_LOCK.json")["files"].items():
        assert sha(OUT/name)==digest
    code=load(OUT/"KANIT/YONTEM_KILIDI.json")
    assert code["protocol_sha256"]==sha(OUT/"PROTOKOL_LOCK.json")
    for name,digest in code["codes"].items():
        assert sha(ROOT/name)==digest
    assert all(identity(x["scenario"])==x["scenario_sha256"] for x in inputs)
    for entry in load(SOURCE)["models"]:
        assert model_for_entry(entry).num_pipes==entry["pipes"]


def test_registration_is_disjoint_and_preserves_two_crew_dependence(inputs):
    groups={}
    for task in inputs:
        ids=frozenset(f["pipe_id"] for f in task["scenario"]["failures"])
        assert len(ids)==4
        key=(task["model_id"],ids)
        role,crews=groups.setdefault(key,(task["group"],set()))
        assert role==task["group"]
        crews.add(task["scenario"]["crews"])
    assert len(inputs)==14 and len(groups)==7
    assert all(crews=={1,2} for _,crews in groups.values())


def test_old_api_rejects_four_while_research_accepts_four(inputs):
    setting=inputs[0]["scenario"]
    assert len(ScenarioS02.model_validate(setting).failures)==4
    with pytest.raises(ValidationError):
        ScenarioV2.model_validate(setting)
    with pytest.raises(ValidationError):
        ScenarioS02.model_validate({**setting,"failures":[setting["failures"][0]]*4})


@pytest.mark.parametrize("crews,unique",[(1,24),(2,12)])
def test_two_schedulers_and_budgeted_search_without_physics(inputs,monkeypatch,crews,unique):
    sc=ScenarioS02.model_validate({**inputs[0]["scenario"],"crews":crews})
    fifo=tuple(f.pipe_id for f in sc.failures)
    model=model_for_entry(load(SOURCE)["models"][0])
    def forbidden(*args,**kwargs):
        pytest.fail("Candidate ranking called the physical solver")
    monkeypatch.setattr(wntr.sim.WNTRSimulator,"run_sim",forbidden)
    greedy=tuple(reversed(fifo))
    def rank():
        return rank_schedules(sc,model,fifo,dict.fromkeys(fifo,0.001),set(model.link_name_list),
                              set(model.tank_name_list+model.reservoir_name_list),{})
    ranked=rank()
    assert ranked==rank() and len(ranked)==24
    assert len({r[3] for r in ranked})==unique
    assert all(schedule(sc,o)==oracle_schedule(sc,o) for o in permutations(fifo))
    six=candidates(ranked,fifo,greedy,6)
    twelve=candidates(ranked,fifo,greedy,12)
    assert six==twelve[:6]
    for limit,orders in ((6,six),(12,twelve)):
        sig={signature(schedule(sc,o)) for o in orders}
        assert len(sig)==len(orders)==limit
        assert all(signature(schedule(sc,o)) in sig for o in (fifo,greedy))
    with pytest.raises(ValueError):
        candidates(ranked,fifo,greedy,24)


def test_greedy_uses_real_duration_and_baseline(inputs):
    sc=ScenarioS02.model_validate(inputs[0]["scenario"])
    singles={f.pipe_id:100+10*f.repair_hours*(i+1) for i,f in enumerate(sc.failures)}
    order,scores=greedy_order(sc,100,singles)
    assert list(order)==[f.pipe_id for f in reversed(sc.failures)]
    assert sorted(scores.values())==[10,20,30,40]


def test_manifest_and_model_path_fail_closed():
    first=load(SOURCE)["models"][0]
    for change in ({"working_sha256":"0"*64},{"filename":"../missing.inp"},{"license_sha256":"0"*64}):
        with pytest.raises(ValueError):
            model_for_entry({**first,**change})


def test_tolerant_choice_and_independent_metric_verdict():
    def row(value,pressure,finish,order):
        return dict(status="PASS",order=[order],metrics=dict(zip(METRICS,[value,300,pressure,finish])))
    pool=[row(10.0,2.0,12,"a"),row(10.00000001,1.0,16,"b"),row(10.00000002,1.0,11,"c")]
    assert select_verified(pool)["order"]==["c"]
    assert verdict(10,10.00000001,METRICS[0])=="TIE"
    assert verdict(10,11,METRICS[0])=="LOSS" and verdict(10,9,METRICS[0])=="WIN"
    assert verdict(10,10.00000001,METRICS[3])=="LOSS"
    for bad in ([{**pool[0],"status":"PHYSICAL_INVALID"}],[row(float("nan"),0,0,"z")],[]):
        with pytest.raises(ValueError):
            select_verified(bad)


def test_oracle_only_starts_after_decisions_are_written(tmp_path,inputs,monkeypatch):
    seen=[]
    lab=SimpleNamespace(scenario=ScenarioS02.model_validate(inputs[0]["scenario"]),records=[],folder=tmp_path)
    def method(_,name):
        assert not (tmp_path/"decisions-before-oracle.json").exists()
        seen.append(name)
        return {"status":"SOLVER_ERROR"}
    def oracle(_):
        assert tuple(seen)==comparison.METHODS
        frozen=load(tmp_path/"decisions-before-oracle.json")
        assert set(frozen["methods"])==set(seen)
        return {"status":"PHYSICAL_INVALID"},[]
    monkeypatch.setattr(comparison,"execute",method)
    monkeypatch.setattr(comparison,"exhaustive",oracle)
    assert comparison.compare(lab)["status"]=="SOLVER_ERROR"


@pytest.mark.parametrize("status,oracle_count",[("TIMEOUT",24),("PHYSICAL_INVALID",0),("ORACLE_MISMATCH",24),("PASS",23)])
def test_partial_or_invalid_case_cannot_export_demo(tmp_path,status,oracle_count):
    with pytest.raises(ValueError):
        verified_card(tmp_path,{"status":status,"oracle":{"valid":oracle_count}},"fifo","s02_b6",14)


def test_cost_counts_actual_entries_and_failures_separately():
    event=dict(cpu_s=.05,wall_s=.1,solver_status="returned")
    er={**event,"solver_status":"exception"}
    records=[dict(name="x-base",status="PASS",calls=[event,event]),
             dict(name="x-candidate01",status="SOLVER_ERROR",calls=[er])]
    cost=comparison.cost(records,2,1)
    assert (cost["wntr_calls"],cost["solver_returns"],cost["physical_trials"])==(3,2,2)
    assert cost["valid_trials"]==cost["invalid_trials"]==1
    assert cost["preliminary_trials"]==cost["candidate_trials"]==1

def test_worker_failure_before_first_call_is_a_recorded_result(tmp_path,inputs):
    import json
    task=inputs[0]
    (tmp_path/"task.json").write_text(json.dumps({"task":task}),encoding="utf8")
    result={"task":task,"status":"WORKER_ERROR","started_calls":0,"finished_calls":0}
    audited=audit_case(tmp_path,result)
    assert audited["raw_archives"]==audited["independent_integrals"]==0
    assert audited["result_status"]=="WORKER_ERROR" and not audited["oracle_24_verified"]
    with pytest.raises(ValueError):
        audit_case(tmp_path,{**result,"status":"PASS"})

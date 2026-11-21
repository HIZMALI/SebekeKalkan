"""Independent, physically checked methods. The exhaustive reference runs last."""
from itertools import permutations
import time
from zipfile import ZipFile

import pandas as pd

from .planning import oracle_schedule, schedule
from .s02_physics import METRICS, same_metrics, sha, write
from .s02_search import candidates, greedy_order, rank_schedules, select_verified, signature

PRIMARY = METRICS[0]
METHODS = ("fifo","greedy","s02_b6","s02_b12")


def failed(row):
    return {"status":row["status"],"failed_trial":row.get("name"),"reason":row.get("cause") or row.get("reason")}


def verified(lab, prefix, record):
    if record["status"]!="PASS":return failed(record)
    order=record["order"]
    reference=record["metrics"]
    repeats=[]
    for stage, scheduler in (("fresh",schedule),("repeat",oracle_schedule)):
        row=lab.trial(prefix+"-"+stage,scheduler(lab.scenario,order),order)
        repeats.append(row["name"])
        if row["status"]!="PASS":return failed(row)
        if (signature(row["assignments"])!=signature(record["assignments"]) or
            row["assignments"]!=record["assignments"] or not same_metrics(reference,row["metrics"])):
            return {"status":"ORACLE_MISMATCH","failed_trial":row["name"]}
    return {"status":"PASS","order":order,"metrics":reference,"record":record["name"],
            "verification":repeats,"physical_pass":True}


def observed(lab, prefix, order):
    return lab.trial(prefix,schedule(lab.scenario,order),order)


def reference_features(lab,prefix):
    base=lab.trial(prefix+"-base",[])
    if base["status"]!="PASS":return None,None,failed(base)
    singles={}
    for i,f in enumerate(lab.scenario.failures):
        row=lab.trial(f"{prefix}-single{i+1}",[{"pipe_id":f.pipe_id,"crew":1,"starts_at_h":lab.scenario.failure_start_hour,
                         "ends_at_h":lab.scenario.horizon_hours}],(f.pipe_id,))
        if row["status"]!="PASS":return None,None,failed(row)
        singles[f.pipe_id]=row["metrics"][PRIMARY]
    return base,singles,None


def topological_inputs(scenario, raw):
    with ZipFile(raw) as archive:
        with archive.open("expected-demand.csv") as f:
            expected=pd.read_csv(f,index_col=0)
        with archive.open("link-status.csv") as f:
            initial=pd.read_csv(f,index_col=0,nrows=1).iloc[0]
    start=scenario.failure_start_hour*3600
    end=scenario.horizon_hours*3600
    samples=expected[(expected.index>=start)&(expected.index<end)]
    if len(samples)!=(end-start)/(scenario.step_minutes*60):raise ValueError("Eksik talep zaman dizisi.")
    demand={p:float(v)*scenario.critical_weights.get(p,1) for p,v in samples.clip(lower=0).mean().items()}
    injectors={p for p in samples if (samples[p]<0).any()}
    return set(initial[initial!=0].index),injectors,demand


def execute(lab,name):
    sc=lab.scenario; fifo=tuple(f.pipe_id for f in sc.failures)
    if name=="fifo":return verified(lab,name,observed(lab,"fifo-candidate",fifo))
    base,singles,error=reference_features(lab,name)
    if error:return error
    volume=base["metrics"][PRIMARY]
    greedy,scores=greedy_order(sc,volume,singles)
    if name=="greedy":
        return {**verified(lab,name,observed(lab,"greedy-candidate",greedy)),"single_scores_m3_per_h":scores}
    budget={"s02_b6":6,"s02_b12":12}[name]
    span=(sc.horizon_hours-sc.failure_start_hour)*3600
    rates={p:max(0,(v-volume)/span) for p,v in singles.items()}
    open_links,injections,demand=topological_inputs(sc,lab.folder/base["raw"])
    sources=set(lab.model.reservoir_name_list+lab.model.tank_name_list)|injections
    ranking=rank_schedules(sc,lab.model,fifo,rates,open_links,sources,demand)
    orders=candidates(ranking,fifo,greedy,budget)
    plan={"budget":budget,"fifo":fifo,"greedy":greedy,"candidate_orders":orders,
          "available_unique_schedules":len({x[3] for x in ranking}),
          "surrogate":[{"order":x[2],"estimated_volume_m3":x[0],"finish_h":x[1]} for x in ranking]}
    write(lab.folder/(name+"-plan.json"),plan)
    pool=[observed(lab,f"{name}-candidate{i+1:02}",o) for i,o in enumerate(orders)]
    invalid=next((r for r in pool if r["status"]!="PASS"),None)
    outcome=failed(invalid) if invalid else verified(lab,name,select_verified(pool))
    return {**outcome,"budget":budget,"unique_candidates":len(pool),"unique_available":plan["available_unique_schedules"],
            "mandatory_reference_signatures_included":all(signature(schedule(sc,o)) in {signature(c["assignments"]) for c in pool}
                for o in (fifo,greedy))}


def cost(records,wall,cpu):
    return {"physical_trials":len(records),"wntr_calls":sum(len(r["calls"]) for r in records),
            "solver_returns":sum(c["solver_status"]=="returned" for r in records for c in r["calls"]),
            "valid_trials":sum(r["status"]=="PASS" for r in records),
            "invalid_trials":sum(r["status"]!="PASS" for r in records),
            "preliminary_trials":sum("-base" in r["name"] or "-single" in r["name"] for r in records),
            "candidate_trials":sum("-candidate" in r["name"] for r in records),
            "verification_trials":sum(r["name"].endswith(("-fresh","-repeat")) for r in records),
            "wall_s":wall,"cpu_s":cpu,"solver_cpu_s":sum(c["cpu_s"] for r in records for c in r["calls"]),
            "solver_wall_s":sum(c["wall_s"] for r in records for c in r["calls"])}


def exhaustive(lab):
    ids=sorted(f.pipe_id for f in lab.scenario.failures)
    if len(ids)!=4:raise ValueError("Dört arıza gerekli.")
    pool=[lab.trial(f"oracle-candidate{i+1:02}",oracle_schedule(lab.scenario,o),o)
          for i,o in enumerate(permutations(ids))]
    invalid=next((row for row in pool if row["status"]!="PASS"),None)
    if invalid:return {**failed(invalid),"count":len(pool),"valid":sum(r["status"]=="PASS" for r in pool)},pool
    earliest=select_verified(pool)
    return {**verified(lab,"oracle",earliest),"count":len(pool),"valid":len(pool),
            "unique":len({signature(x["assignments"]) for x in pool}),
            "minimum_weighted_unmet_volume_m3":min(r["metrics"][PRIMARY] for r in pool)},pool


def compare(lab):
    if len(lab.scenario.failures)!=4:raise ValueError("Dört arıza zorunlu.")
    methods={}; costs={}
    for name in METHODS:
        offset=len(lab.records); w,c=time.perf_counter(),time.process_time()
        outcome=execute(lab,name)
        if name.startswith("s02") and outcome["status"]!="PASS" and methods["greedy"]["status"]=="PASS":
            outcome["fallback_to_greedy"]={"order":methods["greedy"]["order"],"source_record":methods["greedy"]["record"]}
        methods[name]=outcome
        costs[name]=cost(lab.records[offset:],time.perf_counter()-w,time.process_time()-c)
    frozen=lab.folder/"decisions-before-oracle.json"
    write(frozen,{"methods":methods,"costs":costs})
    frozen_hash=sha(frozen)
    offset=len(lab.records);w,c=time.perf_counter(),time.process_time()
    oracle,pool=exhaustive(lab)
    costs["oracle"]=cost(lab.records[offset:],time.perf_counter()-w,time.process_time()-c)
    by_order={tuple(x["order"]):x for x in pool}
    if sha(frozen)!=frozen_hash:raise RuntimeError("Kayıtlı yöntem kararı değişti.")
    for name,m in methods.items():
        if m["status"]!="PASS" or oracle["status"]!="PASS":continue
        matched=same_metrics(m["metrics"],by_order[tuple(m["order"])]["metrics"])
        m["oracle_same_order_match"]=matched
        if not matched:m["status"]="ORACLE_MISMATCH"
        else:m["oracle_gap_m3"]=m["metrics"][PRIMARY]-oracle["minimum_weighted_unmet_volume_m3"]
    first=next((m for m in [*methods.values(),oracle] if m["status"]!="PASS"),None)
    return {"status":first["status"] if first else "PASS","methods":methods,"oracle":oracle,"costs":costs,
            "decisions_sha256":frozen_hash,"recover_service":"not_evaluated"}

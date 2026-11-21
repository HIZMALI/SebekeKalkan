"""Read-only view of finished S02 results. This module cannot launch a calculation."""
from itertools import permutations
from pathlib import Path
from zipfile import ZipFile
import json

import numpy as np
import pandas as pd

from .s02_physics import METRICS, close, identity, load, same_metrics, sha


def verdict(reference, proposal, metric):
    equal=reference==proposal if metric=="repair_completion_hour" else close(reference,proposal)
    return "TIE" if equal else "WIN" if proposal<reference else "LOSS"


def verified_card(folder, outcome, baseline, method, denominator):
    """Export admission is evidence-based; an incomplete physical run has no public card."""
    if outcome.get("status")!="PASS" or outcome.get("oracle",{}).get("valid")!=24:
        raise ValueError("Eksik veya fiziksel doğrulanmamış kayıttan gösterim üretilmez.")
    task=outcome["task"]
    if (folder.name!=outcome["run_id"] or identity(task["scenario"])!=task["scenario_sha256"]
        or sha(folder/"decisions-before-oracle.json")!=outcome["decisions_sha256"]):
        raise ValueError("Kayıt kimliği doğrulanamadı.")
    for which in (baseline,method):
        m=outcome["methods"][which]
        if (m.get("status")!="PASS" or m.get("physical_pass") is not True or
                m.get("oracle_same_order_match") is not True or len(m.get("verification",[]))!=2):
            raise ValueError("Doğrulanmamış yöntem.")
        for name in (m["record"],*m["verification"]):
            record=load(folder/(name+".json"))
            if (record.get("status")!="PASS" or not record.get("r1",{}).get("pass") or not record.get("extra",{}).get("pass")
                    or not same_metrics(m["metrics"],record["metrics"]) or sha(folder/record["raw"])!=record["raw_sha256"]):
                raise ValueError("Ham fizik kaydı uyuşmuyor.")
    a,b=(outcome["methods"][key] for key in (baseline,method))
    return {"case_id":task["case_id"],"network":task["model_id"],"network_sha256":task["model_sha256"],
            "scenario_sha256":task["scenario_sha256"],"method_version":outcome["method_version"],
            "record_id":outcome["run_id"],"record_sha256":sha(folder/"result.json"),"physical_pass":True,
            "record_path":f"KOSULAR/{folder.name}/result.json","mode":"recorded","label":"Kayıtlı ve doğrulanmış sonuç",
            "source_stage":"SPRINT02","group":task["group"],"baseline":baseline,"comparison":method,
            "baseline_order":a["order"],"comparison_order":b["order"],"baseline_metrics":a["metrics"],
            "comparison_metrics":b["metrics"],"protocol_sha256":outcome["protocol_lock_sha256"],
            "scientific_scope":f"{task['group']}, dört sabit arıza; {denominator} kayıtlı koşul. Seçili örneğin ölçümleri.",
            "service_recovery":"not_evaluated"}


def independent_metrics(folder, row, sc):
    """Reintegrate untouched WNTR CSVs, independently of the in-memory objective."""
    with ZipFile(folder/row["raw"]) as archive:
        def frame(name):
            with archive.open(name+".csv") as file:return pd.read_csv(file,index_col=0)
        wanted,delivered,pressure=frame("expected-demand"),frame("demand"),frame("pressure")
    t=wanted.index.to_numpy()
    if not (np.array_equal(t,delivered.index) and np.array_equal(t,pressure.index) and len(t)>1
            and t[0]==0 and t[-1]==sc["horizon_hours"]*3600):
        raise ValueError("Ham zaman ekseni uyumsuz")
    weights=np.array([sc["critical_weights"].get(x,1) for x in wanted.columns])
    deficits=np.maximum(wanted.to_numpy()-delivered[wanted.columns].to_numpy(),0)*(wanted.to_numpy()>0)
    seconds=np.diff(t)
    low=(pressure[list(sc["critical_weights"])]<sc["low_pressure_m"]).sum(axis=1).to_numpy()
    return dict(zip(METRICS,(float(np.sum((deficits[:-1]@weights)*seconds)),
                              float(np.sum(deficits[:-1].sum(axis=1)*seconds)),
                              float(np.sum(low[:-1]*seconds)/3600),
                              max((e["ends_at_h"] for e in row["assignments"]),default=0))))


def audit_case(folder, outcome):
    task=outcome["task"];sc=task["scenario"];metadata=load(folder/"task.json")
    if metadata["task"]!=task or identity(sc)!=task["scenario_sha256"]:raise ValueError("Girdi kaydı uyuşmuyor")
    rows=[load(p) for p in folder.glob("*.json") if p.name not in {"task.json","result.json","worker.json","decisions-before-oracle.json"}
          and not p.name.endswith("-plan.json")]
    ledger=folder/"solver.jsonl"
    events=[json.loads(l) for l in ledger.read_text("utf8").splitlines()] if ledger.is_file() else []
    outcome_ok=outcome["status"]=="PASS"
    started=[e for e in events if e["op"]=="begin"]; ended=[e for e in events if e["op"]=="end"]
    if len(started)!=outcome["started_calls"] or len(ended)!=outcome["finished_calls"]:raise ValueError("Çağrı sayısı")
    event_keys=lambda group:[(e["trial"],e["seq"]) for e in group]
    if outcome_ok and (not started or event_keys(started)!=event_keys(ended) or
                       len(set(event_keys(started)))!=len(started) or any(e["solver_status"]!="returned" for e in ended)):
        raise ValueError("Tamamlanmamış veya yanlış eşleştirilmiş çözücü çağrısı")
    verified=0
    for row in rows:
        if sha(folder/row["raw"])!=row["raw_sha256"]:raise ValueError("Ham çıktı özeti farklı")
        if row["status"]!="PASS":continue
        if not row.get("r1",{}).get("pass") or not row.get("extra",{}).get("pass"):
            raise ValueError("Olumlu fizik kaydında kapı eksik")
        if [c["seq"] for c in row["calls"]]!=[1,2]:
            raise ValueError("Rapor ve iç olay WNTR çözümleri eksik")
        values=independent_metrics(folder,row,sc)
        if not same_metrics(values,row["metrics"]):raise ValueError("Bağımsız integraller uyuşmuyor: "+row["name"])
        verified+=1
    if outcome_ok:
        methods={**outcome["methods"],"oracle":outcome["oracle"]}
        if sum(v["wntr_calls"] for v in outcome["costs"].values())!=len(started):raise ValueError("Toplam bütçe")
        # Oracle may never precede an unfinished method decision.
        ordered=[e["trial"].split("-")[0] for e in started]
        first_oracle=ordered.index("oracle")
        if any(name!="oracle" for name in ordered[first_oracle:]):raise ValueError("Oracle sırası bozulmuş")
        if sha(folder/"decisions-before-oracle.json")!=outcome["decisions_sha256"]:raise ValueError("Karar özeti")
        for budget in (6,12):
            name="s02_b"+str(budget); plan=load(folder/(name+"-plan.json"))
            shots=[r for r in rows if r["name"].startswith(name+"-candidate")]
            keys={tuple(sorted((x["pipe_id"],x["ends_at_h"]) for x in r["assignments"])) for r in shots}
            if len(keys)!=len(shots) or len(shots)!=min(plan["available_unique_schedules"],budget):raise ValueError("Aday bütçesi")
            if set(map(tuple,plan["candidate_orders"]))!={tuple(r["order"]) for r in shots}:raise ValueError("Bütçe planı")
        oracle=[r for r in rows if r["name"].startswith("oracle-candidate")]
        if len(oracle)!=24 or {tuple(r["order"]) for r in oracle}!=set(permutations(f["pipe_id"] for f in sc["failures"])):
            raise ValueError("24 benzersiz öncelik tamamlanmadı")
        best=oracle
        for m in (METRICS[0],METRICS[2]):
            v=min(x["metrics"][m] for x in best)
            best=[x for x in best if abs(x["metrics"][m]-v)<=1e-6+1e-8*max(abs(v),abs(x["metrics"][m]))]
        ordered_best=sorted(best,key=lambda x:(x["metrics"][METRICS[3]],x["order"]))
        if outcome["oracle"]["order"]!=ordered_best[0]["order"]:raise ValueError("Bağımsız optimum uyuşmazlığı")
        for method in methods.values():
            if not same_metrics(method["metrics"],next(r["metrics"] for r in oracle if r["order"]==method["order"])):
                raise ValueError("Aynı plan için bağımsız değer uyuşmazlığı")
    return {"case":task["case_id"],"record_id":folder.name,"raw_archives":len(rows),"independent_integrals":verified,
            "solver_calls_started":len(started),"solver_calls_finished":len(ended),"result_status":outcome["status"],
            "oracle_24_verified":outcome_ok,"frozen_decision_sha256":outcome.get("decisions_sha256")}

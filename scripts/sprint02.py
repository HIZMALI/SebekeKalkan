"""Run a fixed S02 pilot or registered case in a fresh, bounded child process."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time
from uuid import uuid4

from sebekekalkan_core.networks import ROOT, eligible_pipes
from sebekekalkan_core.planning import oracle_schedule, schedule
from sebekekalkan_core.s02_physics import (OUT, SOURCE, METRICS, METHOD_VERSION, ScenarioS02,
    Laboratory, code_id, csv_file, identity, load, model_for_entry, same_metrics, sha, utc, write)

LIMIT = 180
SCRIPT = Path(__file__).resolve()
CORE = ROOT/"backend/sebekekalkan_core"
LOCK = OUT/"PROTOKOL_LOCK.json"
INPUTS = OUT/"PROTOKOL_GIRDILERI.json"
PILOTS = OUT/"PILOT_GIRDILERI.json"


def source_entry(name):
    return next(x for x in load(SOURCE)["models"] if x["model_id"]==name)


def strata(entry):
    model=model_for_entry(entry)
    pipes=sorted((model.get_link(n) for n in eligible_pipes(model)),key=lambda x:(-x.diameter,-x.length,x.name))
    n=len(pipes)
    if n<4:raise ValueError("Dört uygun boru gerekli")
    bins=[[p.name for p in pipes[i*n//4:(i+1)*n//4]] for i in range(4)]
    # Aggregate all demand categories. Injection nodes never become weighted customers.
    peak=__import__("wntr").metrics.expected_demand(model).max()
    nodes=sorted((n for n in model.junction_name_list if peak[n]>0),key=lambda n:(-float(peak[n]),n))
    return bins,dict(zip(nodes[:2],(3,2)))


def case(entry,group,label,pipes,weights,crews,stage):
    sc=ScenarioS02(name=label,failures=[{"pipe_id":p,"repair_hours":i+2} for i,p in enumerate(pipes)],
        critical_weights=weights,crews=crews,failure_start_hour=2,horizon_hours=24,step_minutes=15)
    return {"case_id":label,"group":group,"stage":stage,"model_id":entry["model_id"],
            "model_sha256":entry["original_sha256"],"scenario":sc.model_dump(),
            "scenario_sha256":identity(sc.model_dump())}


def pilot_eval(task,lab):
    ids=[f.pipe_id for f in lab.scenario.failures]
    if task["stage"]=="baseline":ids=[]
    assignments=schedule(lab.scenario,ids) if ids else []
    first=lab.trial("pilot",assignments,ids)
    if first["status"]!="PASS":return {"status":first["status"],"cause":first.get("cause") or first.get("reason")}
    fresh=lab.trial("repeat",oracle_schedule(lab.scenario,ids) if ids else [],ids)
    if fresh["status"]!="PASS":return {"status":fresh["status"],"cause":fresh.get("cause") or fresh.get("reason")}
    matched=assignments==fresh["assignments"] and same_metrics(first["metrics"],fresh["metrics"])
    return {"status":"PASS" if matched else "ORACLE_MISMATCH","fresh":matched,"minimum_pressure_m":first["extra"]["raw_min_junction_pressure_m"]}


def revision(pilot):
    files=[SCRIPT,ROOT/"scripts/sprint02_sources.py"]
    if not pilot:files += [CORE/"s02_search.py",CORE/"s02_comparison.py"]
    return code_id(*files)


def lockcheck():
    settings=load(LOCK)
    for name,h in settings["files"].items():
        if sha(OUT/name)!=h:raise ValueError("Ön kayıt bozulmuş: "+name)
    if load(INPUTS)["plan"]!="s02-v1":raise ValueError("Bilinmeyen protokol")
    return load(INPUTS)


def child(folder):
    packet=load(folder/"task.json"); task=packet["task"]
    pilot=task["group"]=="pilot"
    if packet["code_sha256"]!=revision(pilot):raise ValueError("Koşu kodu değişti")
    if not pilot:
        if packet["protocol_lock_sha256"]!=sha(LOCK) or task not in lockcheck()["cases"]:raise ValueError("Kilit dışı koşul")
    elif task not in load(PILOTS):raise ValueError("Pilot dışı koşul")
    entry=source_entry(task["model_id"])
    if identity(task["scenario"])!=task["scenario_sha256"] or task["model_sha256"]!=entry["original_sha256"]:
        raise ValueError("Girdi özeti değişti")
    lab=Laboratory(entry,ScenarioS02.model_validate(task["scenario"]),folder,packet)
    started=time.process_time()
    if pilot:outcome=pilot_eval(task,lab)
    else:
        from sebekekalkan_core.s02_comparison import compare
        outcome=compare(lab)
    outcome.update(worker_cpu_s=time.process_time()-started,physical_trials=len(lab.records),
        trial_statuses=dict(Counter(t["status"] for t in lab.records)),
        wntr_calls=sum(len(t["calls"]) for t in lab.records))
    write(folder/"worker.json",outcome)


def job(task,batch):
    folder=OUT/"KOSULAR"/uuid4().hex;folder.mkdir(parents=True)
    pilot=task["group"]=="pilot"
    meta={"run_id":folder.name,"batch":batch,"task":task,"started_utc":utc(),"solver":"WNTRSimulator 1.5.0 / PDD",
          "code_sha256":revision(pilot),"method_version":"pilot-s02-v1" if pilot else METHOD_VERSION,
          "protocol_lock_sha256":sha(PILOTS) if pilot else sha(LOCK),"limit_s":LIMIT}
    write(folder/"task.json",meta); start=time.perf_counter()
    env=dict(os.environ,PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1")
    with (folder/"worker.log").open("xb") as log:
        try:
            r=subprocess.run([sys.executable,"-X","utf8",str(SCRIPT),"worker",folder.name],
                 cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=LIMIT)
            result=load(folder/"worker.json") if r.returncode==0 else {"status":"WORKER_ERROR","exit_code":r.returncode}
        except subprocess.TimeoutExpired:
            result={"status":"TIMEOUT","cause":"180 s duvar süresi"}
    events=[json.loads(line) for line in (folder/"solver.jsonl").read_text("utf8").splitlines()] if (folder/"solver.jsonl").is_file() else []
    result["started_calls"]=sum(e["op"]=="begin" for e in events)
    result["finished_calls"]=sum(e["op"]=="end" for e in events)
    if result.get("status")=="PASS" and result["started_calls"]!=result["finished_calls"]:raise RuntimeError("Eksik çözücü günlüğü")
    result.update(**meta,wall_s=time.perf_counter()-start,finished_utc=utc())
    write(folder/"result.json",result)
    print(task["case_id"],result["status"],result["started_calls"],round(result["wall_s"],2),folder.name,flush=True)
    return result


def pilots():
    if PILOTS.exists():raise FileExistsError("Mevcut pilot kaydı korunur")
    tasks=[]
    for entry in load(SOURCE)["models"]:
        bins,w=strata(entry);pipes=[b[len(b)//2] for b in bins];name=entry["model_id"]
        for stage,ids in [("baseline",[pipes[1]]),("single",[pipes[1]]),("multi",pipes)]:
            tasks.append(case(entry,"pilot",name+"_"+stage,ids,w,1,stage))
    write(PILOTS,tasks); rows=[]; passed={}; batch=uuid4().hex
    for task in tasks:
        net=task["model_id"];stage=task["stage"]
        result=job(task,batch) if passed.get(net,True) else {"status":"NOT_EVALUATED","cause":"Önceki fizik kapısı başarısız"}
        passed[net]=result["status"]=="PASS"
        rows.append({"model":net,"stage":stage,"status":result["status"],"fresh_verified":result.get("fresh",False),
            "cause":result.get("cause",""),"minimum_pressure_m":result.get("minimum_pressure_m",""),
            "model_sha256":task["model_sha256"],"scenario_sha256":task["scenario_sha256"],"record_id":result.get("run_id",""),
            "wntr_calls":result.get("started_calls",0),"seconds":result.get("wall_s",0)})
    csv_file(OUT/"AG_FIZIK_KABULU_S02.csv",rows)
    write(OUT/"PILOT_SONUCU.json",{"batch":batch,"physical_pass":passed,"rows":rows})


def register():
    if LOCK.exists() or INPUTS.exists():raise FileExistsError("Var olan ön kayıt değiştirilemez")
    pilot=load(OUT/"PILOT_SONUCU.json")["physical_pass"];pilot_inputs=load(PILOTS)
    matrix=[]; excluded={}
    for i,entry in enumerate(load(SOURCE)["models"]):
        name=entry["model_id"];bins,weights=strata(entry)
        if not pilot[name] or entry["positive_demand_nodes"]==0 or name in ("Anytown","Todini2"):
            excluded[name]="pilot fizik kapısı" if not pilot[name] else "pozitif talep yok" if not entry["positive_demand_nodes"] else "önceden bilinen tanısal ağ"
            continue
        groups=["dev","dev","internal_holdout","internal_holdout"] if name=="Net2" else ["external_holdout"]*3
        used={frozenset(f["pipe_id"] for f in t["scenario"]["failures"]) for t in pilot_inputs if t["model_id"]==name}
        rng=random.Random(2026112002+i)
        for index,group in enumerate(groups,1):
            for _ in range(1000):
                ids=[rng.choice(b) for b in bins]
                if frozenset(ids) not in used:break
            else:raise ValueError("Bağımsız farklı arıza kümesi bulunamadı")
            used.add(frozenset(ids));rng.shuffle(ids)
            for crews in (1,2):
                matrix.append(case(entry,group,f"{name}_G{index}_C{crews}",ids,weights,crews,"comparison"))
    write(INPUTS,{"plan":"s02-v1","registered_local":datetime.now().astimezone().isoformat(),"seed":2026112002,
        "models_excluded":excluded,"budgets":[6,12],"cases":matrix,"limit_s":LIMIT,"recover_service":"not_evaluated"})
    files=["PROTOKOL.md","PROTOKOL_GIRDILERI.json","SOURCE_MANIFEST.json","PILOT_TASARIMI.md","PILOT_GIRDILERI.json","PILOT_SONUCU.json","AG_FIZIK_KABULU_S02.csv"]
    write(LOCK,{"registered_local":datetime.now().astimezone().isoformat(),"files":{p:sha(OUT/p) for p in files}})
    print("Kilit",sha(LOCK),"Koşullar",len(matrix))


def run(label):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}",label):raise ValueError("Geçersiz koşu seçimi")
    cases=lockcheck()["cases"]
    if label!="all":cases=[t for t in cases if t["case_id"]==label or t["group"]==label]
    if not cases:raise ValueError("Kayıtlı koşul yok")
    batch=uuid4().hex; indices=[]
    for task in cases:
        result=job(task,batch)
        indices.append({"case_id":task["case_id"],"record_id":result["run_id"],"status":result["status"]})
    write(OUT/"SERILER"/(batch+".json"),{"id":batch,"selector":label,"cases":indices})


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["pilots","register","run","worker"])
    p.add_argument("id",nargs="?")
    args=p.parse_args()
    if args.action=="pilots":pilots()
    elif args.action=="register":register()
    elif args.action=="run":run(args.id or "all")
    elif args.id and re.fullmatch("[0-9a-f]{32}",args.id):child(OUT/"KOSULAR"/args.id)
    else:p.error("Geçerli iş kimliği gerekli.")

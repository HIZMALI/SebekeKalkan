"""SPRINT 01: pilot, register, run the locked matrix, or reproduce one registered case."""
import argparse
from datetime import datetime
from itertools import product
from pathlib import Path
import json
import os
import random
import re
import subprocess
import sys
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

from sebekekalkan_core.contracts_v2 import ScenarioV2
from sebekekalkan_core.networks import eligible_pipes
from sebekekalkan_core.research_s01 import (
    METRICS_VERSION, MODEL_IDS, ROOT, RUNS, SOLVER, SPRINT, code_revision, evaluate, load_model, model_record,
    read_record, sha, utc, write_record,
)
from sprint01_sources import save_csv

SEEDS = {"Net2": 20261120, "Anytown": 20261121, "Todini2": 20261122}
LIMIT = 180
PROTOCOL = SPRINT / "PROTOKOL_ONCEDEN_KAYDEDILDI.md"
MATRIX = SPRINT / "PROTOKOL_V1_GIRDILERI.json"
LOCK = SPRINT / "PROTOKOL_V1_LOCK.json"


def rank_inputs(model):
    ranked = sorted((model.get_link(name) for name in eligible_pipes(model)),
                    key=lambda pipe: (-pipe.diameter, -pipe.length, pipe.name))
    if len(ranked) < 3:
        raise ValueError("Üç uygun boru bulunamadı.")
    n = len(ranked)
    bins = [[pipe.name for pipe in ranked[i*n//3:(i+1)*n//3]] for i in range(3)]
    nodes = sorted(((name, j.base_demand) for name, j in model.junctions() if j.base_demand > 0),
                   key=lambda item: (-item[1], item[0]))
    weights = dict(zip((name for name, _ in nodes[:2]), (3, 2)))
    return bins, weights


def task(entry, mode, case_id, pipes, weights, crews=1, step=15):
    scenario = ScenarioV2(name=case_id, failures=[{"pipe_id": p, "repair_hours": h}
                         for p, h in zip(pipes, (2, 3, 4))], crews=crews, failure_start_hour=2,
                         horizon_hours=16, step_minutes=step, required_pressure_m=20, low_pressure_m=15,
                         critical_weights=weights)
    return {"mode": mode, "case_id": case_id, "model_id": entry["model_id"],
            "model_sha256": entry["working_sha256"], "scenario": scenario.model_dump()}


def stop_tree(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
    else:
        process.kill()
    process.wait(timeout=10)


def directory(run_id):
    if not re.fullmatch("[0-9a-f]{32}", run_id):
        raise ValueError("Geçersiz koşu kimliği.")
    base = RUNS.resolve()
    if not base.is_relative_to(SPRINT.resolve()):
        raise ValueError("Koşu dizini SPRINT01 dışında.")
    path = (base / run_id).resolve()
    if path.parent != base:
        raise ValueError("Geçersiz koşu yolu.")
    return path


def run_case(data, revision, parent):
    run_id = uuid4().hex
    folder = directory(run_id)
    folder.mkdir(parents=True, exist_ok=False)
    payload = {**data, "run_id": run_id, "code_revision": revision,
               "solver_version": SOLVER, "metrics_version": METRICS_VERSION, "started_utc": utc()}
    payload["scenario_sha256"] = sha(json.dumps(data["scenario"], sort_keys=True, ensure_ascii=True,
                                               separators=(",", ":"), allow_nan=False).encode("ascii"))
    write_record(folder / "task.json", payload)
    started = time.perf_counter()
    outcome = {"status": "WORKER_ERROR", "oracle_verified": False}
    env = dict(os.environ, PYTHONUTF8="1", MPLCONFIGDIR=str(ROOT / ".cache/matplotlib"))
    with (folder / "worker.log").open("wb") as log:
        process = subprocess.Popen([sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "worker", run_id],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            returncode = process.wait(timeout=LIMIT)
            worker_result = folder / "worker-result.json"
            if returncode == 0 and worker_result.is_file():
                outcome = read_record(worker_result)
            else:
                outcome["worker_exit_code"] = returncode
        except subprocess.TimeoutExpired:
            stop_tree(process)
            outcome = {"status": "TIMEOUT", "oracle_verified": False, "limit_seconds": LIMIT}
        except KeyboardInterrupt:
            stop_tree(process)
            write_record(folder / "interrupted.json", {"run_id": run_id, "finished_utc": utc()})
            raise
    if "trials" not in outcome:
        outcome["trials"] = [read_record(path) for path in sorted(folder.glob("*.json"))
                             if re.fullmatch(r"(baseline|single|triple)(-fresh)?|(?:single|candidate|oracle)-\d+", path.stem)]
    result = {**payload, **outcome, "finished_utc": utc(), "elapsed_seconds": time.perf_counter() - started,
              "record_path": (folder / "result.json").relative_to(SPRINT).as_posix(), "batch_id": parent}
    write_record(folder / "result.json", result)
    print(f"{data['case_id']}: {result['status']} {result['elapsed_seconds']:.2f}s {run_id}", flush=True)
    return result


def pilots():
    batch = uuid4().hex
    revision = code_revision()["sha256"]
    summary = []
    outcomes = {}
    for name in MODEL_IDS:
        entry = model_record(name)
        groups, weights = rank_inputs(load_model(entry))
        trio = [group[len(group)//2] for group in groups]
        outcomes[name] = {"pilot_triple": trio, "status": {}}
        prior_pass = True
        for mode, pipes in [("baseline", [trio[1]]), ("single", [trio[1]]), ("triple", trio)]:
            inputs = task(entry, mode, f"{name}-{mode}", pipes, weights)
            result = run_case(inputs, revision, batch) if prior_pass else {"status": "NOT_RUN_PRIOR_GATE"}
            outcomes[name]["status"][mode] = result["status"]
            row = next((r for r in result.get("trials", []) if r["status"] != "PASS"),
                       next(iter(result.get("trials", [])), {}))
            extra = row.get("additional_gate", {})
            summary.append({
                "model_id": name, "phase": mode, "status": result["status"],
                "run_id": result.get("run_id"), "converged": row.get("converged"),
                "r1_gate": row.get("r1_gate", {}).get("pass"), "fresh_verified": result.get("oracle_verified"),
                "elapsed_seconds": result.get("elapsed_seconds"), "scenario_sha256": result.get("scenario_sha256"),
                "model_sha256": entry["working_sha256"], "pipes": pipes if mode != "baseline" else [],
                "raw_min_junction_pressure_m": extra.get("raw_min_junction_pressure_m"),
                "source_free_junction_event_samples": extra.get("source_free_junction_event_samples"),
                "reason": row.get("error") or extra.get("unsupported_hydraulics") or
                          ("Önceki pilot aşaması geçmedi." if not prior_pass else result["status"]),
                "record_path": result.get("record_path"),
            })
            prior_pass = result["status"] == "PASS"
    save_csv(SPRINT / "AG_FIZIK_KABULU.csv", summary)
    write_record(SPRINT / "PILOT_V1.json", {"batch_id": batch, "selection_order": MODEL_IDS, "models": outcomes})


def register():
    pilot = read_record(SPRINT / "PILOT_V1.json")
    accepted = [name for name in MODEL_IDS if set(pilot["models"][name]["status"].values()) == {"PASS"}][:2]
    main = []
    sensitivity = []
    strata = {}
    for name in accepted:
        entry = model_record(name)
        groups, weights = rank_inputs(load_model(entry))
        strata[name] = {"seed": SEEDS[name], "tiers": groups, "critical_weights": weights}
        excluded = set(pilot["models"][name]["pilot_triple"])
        population = [ids for ids in product(*groups) if set(ids) != excluded]
        rng = random.Random(SEEDS[name])
        for i, ids in enumerate(rng.sample(population, min(3, len(population))), start=1):
            fifo = list(ids)
            rng.shuffle(fifo)
            for crews in (1, 2, 3):
                main.append(task(entry, "main", f"{name}_S{i}_C{crews}", fifo, weights, crews))
            if i == 1 and name == accepted[0]:
                for step in (5, 30, 60):
                    sensitivity.append(task(entry, "main", f"{name}_S1_C2_{step}dk", fifo, weights, 2, step))
    payload = {"version": "S01-v1", "models": accepted, "strata": strata,
               "main": main, "sensitivity": sensitivity, "code_revision": code_revision()}
    write_record(MATRIX, payload)
    at = datetime.now(ZoneInfo("Europe/Istanbul")).isoformat()
    template = (ROOT / "scripts/sprint01_protocol.md").read_text(encoding="utf-8")
    with PROTOCOL.open("x", encoding="utf-8", newline="\n") as out:
        out.write(template.format(at=at, models=", ".join(accepted) or "yok",
                                  count=len(main), matrix_sha=sha(MATRIX.read_bytes())))
    paths = [PROTOCOL, MATRIX, SPRINT / "SOURCE_MANIFEST.json", SPRINT / "PILOT_V1.json"]
    write_record(LOCK, {"registered_at": at, "files": {p.name: sha(p.read_bytes()) for p in paths}})
    print(f"{at} | {accepted} | {len(main)} ana koşul | protokol SHA-256 {sha(PROTOCOL.read_bytes())}")


def locked_matrix():
    lock = read_record(LOCK)
    for path in (PROTOCOL, MATRIX, SPRINT / "SOURCE_MANIFEST.json", SPRINT / "PILOT_V1.json"):
        if sha(path.read_bytes()) != lock["files"][path.name]:
            raise ValueError(f"Kilitli dosya değişmiş: {path.name}")
    matrix = read_record(MATRIX)
    if matrix["code_revision"] != code_revision():
        raise ValueError("Kilitli çözücü kodu değişmiş.")
    return matrix


def run(stage, case_id):
    matrix = locked_matrix()
    candidates = matrix["main"] + matrix["sensitivity"] if stage == "replay" else matrix[stage]
    if stage == "replay":
        candidates = [item for item in candidates if item["case_id"] == case_id]
        if not candidates:
            raise ValueError("Kayıtlı koşu kimliği bulunamadı.")
    batch = uuid4().hex
    index = SPRINT / "KOSULAR/v1" / f"{stage}-{batch}.json"
    paths = []
    for item in candidates:
        result = run_case(item, matrix["code_revision"]["sha256"], batch)
        paths.append(result["record_path"])
    write_record(index, {"batch_id": batch, "stage": stage, "started_with_cases": [i["case_id"] for i in candidates],
                         "result_paths": paths, "finished_utc": utc()})
    print(index, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("pilots", "register", "main", "sensitivity", "replay", "worker"))
    parser.add_argument("identifier", nargs="?")
    args = parser.parse_args()
    if args.command == "worker":
        folder = directory(args.identifier or "")
        write_record(folder / "worker-result.json", evaluate(read_record(folder / "task.json"), folder))
    elif args.command == "pilots":
        pilots()
    elif args.command == "register":
        register()
    else:
        run(args.command, args.identifier)


if __name__ == "__main__":
    main()

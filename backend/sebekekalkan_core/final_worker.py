"""Isolated adapter to the unchanged Sprint 02 comparison and physics engine."""
import json
import os
from pathlib import Path
import sys

from . import s02_comparison, s02_search
from .final_records import MANIFEST, Records, metrics, require
from .networks import ROOT
from .s02_evidence import independent_metrics
from .s02_physics import Laboratory, METHOD_VERSION, ScenarioS02, code_id, identity, same_metrics, sha, write

METHODS = ("fifo", "greedy", "s02_b6")
TIMEOUT = 180
MODELS = {"Net2": "Net2.inp", "Skeletonize": "skeletonize.inp"}
LOCKED_ENGINE = "a6cac10d72bc099230b0b5997d4ca94b0f42a8cb88016a35b8ee6c8ce668475a"
JOBS = ROOT / ".calisma/final_live"
SOLVER = "WNTRSimulator 1.5.0 / basınca bağlı talep"


def diagnostic():
    return os.environ.get("SEBEKE_FINAL_DIAGNOSTIC_WNTR_FAILURE") == "1"


def protocol(records):
    manifest = records.manifest()
    lock_hash = manifest["PROTOKOL_LOCK.json"]
    lock = records.json("SPRINT02/PROTOKOL_LOCK.json", lock_hash)
    settings = records.json("SPRINT02/PROTOKOL_GIRDILERI.json", lock["files"]["PROTOKOL_GIRDILERI.json"])
    require(settings["plan"] == "s02-v1" and settings["limit_s"] == TIMEOUT and settings["budgets"] == [6, 12],
            "Protokol bütçesi veya süresi uyuşmuyor.")
    tasks = {t["case_id"]: t for t in settings["cases"] if t["model_id"] in MODELS}
    return tasks, lock, lock_hash


def packet(case):
    records = Records()
    tasks, lock, lock_hash = protocol(records)
    task = tasks[case]
    models = records.json("SPRINT02/SOURCE_MANIFEST.json", lock["files"]["SOURCE_MANIFEST.json"])
    entry = next(m for m in models["models"] if m["model_id"] == task["model_id"])
    require(entry["filename"] == MODELS[task["model_id"]] and task["model_sha256"] == entry["original_sha256"]
            == entry["working_sha256"] and task["scenario_sha256"] == identity(task["scenario"]),
            "Kilitli model veya senaryo uyuşmuyor.")
    records.bytes(f"SPRINT02/MODELLER/{entry['filename']}", task["model_sha256"])
    records.bytes("SPRINT02/MODELLER/WNTR-LICENSE.md", entry["license_sha256"])
    source = code_id(ROOT / "scripts/sprint02.py", ROOT / "scripts/sprint02_sources.py",
                     Path(s02_search.__file__), Path(s02_comparison.__file__))
    require(source == LOCKED_ENGINE, "Sprint 02 hesaplama motorunun kaynak özeti uyuşmuyor.")
    actual = dict(task["scenario"])
    if diagnostic():
        actual["wntr_max_iterations"] = 1
    scenario = ScenarioS02.model_validate(actual)
    require(len(scenario.failures) == 4 and scenario.manual_order is None and scenario.step_minutes == 15
            and scenario.horizon_hours == 24 and 1 <= scenario.crews <= 2, "Canlı senaryo sınır dışında.")
    exact_input = {"model_id": task["model_id"], "case_id": case, "scenario": actual,
                   "network_sha256": task["model_sha256"], "method_version": METHOD_VERSION,
                   "methods": list(METHODS)}
    return {"input": exact_input, "input_sha256": identity(exact_input), "source_sha256": source,
            "adapter_sha256": sha(Path(__file__)), "protocol_sha256": lock_hash,
            "scenario_sha256": identity(actual), "entry": entry, "diagnostic": diagnostic()}


def calculate(folder):
    metadata = json.loads((folder / "input.json").read_text("utf-8"))
    require(metadata["job_id"] == folder.name and metadata["data"] == packet(metadata["data"]["input"]["case_id"]),
            "İş girdisi kaynağı uyuşmuyor.")
    p = metadata["data"]
    actual = p["input"]["scenario"]
    lab = Laboratory(p["entry"], ScenarioS02.model_validate(actual), folder, metadata)
    methods = {}
    for key in METHODS:
        selected = s02_comparison.execute(lab, key)
        if selected["status"] != "PASS":
            write(folder / "diagnostic.json", {"method": key, **selected})
            return 2
        records = {row["name"]: row for row in lab.records}
        row = records[selected["record"]]
        require(selected["physical_pass"] is True and len(selected["verification"]) == 2
                and all(records[name]["status"] == "PASS" for name in selected["verification"])
                and same_metrics(independent_metrics(folder, row, actual), selected["metrics"]),
                "Yeniden çözüm veya bağımsız ölçüm uyuşmuyor.")
        methods[key] = {"order": row["order"], "assignments": row["assignments"], "metrics": metrics(row),
                        "physical": {"hydraulic": row["r1"], "additional": row["extra"],
                                     "fresh_repeats": selected["verification"], "raw_sha256": row["raw_sha256"]}}
    require(all(row["status"] == "PASS" and len(row["calls"]) == 2 and
                all(c["solver_status"] == "returned" for c in row["calls"]) for row in lab.records),
            "Fizik çağrısı tamamlanmadı.")
    write(folder / "outcome.json", {"job_id": folder.name, "input_sha256": p["input_sha256"],
          "source_sha256": p["source_sha256"], "methods": methods, "trial_count": len(lab.records),
          "wntr_calls": sum(len(t["calls"]) for t in lab.records), "physical_pass": True})
    return 0


if __name__ == "__main__":
    identifier = sys.argv[1]
    if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
        raise SystemExit(3)
    raise SystemExit(calculate(JOBS / identifier))

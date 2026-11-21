"""SPRINT 02 research input and physical ledger. The three-fault API is unchanged."""
from contextlib import contextmanager
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import time
import traceback
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from pydantic import Field
import wntr

from . import hydraulics, hydraulics_v2
from .contracts import Failure
from .contracts_v2 import ScenarioV2
from .networks import ROOT
from .numerical_gates_r1 import read_frames
from .research_s01 import additional_gate

OUT = ROOT.parent / "SPRINT02"
MODELS = OUT / "MODELLER"
SOURCE = OUT / "SOURCE_MANIFEST.json"
METHOD_VERSION = "s02-restoration-1"
METRICS = ("weighted_unmet_volume_m3", "unmet_demand_volume_m3",
           "critical_low_pressure_node_hours", "repair_completion_hour")
ATOL, RTOL = 1e-6, 1e-8


class ScenarioS02(ScenarioV2):
    failures: list[Failure] = Field(min_length=1, max_length=4)
    crews: int = Field(default=1, ge=1, le=2, strict=True)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def identity(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                                     allow_nan=False).encode("ascii")).hexdigest()


def read(path):
    return Path(path).read_text(encoding="utf-8-sig")


def load(path):
    return json.loads(read(path))


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def csv_file(path, rows):
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def code_id(*modules):
    files = sorted({*modules, *(ROOT/"backend/sebekekalkan_core"/name for name in
                                ("hydraulics.py","hydraulics_v2.py","networks.py","numerical_gates_r1.py",
                                 "research_s01.py","contracts.py","contracts_v2.py","planning.py","sebeke.py",
                                 "s02_physics.py"))})
    return identity({p.relative_to(ROOT).as_posix():sha(p) for p in files})


def model_for_entry(entry):
    path = (MODELS/entry["filename"]).resolve()
    if (path.parent != MODELS.resolve() or path.suffix != ".inp" or not 0 < path.stat().st_size <= 2_000_000
        or path.stat().st_size != entry["bytes"] or sha(path) != entry["working_sha256"]
        or entry["working_sha256"] != entry["original_sha256"]
        or sha(MODELS/"WNTR-LICENSE.md") != entry["license_sha256"] or wntr.__version__ != "1.5.0"):
        raise ValueError("Model, lisans veya çözücü kimliği eşleşmedi.")
    return wntr.network.WaterNetworkModel(str(path))


def close(a,b):
    return abs(a-b) <= ATOL + RTOL * max(abs(a),abs(b))


def same_metrics(left,right):
    return all(close(left[k],right[k]) if k != "repair_completion_hour" else left[k]==right[k] for k in METRICS)


class Laboratory:
    """One serial child per case. Every real solver entry/return survives a worker timeout."""
    def __init__(self, entry, scenario, folder, meta):
        self.entry, self.scenario, self.folder, self.meta = entry, scenario, folder, meta
        self.model = model_for_entry(entry)
        hydraulics.validate_network(scenario,self.model)
        self.records = []
        self.events = folder/"solver.jsonl"
        self.events.touch(exist_ok=False)

    def log(self, **event):
        with self.events.open("a",encoding="utf8",newline="\n") as f:
            f.write(json.dumps({"at":utc(), **event},ensure_ascii=False,allow_nan=False)+"\n")

    def trial(self, name, assignments, order=()):
        original = wntr.sim.WNTRSimulator.run_sim
        calls = []
        def measured(sim, *args, **kwargs):
            seq = len(calls)+1
            self.log(op="begin", trial=name, seq=seq)
            w,c = time.perf_counter(),time.process_time()
            status = "exception"
            try:
                out = original(sim,*args,**kwargs)
                status = "returned" if not out.error_code else "error_code"
                return out
            finally:
                observed = {"seq":seq,"solver_status":status,"wall_s":time.perf_counter()-w,"cpu_s":time.process_time()-c}
                calls.append(observed)
                self.log(op="end",trial=name,**observed)
        w,c = time.perf_counter(),time.process_time()
        rel = name+".zip"
        summary = {"name":name,"order":list(order),"assignments":assignments, "raw":rel}
        with tempfile.TemporaryDirectory(dir=self.folder) as tmp:
            raw = Path(tmp)/"raw"
            try:
                with patch.object(hydraulics,"load_model",lambda:model_for_entry(self.entry)), \
                     patch.object(wntr.sim.WNTRSimulator,"run_sim",measured):
                    result=hydraulics_v2.simulate_checked(self.scenario,assignments,raw)
                extra=additional_gate(self.model,read_frames(raw/"internal_events"))
                # All raw heads, signed demand and flows are retained in the ZIP.
                write(raw/"s02-gate.json",extra)
                summary.update(status="PASS" if extra["pass"] else "PHYSICAL_INVALID",
                               r1=result["physical_gate"], extra=extra,
                               metrics={k:float(result["metrics"][k]) for k in METRICS},
                               warnings=result["solver_warnings_original"])
                if not extra["pass"]:
                    summary["reason"]="junction_mass_balance/closed_link/equipment/source_free"
            except Exception as exc:
                raw.mkdir(exist_ok=True)
                (raw/"exception.txt").write_text(traceback.format_exc(),encoding="utf8")
                gate=load(raw/"physical-gate.json") if (raw/"physical-gate.json").is_file() else {}
                status="PHYSICAL_INVALID" if gate.get("converged") else "SOLVER_ERROR" if calls else "WORKER_ERROR"
                summary.update(status=status,r1=gate,reason=str(exc),cause=repr(exc.__cause__))
            with ZipFile(self.folder/rel,"x",compression=ZIP_DEFLATED,compresslevel=1) as archive:
                for path in sorted(raw.rglob("*")):
                    if path.is_file():archive.write(path,path.relative_to(raw).as_posix())
        summary.update(calls=calls,wall_s=time.perf_counter()-w,cpu_s=time.process_time()-c,
                       raw_sha256=sha(self.folder/rel))
        self.records.append(summary)
        write(self.folder/(name+".json"),summary)
        return summary

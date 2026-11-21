"""Strict user input and immutable model identities for the isolated V4 worker."""
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import s02_comparison, s02_search
from .final_records import Diagram, Records, diagram, require
from .final_worker import LOCKED_ENGINE, MODELS, protocol
from .hydraulics import validate_network
from .networks import AnalysisError, ROOT, eligible_pipes
from .s02_physics import METHOD_VERSION, ScenarioS02, code_id, identity, model_for_entry, sha

JOBS = ROOT / ".calisma/v4"
MODE = "LIVE_USER_SCENARIO"
VERSION = "final-v4-user-1"
Network = Literal["Net2", "Skeletonize"]


class Fault(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    pipe_id: str = Field(min_length=1, max_length=24, pattern=r"^[a-zA-Z0-9_-]+$")
    repair_hours: int = Field(ge=2, le=5)


class CustomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    network: Network
    faults: list[Fault] = Field(min_length=3, max_length=4)
    crews: int = Field(ge=1, le=2)
    search: Literal["fast", "comprehensive"] = "fast"

    @model_validator(mode="after")
    def unique(self):
        if len({fault.pipe_id for fault in self.faults}) != len(self.faults):
            raise ValueError("Aynı boru iki kez seçilemez.")
        if self.search == "comprehensive" and len(self.faults) != 4:
            raise ValueError("24 sıra taraması dört arızalı senaryolar içindir.")
        return self


@dataclass
class ModelSource:
    entry: dict
    chart: Diagram
    eligible: set[str]
    weights: dict[str, float]
    lock_sha256: str
    model: object


def model_source(network):
    records = Records()
    tasks, locked, digest = protocol(records)
    manifest = records.json("SPRINT02/SOURCE_MANIFEST.json", locked["files"]["SOURCE_MANIFEST.json"])
    entry = next(x for x in manifest["models"] if x["model_id"] == network)
    require(entry["filename"] == MODELS[network] and entry["original_sha256"] == entry["working_sha256"],
            "Model adı veya SHA-256 eşleşmiyor.")
    raw = records.bytes("SPRINT02/MODELLER/" + entry["filename"], entry["original_sha256"])
    records.bytes("SPRINT02/MODELLER/WNTR-LICENSE.md", entry["license_sha256"])
    own = [t for t in tasks.values() if t["model_id"] == network]
    weights = own[0]["scenario"]["critical_weights"]
    require(all(t["scenario"]["critical_weights"] == weights and t["model_sha256"] == entry["original_sha256"]
                for t in own), "Model ön kaydının fizik ayarları uyuşmuyor.")
    model = model_for_entry(entry)
    chart = diagram(raw)
    eligible = set(chart.pipes) & eligible_pipes(model)
    require(len(eligible) >= 4 and weights.keys() <= chart.nodes.keys(), "Ağ seçime uygun değil.")
    return ModelSource(entry, chart, eligible, weights, digest, model)


def revisions():
    engine = code_id(ROOT / "scripts/sprint02.py", ROOT / "scripts/sprint02_sources.py",
                     Path(s02_search.__file__), Path(s02_comparison.__file__))
    require(engine == LOCKED_ENGINE, "Kilitli Sprint 02 çözücü kaynağı değişti.")
    folder = Path(__file__).parent
    files = ("final_v4_custom_api.py", "final_v4_custom_input.py", "final_v4_custom_worker.py",
             "final_v4_trace.py", "decision_policy_v2.py")
    return engine, identity({name: sha(folder / name) for name in files})


def prepare(request, diagnostic=False):
    source = model_source(request.network)
    if any(f.pipe_id not in source.eligible for f in request.faults):
        raise AnalysisError("Bir boru doğrulanmış ağda yok veya izolasyona uygun değil.")
    scenario = ScenarioS02(
        name=f"{request.network} V4 kullanıcı senaryosu", failures=[f.model_dump() for f in request.faults],
        crews=request.crews, failure_start_hour=2, horizon_hours=24, step_minutes=15, low_pressure_m=15,
        required_pressure_m=20, critical_weights=source.weights, wntr_max_iterations=1 if diagnostic else 3000,
    )
    validate_network(scenario, source.model)
    engine, code = revisions()
    physical = scenario.model_dump(mode="json")
    inputs = {"model": request.network, "network_sha256": source.entry["original_sha256"],
              "search": request.search, "scenario": physical, "mode": MODE}
    p = {"request": request.model_dump(mode="json"), "inputs": inputs, "input_sha256": identity(inputs),
         "scenario_sha256": identity(physical), "source_sha256": engine, "code_sha256": code,
         "network_sha256": source.entry["original_sha256"], "protocol_sha256": source.lock_sha256,
         "diagnostic": diagnostic, "version": VERSION,
         "method_version": "decision_policy_v2" if len(request.faults) == 3 else METHOD_VERSION}
    return p, source


def diagnostic_enabled():
    # A separate server process can exercise a real WNTR failure without exposing this as a setting.
    return os.environ.get("SEBEKE_V4_DIAGNOSTIC_WNTR_FAILURE") == "1"

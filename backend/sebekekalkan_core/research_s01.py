"""Local SPRINT 01 research solver, independent of the product API."""
from datetime import datetime, timezone
from itertools import permutations
from pathlib import Path
import hashlib
import json
import time
import traceback
from unittest.mock import patch

import networkx as nx
import numpy as np
import wntr

from . import hydraulics, hydraulics_v2, numerical_gates_r1, planning_v2
from .contracts_v2 import ScenarioV2
from .decision_policy_v2 import evaluate_methods, select
from .networks import ROOT
from .planning import objective, oracle_schedule, schedule

SPRINT = ROOT.parent / "SPRINT01"
RUNS = SPRINT / "KOSULAR/v1"
MODEL_IDS = ("Net2", "Anytown", "Todini2")
ALLOWED_LICENSE = "Revised BSD (WNTR dağıtımı ve beraberindeki bildirim)"
MAX_MODEL_BYTES = 2_000_000
SOLVER = "WNTRSimulator 1.5.0"
METRICS_VERSION = "SK-v2-S01-1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_record(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as out:
        json.dump(data, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write("\n")


def read_record(path):
    return json.loads(path.read_text(encoding="utf-8"))


def code_revision():
    modules = ("research_s01", "contracts", "contracts_v2", "networks", "hydraulics",
               "hydraulics_v2", "numerical_gates_r1", "planning", "planning_v2", "decision_policy_v2")
    folder = Path(__file__).resolve().parent
    files = [folder / f"{name}.py" for name in modules]
    files.append(ROOT / "scripts/sprint01.py")
    hashes = {path.relative_to(ROOT).as_posix(): sha(path.read_bytes()) for path in files}
    return {"sha256": sha(json.dumps(hashes, sort_keys=True).encode()), "files": hashes}


def model_record(model_id):
    if model_id not in MODEL_IDS:
        raise ValueError("Katalogdaki pilot ağ kimliklerinden birini seçin.")
    entry = next(row for row in read_record(SPRINT / "SOURCE_MANIFEST.json")["models"] if row["model_id"] == model_id)
    if not entry["selected_for_pilot"] or entry["license"] != ALLOWED_LICENSE:
        raise ValueError("Ağ doğrulanmış kaynak ve lisans listesinde yok.")
    return entry


def load_model(entry):
    if wntr.__version__ != "1.5.0":
        raise ValueError("Bu koşu için WNTR 1.5.0 gerekli.")
    allowed = (SPRINT / "MODELLER/v1/orijinal").resolve()
    path = (SPRINT / entry["local_path"]).resolve()
    if path.parent != allowed or path.suffix.lower() != ".inp":
        raise ValueError("Beklenmeyen model yolu veya dosya türü.")
    notice = (allowed / "WNTR-LICENSE.md").resolve()
    if notice.parent != allowed or sha(notice.read_bytes()) != entry["license_notice_sha256"]:
        raise ValueError("Modelle birlikte kayıtlı lisans bildirimi bozulmuş.")
    size = path.stat().st_size
    if not 0 < size <= MAX_MODEL_BYTES or size != entry["bytes"]:
        raise ValueError("Model dosyası boyutu kayıtla eşleşmiyor.")
    data = path.read_bytes()
    if sha(data) != entry["working_sha256"] or entry["working_sha256"] != entry["original_sha256"]:
        raise ValueError("Model dosyası SHA-256 doğrulaması başarısız.")
    sections = {line.partition(";")[0].strip().upper() for line in data.decode("utf-8-sig").splitlines()}
    if b"\0" in data or not {"[JUNCTIONS]", "[PIPES]", "[OPTIONS]", "[END]"} <= sections:
        raise ValueError("Geçerli EPANET INP bölümleri bulunamadı.")
    return wntr.network.WaterNetworkModel(str(path))


def additional_gate(model, frames):
    flows = frames["flowrate"]
    status = frames["status"].to_numpy()
    demands = frames["demand"]
    junctions = model.junction_name_list
    flow_values = flows.to_numpy()
    net = demands[junctions].to_numpy(copy=True)
    index = {name: i for i, name in enumerate(junctions)}
    links = [model.get_link(name) for name in flows.columns]
    for column, link in enumerate(links):
        if link.start_node_name in index:
            net[:, index[link.start_node_name]] += flow_values[:, column]
        if link.end_node_name in index:
            net[:, index[link.end_node_name]] -= flow_values[:, column]
    max_balance = float(np.max(np.abs(net), initial=0))
    max_closed = float(np.max(np.abs(flow_values[status == 0]), initial=0))
    equipment = {}
    equipment_ok = True
    for name in model.pump_name_list + model.valve_name_list:
        link = model.get_link(name)
        states = frames["status"][name].to_numpy()
        q = flows[name].to_numpy()
        head_gain = frames["head"][link.end_node_name].to_numpy() - frames["head"][link.start_node_name].to_numpy()
        pump = name in model.pump_name_list
        active = q > 1e-7
        equipment_ok &= bool(np.isin(states, [0, 1, 2]).all())
        if pump:
            equipment_ok &= bool(np.min(q, initial=0) >= -1e-7 and np.min(head_gain[active], initial=0) >= -0.001)
        equipment[name] = {
            "type": link.link_type, "status_codes": sorted({int(s) for s in states}),
            "status_transitions": int(np.count_nonzero(np.diff(states))),
            "minimum_flow_m3s": float(np.min(q)), "maximum_flow_m3s": float(np.max(q)),
            "minimum_head_gain_m": float(np.min(head_gain)), "maximum_head_gain_m": float(np.max(head_gain)),
        }

    disconnected = 0
    max_disconnected_demand = 0.0
    fixed = set(model.reservoir_name_list + model.tank_name_list)
    actual = demands[junctions].to_numpy()
    by_state = {}
    for row, flags in enumerate(status != 0):
        key = flags.tobytes()
        if key not in by_state:
            graph = nx.Graph()
            graph.add_nodes_from(model.node_name_list)
            graph.add_edges_from((link.start_node_name, link.end_node_name) for link, open_ in zip(links, flags) if open_)
            by_state[key] = tuple(nx.connected_components(graph))
        injectors = {n for n, q in zip(junctions, actual[row]) if q < -2e-6}
        for component in by_state[key]:
            if component & (fixed | injectors):
                continue
            cols = [index[n] for n in component if n in index]
            disconnected += len(cols)
            max_disconnected_demand = max(max_disconnected_demand, float(np.max(actual[row, cols], initial=0)))
    return {
        "pass": max_balance <= 2e-6 and max_closed < 1e-7 and equipment_ok and max_disconnected_demand <= 2e-6,
        "junction_mass_balance_max_m3s": max_balance,
        "closed_link_max_abs_flow_m3s": max_closed,
        "equipment_pass": equipment_ok, "equipment": equipment,
        "source_free_junction_event_samples": disconnected,
        "source_free_max_positive_delivery_m3s": max_disconnected_demand,
        "raw_min_junction_pressure_m": float(frames["pressure"][junctions].min().min()),
        "reservoir_count": model.num_reservoirs, "tank_count": model.num_tanks,
        "positive_delivery_in_zero_demand_island_limit_m3s": 2e-6,
    }


def run_trial(entry, model, scenario, assignments, folder):
    try:
        # Only this short-lived child replaces the loader. The API always uses pinned Net3.
        with patch.object(hydraulics, "load_model", lambda: load_model(entry)):
            result = hydraulics_v2.simulate_checked(scenario, assignments, folder)
        extra = additional_gate(model, numerical_gates_r1.read_frames(folder / "internal_events"))
        unsupported = entry["unsupported_hydraulics"]
        extra["unsupported_hydraulics"] = unsupported
        extra["pass"] = extra["pass"] and not unsupported
        write_record(folder / "s01-gate.json", extra)
        status = "PASS" if extra["pass"] else "PHYSICAL_INVALID"
        return {"status": status, "converged": True, "assignments": assignments,
                "physical_valid": extra["pass"], "r1_gate": result["physical_gate"], "additional_gate": extra,
                "metrics": result["metrics"], "solver_warnings": result["solver_warnings_original"],
                **{key: result[key] for key in ("times_seconds", "unmet_demand_m3s", "expected_customer_demand_m3s",
                                               "delivered_customer_demand_m3s", "minimum_junction_pressure_m")}}
    except Exception as error:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        path = folder / "physical-gate.json"
        gate = read_record(path) if path.is_file() else {}
        return {"status": "PHYSICAL_INVALID" if gate.get("converged") else "SOLVER_ERROR",
                "converged": gate.get("converged", False), "physical_valid": False, "assignments": assignments,
                "r1_gate": gate, "error": str(error), "cause": repr(error.__cause__)}


def evaluate(task, folder):
    entry = model_record(task["model_id"])
    if task["model_sha256"] != entry["working_sha256"]:
        raise ValueError("Kilitli işin model SHA-256 değeri değişmiş.")
    model = load_model(entry)
    scenario = ScenarioV2.model_validate(task["scenario"])
    hydraulics.validate_network(scenario, model)
    trials = []

    def trial(key, assigned, order=None):
        started = time.perf_counter()
        result = run_trial(entry, model, scenario, assigned, folder / key)
        record = {"key": key, "order": order, "elapsed_seconds": time.perf_counter() - started, **result}
        trials.append(record)
        write_record(folder / f"{key}.json", record)
        print(f"{task['case_id']} {key} {result['status']}", flush=True)
        return record

    ids = [fault.pipe_id for fault in scenario.failures]
    mode = task["mode"]
    if mode != "main":
        outcome = trial(mode, [] if mode == "baseline" else schedule(scenario, ids), ids)
        reference = None
        if outcome["status"] == "PASS":
            reference = trial(mode + "-fresh", [] if mode == "baseline" else oracle_schedule(scenario, ids), ids)
        matched = bool(reference and reference["status"] == "PASS" and np.allclose(
            objective(outcome), objective(reference), rtol=1e-8, atol=1e-6))
        failed = next((row for row in trials if row["status"] != "PASS"), None)
        return {"status": failed["status"] if failed else "PASS" if matched else "ORACLE_MISMATCH",
                "oracle_verified": matched, "trials": trials}

    base = trial("baseline", [])
    if base["status"] != "PASS":
        return {"status": base["status"], "oracle_verified": False, "trials": trials}
    singles = [trial(f"single-{i}", [{"pipe_id": fault.pipe_id, "crew": 1,
                                     "starts_at_h": scenario.failure_start_hour,
                                     "ends_at_h": scenario.horizon_hours}], [fault.pipe_id])
               for i, fault in enumerate(scenario.failures)]
    candidates = {order: trial(f"candidate-{i}", schedule(scenario, order), list(order))
                  for i, order in enumerate(permutations(ids))}
    oracles = {order: trial(f"oracle-{i}", oracle_schedule(scenario, order), list(order))
               for i, order in enumerate(permutations(sorted(ids)))}
    failed = {row["status"] for row in trials} - {"PASS"}
    if failed:
        return {"status": "PHYSICAL_INVALID" if "PHYSICAL_INVALID" in failed else "SOLVER_ERROR",
                "trial_failure_types": sorted(failed), "oracle_verified": False, "trials": trials}
    if any(candidates[order]["assignments"] != row["assignments"] or not np.allclose(
            objective(candidates[order]), objective(row), rtol=1e-8, atol=1e-6) for order, row in oracles.items()):
        return {"status": "ORACLE_MISMATCH", "oracle_verified": False, "trials": trials}
    pool = [{"order": order, "objective": objective(row), "status": "completed"} for order, row in candidates.items()]
    oracle = select([{"order": order, "objective": objective(row), "status": "completed"} for order, row in oracles.items()])
    decision = select(pool)
    if not planning_v2.reference_matches(decision, oracle):
        return {"status": "ORACLE_MISMATCH", "oracle_verified": False, "trials": trials}
    baseline = base["metrics"]["weighted_unmet_volume_m3"]
    scores = {fault.pipe_id: (row["metrics"]["weighted_unmet_volume_m3"] - baseline) / fault.repair_hours
              for fault, row in zip(scenario.failures, singles, strict=True)}
    orders = {"fifo": ids, "greedy": sorted(ids, key=lambda pipe: (-scores[pipe], pipe)),
              "proposal": decision["selected"]["order"]}
    methods = {name: candidates[tuple(order)] for name, order in orders.items()}
    return {"status": "PASS", "oracle_verified": True, "trials": trials, "decision": decision,
            "greedy_scores": scores, "methods": methods, "classification": evaluate_methods(pool, orders)["methods"]}

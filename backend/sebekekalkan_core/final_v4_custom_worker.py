"""Drive the locked laboratory inside one isolated, bounded process."""
from itertools import permutations
from pathlib import Path
import re
import sys
import time

from . import decision_policy_v2
from . import s02_comparison as locked
from .final_records import metrics, require
from .final_v4_custom_input import CustomRequest, JOBS, MODE, diagnostic_enabled, prepare
from .final_v4_trace import read_trace
from .planning import objective, oracle_schedule
from .s02_evidence import independent_metrics
from .s02_physics import Laboratory, METRICS, ScenarioS02, load, same_metrics, sha, write


class TrialFailed(ValueError):
    def __init__(self, result):
        self.result = result
        super().__init__(result["status"])


def passed(result):
    if result["status"] != "PASS":
        raise TrialFailed(result)
    return result


def v2_three(lab):
    ids = sorted(fault.pipe_id for fault in lab.scenario.failures)
    orders = list(permutations(ids))
    candidates = [passed(locked.observed(lab, f"v2-candidate{i:02}", order))
                  for i, order in enumerate(orders, 1)]
    repeats = [passed(lab.trial(f"v2-oracle{i:02}", oracle_schedule(lab.scenario, order), order))
               for i, order in enumerate(orders, 1)]

    def select(rows):
        return decision_policy_v2.select([{"status": "completed", "order": m["order"], "objective": objective(m)}
                                         for m in rows])["selected"]["order"]

    best = select(candidates)
    if best != select(repeats) or any(a["assignments"] != b["assignments"] or not same_metrics(a["metrics"], b["metrics"])
                                     for a, b in zip(candidates, repeats, strict=True)):
        raise TrialFailed({"status": "ORACLE_MISMATCH", "failed_trial": "v2-oracle"})
    candidate = next(row for row in candidates if row["order"] == best)
    return {**passed(locked.verified(lab, "v2", candidate)), "budget": len(orders), "unique_candidates": len(orders)}


def compute(lab, search):
    methods, costs = {}, {}
    keys = ("fifo", "greedy", "proposal") if len(lab.scenario.failures) == 3 else ("fifo", "greedy", "s02_b6")
    if search == "comprehensive":
        keys += ("oracle",)
    oracle_rows = []
    for key in keys:
        offset = len(lab.records)
        wall, cpu = time.perf_counter(), time.process_time()
        if key == "proposal":
            method = v2_three(lab)
        elif key == "oracle":
            method, oracle_rows = locked.exhaustive(lab)
        else:
            method = locked.execute(lab, key)
        methods[key] = passed(method)
        costs[key] = locked.cost(lab.records[offset:], time.perf_counter()-wall, time.process_time()-cpu)
    if oracle_rows:
        by_order = {tuple(row["order"]): row for row in oracle_rows}
        for method in methods.values():
            if not same_metrics(method["metrics"], by_order[tuple(method["order"])]["metrics"]):
                raise TrialFailed({"status": "ORACLE_MISMATCH", "failed_trial": "oracle"})
    return methods, costs


def method_proof(folder, selected, all_trials, scenario, chart):
    trials = [all_trials[name] for name in (selected["record"], *selected["verification"])]
    require(len({row["name"] for row in trials}) == 3 and selected["physical_pass"] is True,
            "Seçili planın taze doğrulaması eksik.")
    first = trials[0]
    receipts = []
    for row in trials:
        require(row["order"] == selected["order"] and row["assignments"] == first["assignments"]
                and same_metrics(row["metrics"], selected["metrics"]), "Bağımsız çizelgeler uyuşmuyor.")
        digest = row["raw_sha256"]
        read_trace((folder / row["raw"]).read_bytes(), digest, scenario, row, chart)
        receipts.append({"name": row["name"], "raw_sha256": digest, "trial_sha256": sha(folder / (row["name"]+".json"))})
    return {"order": selected["order"], "assignments": first["assignments"], "metrics": metrics(first),
            "physics": {"hydraulic": first["r1"], "additional": first["extra"], "fresh_repeats": selected["verification"],
                        "raw_sha256": first["raw_sha256"]}, "receipts": receipts}


def calculate(folder):
    stored = load(folder / "input.json")
    request = CustomRequest.model_validate(stored["packet"]["request"])
    packet, source = prepare(request, diagnostic_enabled())
    require(stored["job_id"] == folder.name and stored["packet"] == packet, "İş girdisi veya kaynak kimliği değişti.")
    scenario = packet["inputs"]["scenario"]
    lab = Laboratory(source.entry, ScenarioS02.model_validate(scenario), folder, stored)
    try:
        selected, costs = compute(lab, request.search)
        require(not packet["diagnostic"], "Tanısal iş sonucu yayımlanmaz.")
        for row in lab.records:
            require(row["status"] == "PASS" and row["r1"]["pass"] is True and row["extra"]["pass"] is True
                    and [c["seq"] for c in row["calls"]] == [1, 2]
                    and all(c["solver_status"] == "returned" for c in row["calls"])
                    and sha(folder / row["raw"]) == row["raw_sha256"]
                    and same_metrics(row["metrics"], independent_metrics(folder, row, scenario)),
                    "Taze çözüm veya ham veriden hesaplanan dört ölçüt uyuşmuyor.")
        trials = {row["name"]: row for row in lab.records}
        result = {key: method_proof(folder, choice, trials, scenario, source.chart) for key, choice in selected.items()}
    except TrialFailed as exc:
        write(folder / "failure.json", {"code": exc.result["status"], "trial": exc.result.get("failed_trial"),
                                      "reason": exc.result.get("reason"), "wntr_calls":sum(len(t["calls"]) for t in lab.records)})
        return 2
    main = "proposal" if len(request.faults) == 3 else "s02_b6"
    exhaustive = selected.get("oracle")
    coverage = {"candidate_budget": selected[main]["budget"], "evaluated_candidates": selected[main]["unique_candidates"],
                "total_priorities": 6 if main == "proposal" else 24}
    if exhaustive:
        coverage.update(complete_orders=exhaustive["valid"], unique_schedules=exhaustive["unique"],
                        minimum_weighted_m3=exhaustive["minimum_weighted_unmet_volume_m3"],
                        extra_seconds=costs["oracle"]["wall_s"],
                        improvement_vs_fast_m3=result[main]["metrics"][METRICS[0]]-exhaustive["minimum_weighted_unmet_volume_m3"])
    write(folder / "trials.json", {name: {"trial_sha256": sha(folder / (name + ".json")),
          "raw_sha256": row["raw_sha256"]} for name, row in trials.items()})
    digests = {key: packet[key] for key in ("input_sha256", "source_sha256", "code_sha256", "scenario_sha256")}
    write(folder / "outcome.json", {"mode": MODE, "job_id": folder.name, **digests,
          "physical_pass": True, "trial_count": len(lab.records), "wntr_calls": len(lab.records) * 2,
          "costs": costs, "coverage": coverage, "comparison": "oracle" if exhaustive else main, "methods": result})
    return 0


if __name__ == "__main__":
    identifier = sys.argv[1]
    if not re.fullmatch("[0-9a-f]{32}", identifier):
        raise SystemExit(3)
    folder = Path(JOBS) / identifier
    if folder.resolve(strict=True) != folder:
        raise SystemExit(3)
    raise SystemExit(calculate(folder))

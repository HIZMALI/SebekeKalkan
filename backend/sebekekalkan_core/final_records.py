"""Read-only, fail-closed adapter over the immutable demonstration evidence."""
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from pydantic import BaseModel, FiniteFloat

from .networks import ROOT
from .s02_evidence import verdict
from .s02_physics import METRICS, identity

CATALOG = "SPRINT02/DEMO_KATALOGU.json"
MANIFEST = "SPRINT02/SONUC_MANIFEST_SHA256.json"
PAIRS = "SPRINT02/KARSILASTIRMA_S02.csv"
METHODS = ("fifo", "greedy")
MODEL_FILES = {
    "Net2": "SPRINT02/MODELLER/Net2.inp",
    "Skeletonize": "SPRINT02/MODELLER/skeletonize.inp",
    "Net1": "02_CALISAN_REFERANS/Dogrulama/Net1.inp",
    "Net3": "02_CALISAN_REFERANS/data/networks/Net3.inp",
}
HISTORY = "02_CALISAN_REFERANS/Dogrulama"
PINS = {
    CATALOG: "333c85b8de321e531f01198dbfe8a6a2c7e5a4bc7bdca0015712a62bed453b99",
    MANIFEST: "bdc5d06df8fd4aff135f00933e8db3c4c6554266665566e0ff6b7fba273db404",
    f"{HISTORY}/protocol.json": "c2e49822fdfe399774fe8d1c9f9ae358e9a55f8a45ff238363e8191b134fdf31",
}
CASE_GROUPS = {
    "Net2_G4_C1": "internal_holdout", "Net2_S3_C1": "sprint01",
    "Skeletonize_G1_C1": "external_holdout", "Net2_S1_C3": "sprint01",
    "Net2_S1_C2": "sprint01", "Net1_A3_C1": "historical", "Net3_A1_C1": "historical",
}


class EvidenceError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise EvidenceError(message)


class Assignment(BaseModel):
    pipe_id: str
    crew: int
    starts_at_h: FiniteFloat
    ends_at_h: FiniteFloat


class Method(BaseModel):
    order: list[str] | None
    metrics: dict[str, FiniteFloat]
    assignments: list[Assignment] | None = None
    deficit: list[tuple[FiniteFloat, FiniteFloat]] | None = None
    physics: dict


class Diagram(BaseModel):
    pipes: dict[str, list[tuple[FiniteFloat, FiniteFloat]]]
    other_links: list[list[tuple[FiniteFloat, FiniteFloat]]]
    nodes: dict[str, tuple[FiniteFloat, FiniteFloat]]


class Card(BaseModel):
    case_id: str
    group: str
    status: str
    network: str | None = None
    baseline: str | None = None
    comparison: str | None = None
    metrics: dict[str, FiniteFloat] | None = None


class Detail(BaseModel):
    case_id: str
    network: str
    group: str
    mode: str = "recorded"
    baseline: str
    comparison: str
    crews: int
    failures: list[str]
    horizon_hours: FiniteFloat
    failure_start_hour: FiniteFloat
    methods: dict[str, Method]
    diagram: Diagram
    evidence: dict


def metrics(record):
    values = {key: record["metrics"][key] for key in METRICS}
    require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in values.values()),
            "Geçersiz ölçüm")
    return values


def comparison_row(row):
    a, b = (float(row[key]) for key in ("baseline_value", "proposal_value"))
    require(math.isfinite(a) and math.isfinite(b) and
            verdict(a, b, row["metric"]) == row["classification"], "CSV karşılaştırması uyuşmuyor")
    return {**row, "baseline_value": a, "proposal_value": b}


class Records:
    def __init__(self, root: Path = ROOT.parent):
        self.root = root.resolve()
        self.dependencies = set()

    def bytes(self, rel, expected=None, limit=16_000_000):
        # Paths come exclusively from literal policy or previously validated identities.
        path = self.root / rel
        try:
            require(not Path(rel).is_absolute() and path.resolve(strict=True) == path
                    and path.is_relative_to(self.root) and path.is_file(), "İzin dışı kanıt yolu")
            require(0 < path.stat().st_size <= limit, "Geçersiz kanıt dosya boyutu")
            raw = path.read_bytes()
        except OSError as exc:
            raise EvidenceError(f"Kanıt okunamadı ({rel})") from exc
        if expected:
            require(hashlib.sha256(raw).hexdigest() == expected, f"SHA-256 uyuşmuyor ({rel})")
        self.dependencies.add(rel)
        return raw

    def json(self, rel, expected=None):
        return json.loads(self.bytes(rel, expected or PINS.get(rel)).decode("utf-8-sig"))

    def catalogue(self):
        doc = self.json(CATALOG)
        require(doc["schema_version"] == "s02-recorded-1" and len(doc["cards"]) == len(CASE_GROUPS)
                and {c["case_id"] for c in doc["cards"]} == CASE_GROUPS.keys(), "Katalog şeması")
        return {c["case_id"]: c for c in doc["cards"]}

    def manifest(self):
        return self.json(MANIFEST)["files_relative_to_sprint02"]

    def s02_trial(self, parent, name, source, with_series, manifest):
        require(re.fullmatch(r"(fifo|greedy|s02_b6)-(candidate[0-9]{0,2}|fresh|repeat)", name),
                "İzin dışı ham kayıt")
        relative = f"{parent}/{name}.json"
        record = self.json("SPRINT02/" + relative, manifest[relative])
        require(record["name"] == name and record["order"] == source["order"]
                and record["status"] == "PASS" and record["r1"]["pass"] is True
                and record["extra"]["pass"] is True and record["metrics"] == source["metrics"]
                and record["raw"] == name + ".zip", "Ham fizik veya yöntem kaydı uyuşmuyor")
        relative = f"{parent}/{name}.zip"
        require(manifest[relative] == record["raw_sha256"], "Ham kaynak kimliği uyuşmuyor")
        bundle = self.bytes("SPRINT02/" + relative, record["raw_sha256"])
        series = None
        if with_series:
            with ZipFile(io.BytesIO(bundle)) as archive:
                expected, delivered = (
                    list(csv.DictReader(io.StringIO(archive.read(f"{member}.csv").decode("utf-8-sig"))))
                    for member in ("expected-demand", "demand")
                )
            require(len(expected) == len(delivered) > 1, "Ham seri uzunluğu farklı")
            series = []
            for demand, actual in zip(expected, delivered):
                t = float(demand.pop("zaman_saniye"))
                require(t == float(actual["zaman_saniye"]), "Ham seri zaman ekseni farklı")
                deficit = sum(max(0., float(v) - float(actual[k])) for k, v in demand.items() if float(v) > 0)
                series.append((t / 3600, deficit * 1000))
        return record, series

    def s02(self, raw, card, relative):
        task = raw["task"]
        manifest = self.manifest()
        parent = relative.removeprefix("SPRINT02/").rsplit("/", 1)[0]
        require(raw["status"] == "PASS" and raw["oracle"]["valid"] == 24
                and raw["trial_statuses"] == {"PASS": raw["physical_trials"]}
                and raw["batch"] == "bd6bc280d8524f91810cb03b6589fccd" and raw["run_id"] == card["record_id"]
                and task["case_id"] == card["case_id"] and task["model_id"] == card["network"]
                and task["group"] == card["group"] == CASE_GROUPS[card["case_id"]]
                and task["model_sha256"] == card["network_sha256"]
                and task["scenario_sha256"] == card["scenario_sha256"]
                and raw["method_version"] == card["method_version"]
                and raw["protocol_lock_sha256"] == card["protocol_sha256"] == manifest["PROTOKOL_LOCK.json"],
                "Sprint 02 vaka, protokol veya yöntem kimliği uyuşmuyor")
        decision_file = parent + "/decisions-before-oracle.json"
        require(raw["decisions_sha256"] == manifest[decision_file], "Karar özeti uyuşmuyor")
        self.json("SPRINT02/" + decision_file, raw["decisions_sha256"])
        methods = {}
        for key in (*METHODS, "s02_b6"):
            source = raw["methods"][key]
            require(source["status"] == "PASS" and source["physical_pass"] is True
                    and source["oracle_same_order_match"] is True and len(set(source["verification"])) == 2,
                    "Sprint 02 tekrar veya fizik kapısı eksik")
            row, series = self.s02_trial(parent, source["record"], source, True, manifest)
            for name in source["verification"]:
                repeated, _ = self.s02_trial(parent, name, source, False, manifest)
                require(row["assignments"] == repeated["assignments"], "Yeniden çözüm çizelgesi uyuşmuyor")
            methods[key] = Method(order=source["order"], metrics=metrics(source), assignments=row["assignments"],
                                  deficit=series, physics={"hydraulic": row["r1"], "additional": row["extra"],
                                  "fresh_repeats": source["verification"], "raw_sha256": row["raw_sha256"],
                                  "budget": source.get("budget"),
                                  "references_included": source.get("mandatory_reference_signatures_included")})
        return task["scenario"], methods, {"code_sha256": raw["code_sha256"], "solver": raw["solver"],
            "protocol_sha256": raw["protocol_lock_sha256"]}

    def s01(self, raw, card):
        require(raw["status"] == "PASS" and raw["oracle_verified"] is True
                and raw["case_id"] == card["case_id"] and raw["run_id"] == card["record_id"]
                and raw["model_id"] == card["network"] and raw["model_sha256"] == card["network_sha256"]
                and raw["scenario_sha256"] == card["scenario_sha256"]
                and card["method_version"] == "decision_policy_v2 / " + raw["code_revision"],
                "Sprint 01 vaka, fizik veya kod kimliği uyuşmuyor")
        methods = {}
        for key in (*METHODS, "proposal"):
            m = raw["methods"][key]
            require(m["status"] == "PASS" and m["physical_valid"] is True and m["converged"] is True
                    and m["r1_gate"]["pass"] is True and m["additional_gate"]["pass"] is True,
                    "Sprint 01 fizik kapısı eksik")
            series = [(t / 3600, d * 1000) for t, d in
                      zip(m["times_seconds"], m["unmet_demand_m3s"], strict=True)]
            methods[key] = Method(order=m["order"], metrics=metrics(m), assignments=m["assignments"], deficit=series,
                                  physics={"hydraulic": m["r1_gate"], "additional": m["additional_gate"]})
        return raw["scenario"], methods, {"code_sha256": raw["code_revision"], "solver": raw["solver_version"]}

    def historical(self, raw, card):
        selector = card["record_selector"]
        case = card["case_id"]
        require(selector["case"] == case, "Tarihsel vaka seçicisi uyuşmuyor")
        rows = [r for r in raw if r["case"] == case]
        require(len(rows) == 1, "Tarihsel vaka bulunamadı veya tekrarlı")
        row = rows[0]
        decision = row["methods"]["proposal"]["classification"]
        require(row["network"] == card["network"] and row["status"] == "completed"
                and row["selected"]["status"] == "completed" and row["physical"]["pass"] is True
                and selector["decision_sha256"] == decision["decision_sha256"]
                and card["record_id"] == f"historical:{case}:{decision['decision_sha256']}"
                and card["method_version"] == decision["policy"], "Tarihsel karar veya fizik kapısı uyuşmuyor")
        protocol = self.json(f"{HISTORY}/protocol.json")
        inp = next(r for r in protocol["cases"] if r["id"] == case)
        require(not inp["model_changes"], "Tarihsel şema farklı model kullanıyor")
        sc = inp["scenario"]
        orders = {"fifo": [f["pipe_id"] for f in sc["failures"]], "proposal": row["selected"]["order"]}
        return sc, {key: Method(order=orders.get(key), metrics=metrics(row["methods"][key]), physics=row["physical"])
                    for key in (*METHODS, "proposal")}, {"decision_sha256": decision["decision_sha256"],
                      "protocol_sha256": PINS[f"{HISTORY}/protocol.json"]}

    def verify(self, card):
        stage, case, record = (card[k] for k in ("source_stage", "case_id", "record_id"))
        group = CASE_GROUPS[case]
        require(card["physical_pass"] is True and card["mode"] == "recorded", "Fizik veya mod etiketi uyuşmuyor")
        if group == "historical":
            require(stage == "historical" and card["record_path"] == f"../{HISTORY}/case_summary.json",
                    "İzin dışı tarihsel kayıt yolu")
            relative = f"{HISTORY}/case_summary.json"
            source = self.historical(self.json(relative, card["record_sha256"]), card)
        else:
            require(re.fullmatch("[a-f0-9]{32}", record), "İzin dışı kayıt kimliği")
            if group == "sprint01":
                require(stage == "SPRINT01" and card["record_path"] == f"../SPRINT01/KOSULAR/v1/{record}/result.json",
                        "İzin dışı Sprint 01 kayıt yolu")
                relative = f"SPRINT01/KOSULAR/v1/{record}/result.json"
                source = self.s01(self.json(relative, card["record_sha256"]), card)
            else:
                require(stage == "SPRINT02" and card["record_path"] == f"KOSULAR/{record}/result.json",
                        "İzin dışı Sprint 02 kayıt yolu")
                relative = f"SPRINT02/KOSULAR/{record}/result.json"
                source = self.s02(self.json(relative, card["record_sha256"]), card, relative)
        sc, methods, evidence = source
        require(identity(sc) == card["scenario_sha256"], "Senaryo SHA-256 uyuşmuyor")
        for label in ("baseline", "comparison"):
            method = methods[card[label]]
            require(method.order == card[label + "_order"] and method.metrics == card[label + "_metrics"],
                    "Katalog sırası veya dört ölçüm uyuşmuyor")
        strong = card.get("strong_reference_metrics")
        require(strong is None or methods["greedy"].metrics == strong, "Güçlü yöntem ölçümleri uyuşmuyor")
        failures = [f["pipe_id"] for f in sc["failures"]]
        for method in methods.values():
            require(method.order is None or sorted(method.order) == sorted(failures), "Onarım sırası eksik")
            if method.assignments:
                require([a.pipe_id for a in method.assignments] == method.order
                        and all(1 <= a.crew <= sc["crews"] and sc["failure_start_hour"] <= a.starts_at_h
                                < a.ends_at_h <= sc["horizon_hours"] for a in method.assignments)
                        and max(a.ends_at_h for a in method.assignments) == method.metrics[METRICS[3]],
                        "Çizelge kaydı uyuşmuyor")
            if method.deficit:
                times = [hour for hour, _ in method.deficit]
                require(times[0] == 0 and times[-1] == sc["horizon_hours"] and
                        all(a < b for a, b in zip(times, times[1:])), "Zaman serisi eksik")
        model_file = MODEL_FILES[card["network"]]
        model = self.bytes(model_file, card["network_sha256"])
        return Detail(case_id=case, network=card["network"], group=group, baseline=card["baseline"],
                      comparison=card["comparison"], crews=sc["crews"], failures=failures,
                      horizon_hours=sc["horizon_hours"], failure_start_hour=sc["failure_start_hour"],
                      methods=methods, diagram=diagram(model),
                      evidence={**evidence, **{k: card[k] for k in ("network_sha256", "scenario_sha256", "method_version",
                          "record_id", "record_sha256", "physical_pass", "source_stage", "scientific_scope")},
                          "record_path": relative, "model_path": model_file, "record_selector": card.get("record_selector")})

    def research(self):
        manifest = self.manifest()
        rows = list(csv.DictReader(io.StringIO(self.bytes(PAIRS, manifest[Path(PAIRS).name]).decode("utf-8-sig")),
                                   delimiter=";"))
        primary = [comparison_row(r) for r in rows if (r["baseline"], r["proposal"], r["metric"])
                   == ("greedy", "s02_b6", METRICS[0])]
        groups = ("dev", "internal_holdout", "external_holdout")
        require(len({r["case"] for r in primary}) == len(primary) == 14 and
                {key: sum(r["group"] == key for r in primary) for key in groups} ==
                dict(zip(groups, (4, 4, 6))), "Araştırma paydası uyuşmuyor")
        counts = {group: dict(Counter(r["classification"] for r in primary if r["group"] == group))
                  for group in groups}
        full = list(csv.DictReader(io.StringIO(self.bytes("SPRINT02/TUM_KOSULLAR_S02.csv",
                     manifest["TUM_KOSULLAR_S02.csv"]).decode("utf-8-sig")), delimiter=";"))
        gap = [r for r in full if r["case"] == "Net2_G1_C1" and r["method"] in ("s02_b6", "oracle")]
        losses = [comparison_row(r) for r in rows if r["classification"] == "LOSS" and
                  (r["case"], r["baseline"], r["proposal"], r["metric"]) in {
                  ("Net2_G1_C2", "fifo", "s02_b6", METRICS[1]),
                  ("Net2_G1_C2", "fifo", "s02_b6", METRICS[3]),
                  ("Net2_G4_C2", "greedy", "s02_b12", METRICS[3])}]
        return {"groups": counts, "total": dict(Counter(r["classification"] for r in primary)),
                "gap": gap, "losses": losses, "source": PAIRS, "source_sha256": manifest[Path(PAIRS).name]}


def diagram(infile):
    nodes, vertices, pipes, other = {}, {}, {}, []
    links = []
    section = ""
    for line in infile.decode("utf-8-sig", errors="replace").splitlines():
        words = line.split(";", 1)[0].split()
        if not words:
            continue
        if words[0].startswith("["):
            section = words[0].upper()
        elif section in ("[PIPES]", "[PUMPS]", "[VALVES]"):
            links.append((section, *words[:3]))
        elif section in ("[COORDINATES]", "[VERTICES]"):
            name, x, y = words[:3]
            point = (float(x), -float(y))
            if section == "[COORDINATES]":
                nodes[name] = point
            else:
                vertices.setdefault(name, []).append(point)
    for section, name, start, end in links:
        if start not in nodes or end not in nodes:
            continue
        points = [nodes[start], *vertices.get(name, ()), nodes[end]]
        if section == "[PIPES]":
            pipes[name] = points
        else:
            other.append(points)
    return Diagram(pipes=pipes, other_links=other, nodes=nodes)

import csv
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from sebekekalkan_core.api_v2 import app
from sebekekalkan_core import final_v4_recorded
from sebekekalkan_core.final_records import Records
from sebekekalkan_core.final_v4_trace import read_trace

BASE = "/api/final/v2"


@pytest.mark.parametrize("case", ["Net2_G4_C1", "Skeletonize_G1_C1"])
def test_recorded_trace_admission_and_source_agreement(case):
    client = TestClient(app)
    response = client.get(f"{BASE}/recorded/{case}")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    d = response.json()
    records = Records()
    case_file = d["evidence"]["record_path"]
    raw = records.json(case_file, d["evidence"]["record_sha256"])
    assert d["mode"] == "recorded"
    assert {tuple(trace["minutes"]) for trace in d["traces"].values()} == {tuple(range(0, 1441, 15))}
    for method, trace in d["traces"].items():
        assignment = d["methods"][method]["assignments"][0]
        column = trace["pipe_ids"].index(assignment["pipe_id"])
        end = int(assignment["ends_at_h"] * 4)
        assert trace["link_status"][8][column] == 0
        assert trace["flow_m3s"][8][column] == 0
        assert trace["link_status"][end][column] == 1
        rel = case_file.rsplit("/", 1)[0] + f"/{raw['methods'][method]['record']}.zip"
        bundle = records.bytes(rel, trace["raw_sha256"])
        with ZipFile(BytesIO(bundle)) as z:
            rows = list(csv.DictReader(z.read("pressure.csv").decode("utf-8-sig").splitlines()))
            expected = list(csv.DictReader(z.read("expected-demand.csv").decode("utf-8-sig").splitlines()))[end]
            actual = list(csv.DictReader(z.read("demand.csv").decode("utf-8-sig").splitlines()))[end]
        assert trace["pressure_m"][end] == [float(rows[end][n]) for n in trace["node_ids"]]
        positives = [n for n in expected if n != "zaman_saniye" and float(expected[n]) > 0]
        assert trace["delivered_lps"][end] == pytest.approx(sum(float(actual[n]) for n in positives) * 1000)
        assert trace["deficit_lps"][end] == pytest.approx(
            sum(max(0, float(expected[n])-float(actual[n])) for n in positives)*1000)
    assert client.get(f"{BASE}/recorded/{case}/chart.svg").status_code == 200


@pytest.fixture(scope="module")
def known_trace():
    r = Records()
    d = r.verify(r.catalogue()["Net2_G4_C1"])
    filename = d.evidence["record_path"]
    original = r.json(filename, d.evidence["record_sha256"])
    method = "s02_b6"
    plan = d.methods[method]
    directory = filename.rsplit("/", 1)[0]
    raw = r.bytes(f"{directory}/{original['methods'][method]['record']}.zip", plan.physics["raw_sha256"])
    return raw, original["task"]["scenario"], plan.model_dump(), d.diagram


@pytest.mark.parametrize("broken", ["wrong_hash", "missing_csv", "missing_tick", "nonfinite", "bad_pdd", "wrong_status"])
def test_trace_fails_closed_on_corruption(known_trace, broken):
    raw, sc, plan, diagram = known_trace
    if broken == "wrong_hash":
        with pytest.raises(ValueError, match="SHA-256"):
            read_trace(raw, "a"*64, sc, plan, diagram)
        return
    result = BytesIO()
    with ZipFile(BytesIO(raw)) as source, ZipFile(result, "w") as out:
        for info in source.infolist():
            data = source.read(info)
            if broken == "missing_csv" and info.filename == "flowrate.csv":
                continue
            if info.filename == "pressure.csv" and broken == "missing_tick":
                data = b"\n".join(data.splitlines()[:-1])
            if info.filename == "pressure.csv" and broken == "nonfinite":
                header, first, rest = data.split(b"\n", 2)
                fields = first.split(b",")
                fields[1] = b"nan"
                data = b"\n".join((header, b",".join(fields), rest))
            if info.filename == "physical-gate.json" and broken == "bad_pdd":
                data = json.dumps({**json.loads(data), "pdd_pass": False}).encode()
            if info.filename == "link-status.csv" and broken == "wrong_status":
                lines = data.decode("utf-8-sig").splitlines()
                header = lines[0].split(",")
                values = lines[9].split(",")
                values[header.index(plan["order"][0])] = "1"
                lines[9] = ",".join(values)
                data = "\n".join(lines).encode()
            out.writestr(info.filename, data)
    bundle = result.getvalue()
    with pytest.raises(ValueError):
        read_trace(bundle, sha256(bundle).hexdigest(), sc, plan, diagram)


def test_recording_endpoints_hide_numbers_on_bad_trace(monkeypatch):
    def invalid(*args, **kwargs):
        raise ValueError("Eksik zaman ızgarası")
    monkeypatch.setattr(final_v4_recorded, "read_trace", invalid)
    client = TestClient(app)
    for suffix in ("", "/chart.svg"):
        r = client.get(f"{BASE}/recorded/Net2_G4_C1{suffix}")
        assert r.status_code == 409 and list(r.json()) == ["message"]
    assert client.get(f"{BASE}/recorded/Net3_A1_C1").status_code == 404
    stats = client.get(BASE+"/research").json()
    assert stats["total"] == {"WIN": 4, "TIE": 10}
    assert stats["groups"]["external_holdout"] == {"TIE": 6}

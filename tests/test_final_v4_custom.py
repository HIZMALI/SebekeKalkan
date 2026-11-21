from io import BytesIO
import json
import os
from pathlib import Path
import time
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from sebekekalkan_core.api_v2 import app
from sebekekalkan_core import final_v4_custom_api as api
from sebekekalkan_core.final_v4_custom_input import JOBS, MODE, VERSION
from sebekekalkan_core.networks import ROOT

BASE = "/api/final/v2/custom"
SAMPLE = {"network": "Net2", "crews": 1, "faults": [
    {"pipe_id": "17", "repair_hours": 2}, {"pipe_id": "9", "repair_hours": 3},
    {"pipe_id": "18", "repair_hours": 4}, {"pipe_id": "12", "repair_hours": 5}]}


def wait(client, id, seconds=35):
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        response = client.get(f"{BASE}/jobs/{id}")
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] not in {"queued", "running"}:
            return result
        time.sleep(.15)
    pytest.fail("Gerçek iş bekleme süresini aştı.")


def no_result(client, id):
    rel = f"{BASE}/jobs/{id}"
    assert client.get(rel+"/view").status_code == 409
    codes = {kind: client.get(rel+"/export/"+kind).status_code for kind in ("csv", "json", "pdf")}
    assert set(codes.values()) == {409}
    return codes


def evidence(filename, value):
    root = os.environ.get("SE_V4_TEST_EVIDENCE")
    if root:
        (Path(root) / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")


def test_model_contains_real_eligible_pipes_and_rules():
    client = TestClient(app)
    models = client.get(BASE+"/models").json()
    assert models["networks"] == ["Net2", "Skeletonize"]
    assert models["timeout_seconds"] == 180 and models["mode"] == MODE
    for name in models["networks"]:
        data = client.get(BASE+"/models/"+name).json()
        assert set(data["eligible"]) <= data["diagram"]["pipes"].keys()
        assert len(data["eligible"]) >= 30 and len(data["source_sha256"]) == 64
        assert data["settings"] == {"start_hour": 2, "horizon_hours": 24, "step_minutes": 15,
                                    "minimum_pressure_m": 0, "required_pressure_m": 20, "low_pressure_m": 15}


@pytest.mark.parametrize("patch", [
    {"network": "Net3"}, {"network": "../../Net2"}, {"crews": 3}, {"crews": True}, {"start_date": "2026-99-99"},
    {"path": "../Net2.inp"}, {"wntr_max_iterations": 1}, {"horizon_hours": 16},
    {"faults": SAMPLE["faults"][:2]}, {"faults": [SAMPLE["faults"][0]]*3},
    {"faults": [*SAMPLE["faults"][:2], {"pipe_id": "999", "repair_hours": 3}]},
    {"faults": [*SAMPLE["faults"][:2], {"pipe_id": "../12", "repair_hours": 3}]},
    {"faults": [*SAMPLE["faults"][:2], {"pipe_id": "12", "repair_hours": 6}]},
    {"faults": [*SAMPLE["faults"][:2], {"pipe_id": "12", "repair_hours": 1}]},
    {"faults": SAMPLE["faults"][:3], "search": "comprehensive"},
])
def test_unacceptable_user_input(patch):
    client = TestClient(app)
    r = client.post(BASE+"/jobs", json={**SAMPLE, **patch})
    assert r.status_code == 422, r.text
    assert "job_id" not in r.json()


def test_real_wntr_near_convergence_failure_keeps_original_evidence(monkeypatch):
    monkeypatch.setenv("SEBEKE_V4_DIAGNOSTIC_WNTR_FAILURE", "1")
    with TestClient(app) as client:
        response = client.post(BASE+"/jobs", json=SAMPLE)
        assert response.status_code == 202, response.text
        queued = response.json()
        id = queued["job_id"]
        assert queued["diagnostic"] and queued["mode"] == MODE
        saved = wait(client, id)
        assert saved["status"] == "failed" and saved["failure_code"] == "SOLVER_ERROR", saved
        assert saved["worker_exit_code"] == 2 and "result" not in saved
        assert not (JOBS / id / "outcome.json").exists()
        with ZipFile(BytesIO((JOBS / id / "fifo-candidate.zip").read_bytes())) as bundle:
            trace = bundle.read("exception.txt").decode()
        assert "WNTR" in trace and "iç olay" in trace
        rejects = no_result(client, id)
        evidence("p1-gercek-wntr-hatasi.json", {"queued": queued, "final": saved, "rejected": rejects, "traceback": trace})


def test_timeout_kills_a_real_process_and_never_delivers(monkeypatch):
    monkeypatch.setattr(api, "RUN_LIMIT_S", .6)
    with TestClient(app) as client:
        response = client.post(BASE+"/jobs", json=SAMPLE)
        assert response.status_code == 202, response.text
        id = response.json()["job_id"]
        timed = wait(client, id)
        assert timed["status"] == "timeout", timed
        assert "result" not in timed and timed["timeout_seconds"] == 180
        assert not (JOBS / id / "outcome.json").exists()
        rejects = no_result(client, id)
        evidence("p1-kisa-deadline-testi.json", {"developer_test_deadline_s": .6, "state": timed, "rejected": rejects})


def test_restart_marks_old_nonterminal_state_interrupted(monkeypatch):
    root = ROOT / ".calisma/v4-unit" / uuid4().hex
    id = uuid4().hex
    folder = root / id
    folder.mkdir(parents=True)
    (folder / "state.json").write_text(json.dumps({"job_id": id, "status": "running", "mode": MODE,
                                                  "version": VERSION}), "utf-8")
    monkeypatch.setattr(api, "JOBS", root)
    with TestClient(app) as client:
        r = client.get(f"{BASE}/jobs/{id}")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "interrupted"
        assert "result" not in r.json()
        no_result(client, id)

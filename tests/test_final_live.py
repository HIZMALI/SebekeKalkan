import io
import json
import os
from pathlib import Path
import time
from zipfile import ZipFile

from fastapi.testclient import TestClient

from sebekekalkan_core.api_v2 import app
from sebekekalkan_core.final_worker import JOBS, packet

BASE = "/api/final/v1/live"


def test_allowed_scenarios_and_locked_inputs():
    with TestClient(app) as client:
        catalog = client.get(BASE + "/scenarios").json()
        assert catalog["timeout_seconds"] == 180
        assert len(catalog["scenarios"]) == 14
        assert catalog["diagnostic"] is False
        for entry in catalog["scenarios"]:
            p = packet(entry["case_id"])
            assert p["input"]["model_id"] == entry["network"]
            assert len(p["input"]["scenario"]["failures"]) == 4
            assert p["input"]["scenario"]["crews"] == entry["crews"]
        for data in ({"case_id": "Net3_A1_C1"}, {"case_id": "../Net2_G4_C1"},
                     {"case_id": "Net2_G4_C1", "crews": 3}, {"case_id": "Net2_G4_C1", "inp": "x.inp"}):
            assert client.post(BASE + "/jobs", json=data).status_code == 422


def test_real_wntr_failure_cannot_export_or_fall_back(monkeypatch):
    monkeypatch.setenv("SEBEKE_FINAL_DIAGNOSTIC_WNTR_FAILURE", "1")
    with TestClient(app) as client:
        assert client.get(BASE + "/scenarios").json()["diagnostic"]
        recorded = client.get("/api/final/v1/cases/Net2_G4_C1").json()
        r = client.post(BASE + "/jobs", json={"case_id": "Net2_G4_C1"})
        assert r.status_code == 202, r.text
        queued = r.json()
        assert queued["status"] == "queued" and queued["mode"] == "live"
        job = queued["job_id"]
        assert job != recorded["evidence"]["record_id"]
        assert queued["scenario_sha256"] != recorded["evidence"]["scenario_sha256"]
        url = BASE + "/jobs/" + job
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            state = client.get(url).json()
            if state["status"] not in {"queued", "running"}:
                break
            time.sleep(0.15)
        assert state["status"] == "failed" and state["worker_exit_code"] == 2, state
        assert state["failure_code"] == "SOLVER_ERROR"
        assert "result" not in state
        folder = JOBS / job
        row = json.loads((folder / "fifo-candidate.json").read_text("utf-8"))
        # The report grid may converge before the independent internal-event solve fails.
        assert any(call["solver_status"] in {"exception", "error_code"} for call in row["calls"])
        with ZipFile(io.BytesIO((folder / "fifo-candidate.zip").read_bytes())) as raw:
            error = raw.read("exception.txt").decode()
        assert "wntr" in error.lower()
        assert not (folder / "outcome.json").exists()
        exports = {kind: client.get(f"{url}/export/{kind}").status_code for kind in ("csv", "json", "pdf")}
        assert set(exports.values()) == {409}
        assert client.get("/api/final/v1/cases/Net2_G4_C1").json()["evidence"] == recorded["evidence"]
        evidence = os.environ.get("SE_FINAL_DIAGNOSTIC_EVIDENCE")
        if evidence:
            Path(evidence).write_text(json.dumps({"queued": queued, "failed": state, "exports": exports,
                "diagnostic": row, "traceback": error}, ensure_ascii=False, indent=2), encoding="utf-8")

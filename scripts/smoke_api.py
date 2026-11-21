"""Run real WNTR jobs against an isolated local test server."""
from datetime import datetime
from hashlib import sha256
import argparse
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "/api/final/v2/custom"
LIVE = {"queued", "running"}


def call(base, path, *, payload=None, method=None, status=200, headers=None):
    values = headers or {}
    body = None
    if payload is not None:
        values = {"Content-Type": "application/json", **values}
        body = json.dumps(payload).encode()
    req = Request(base + path, method=method, data=body, headers=values)
    try:
        response = urlopen(req, timeout=20)
    except HTTPError as exc:
        response = exc
    with response:
        output = response.read()
        assert response.code == status, (path, response.code, status, output[:256])
        return output, response.headers


def obj(base, path, **args):
    return json.loads(call(base, path, **args)[0])


def issue(base, payload):
    job = obj(base, API + "/jobs", payload=payload, status=202)
    assert job["mode"] == "LIVE_USER_SCENARIO"
    assert re.fullmatch("[a-f0-9]{32}", job["job_id"])
    assert job["timeout_seconds"] == 180
    return job


def terminal(base, path):
    phases = set()
    ends = time.monotonic() + 195
    while time.monotonic() < ends:
        state = obj(base, path)
        phase = state["status"]
        phases.add(phase)
        if phase not in LIVE:
            return state, sorted(phases)
        time.sleep(0.8)
    raise AssertionError("İş zamanında terminal duruma ulaşmadı.")


def run(base, output, failure):
    output.mkdir(parents=True, exist_ok=True)
    health = obj(base, "/healthz")
    assert health["solver"] == "WNTR"
    presets = json.loads((ROOT / "frontend/src/final-v4/presets.json").read_text("utf-8"))
    first = presets[0]["request"]
    receipt = {"at": datetime.now().astimezone().isoformat(), "base": base, "health": health, "jobs": []}
    obj(base, API + "/jobs", payload={**first, "crews": 0}, status=422)
    receipt["validation_http"] = 422
    if failure:
        job = issue(base, first)
        url = API + "/jobs/" + job["job_id"]
        state, _ = terminal(base, url)
        assert state["status"] == "failed" and state["failure_code"] == "SOLVER_ERROR" and "result" not in state
        for kind in ("json", "csv", "pdf"):
            call(base, url + "/export/" + kind, status=409)
        receipt["diagnostic"] = state
    else:
        for preset in presets:
            started = time.monotonic()
            job = issue(base, preset["request"])
            url = API + "/jobs/" + job["job_id"]
            call(base, url + "/export/json", status=409)
            if not receipt["jobs"]:
                obj(base, API + "/jobs", payload=first, status=429)
                receipt["second_client_while_busy_http"] = 429
            state, phases = terminal(base, url)
            assert state["status"] == "completed", state
            assert state["input_sha256"] == job["input_sha256"] and state["job_id"] == job["job_id"]
            view = obj(base, url + "/view")
            assert set(view["methods"]) >= {"fifo", "greedy", view["comparison"]}
            assert all(method["physics"] for method in view["methods"].values())
            exported = {}
            for kind in ("json", "csv", "pdf"):
                data, headers = call(base, url + "/export/" + kind)
                assert "attachment" in headers["Content-Disposition"]
                assert data and (kind != "pdf" or data.startswith(b"%PDF"))
                if kind == "json":
                    assert json.loads(data)["mode"] == "LIVE_USER_SCENARIO"
                if kind == "csv":
                    assert job["job_id"] in data.decode("utf-8-sig")
                name = preset["caseId"] + "." + kind
                (output / name).write_bytes(data)
                exported[kind] = {"sha256": sha256(data).hexdigest(), "bytes": len(data)}
            item = {"fixture": preset["caseId"], "network": preset["request"]["network"],
                    "search": preset["request"]["search"], "job_id": job["job_id"],
                    "phases": phases, "seconds": round(time.monotonic() - started, 3),
                    "worker_s": state.get("elapsed_seconds"), "calls": state["result"]["wntr_calls"],
                    "export_before_completion": 409, "export": exported}
            receipt["jobs"].append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
        job = issue(base, first)
        url = API + "/jobs/" + job["job_id"]
        obj(base, url + "/cancel", method="POST", status=202)
        state, phases = terminal(base, url)
        assert state["status"] == "cancelled" and "result" not in state
        call(base, url + "/export/pdf", status=409)
        receipt["cancel"] = {"job_id": job["job_id"], "phases": phases, "export_pdf": 409}
    (output / "rapor.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print("API kayıtları yazıldı.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("output", type=Path)
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"http://127\.0\.0\.1:\d{4,5}", args.base):
        parser.error("Bu yazmalı test yalnız yalıtılmış yerel 127.0.0.1 sunucusunda çalıştırılır.")
    run(args.base, args.output, args.diagnostic)

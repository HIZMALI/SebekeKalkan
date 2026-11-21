import copy
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sebekekalkan_core import final_api
from sebekekalkan_core.api_v2 import app
from sebekekalkan_core.final_records import CASE_GROUPS, CATALOG, Records
from sebekekalkan_core.s02_physics import METRICS


def test_verified_catalogue_detail_and_exports():
    client = TestClient(app)
    root = "/api/final/v1"
    cards = client.get(f"{root}/catalog")
    assert cards.status_code == 200
    assert [r["case_id"] for r in cards.json()] == list(CASE_GROUPS)
    assert all(r["status"] == "verified" for r in cards.json())
    for case, group in CASE_GROUPS.items():
        url = f"{root}/cases/{case}"
        r = client.get(url)
        assert r.status_code == 200, r.text
        detail = r.json()
        e = detail["evidence"]
        assert detail["mode"] == "recorded" and detail["group"] == group
        assert e["physical_pass"] and len(e["record_sha256"]) == 64
        assert all(set(m["metrics"]) == set(METRICS) for m in detail["methods"].values())
        assert e["record_selector"]["case"] == case if group == "historical" else e["record_selector"] is None
        assert client.get(url + "/evidence").json()["evidence"] == e
        svg = client.get(url + "/chart.svg")
        assert svg.status_code == 200 and e["record_id"] in svg.text
        assert svg.headers["content-type"].startswith("image/svg+xml")
    assert client.get(f"{root}/cases/arbitrary/chart.svg").status_code == 404


def test_golden_values_and_scientific_scope():
    r = Records()
    cards = r.catalogue()
    a, b, c = [r.verify(cards[key]) for key in list(CASE_GROUPS)[:3]]
    key, _, critical, finish = METRICS
    assert a.methods["greedy"].order == ["9", "12", "18", "17"]
    assert a.methods["s02_b6"].order == ["12", "9", "17", "18"]
    x, y = (a.methods[m].metrics for m in ("greedy", "s02_b6"))
    assert [round(x[key], 6), round(y[key], 6), round(x[key] - y[key], 6)] == [1509.015623, 1437.028326, 71.987297]
    assert round(100 * (x[key] - y[key]) / x[key], 2) == 4.77
    assert (x[critical], y[critical], x[finish], y[finish]) == (34.5, 31.5, 16, 16)
    assert b.methods["greedy"].metrics[key] == b.methods["proposal"].metrics[key] == 416.23581142028405
    assert c.methods["greedy"].metrics == c.methods["s02_b6"].metrics
    assert c.methods["greedy"].order == c.methods["s02_b6"].order
    assert round(c.methods["s02_b6"].metrics[key], 6) == 16.602816
    data = r.research()
    assert data["total"] == {"WIN": 4, "TIE": 10}
    assert data["groups"]["external_holdout"] == {"TIE": 6}
    assert (len(data["gap"]), len(data["losses"])) == (2, 3)


@pytest.mark.parametrize("fault", ["record_hash", "missing", "case", "path", "selector", "physical", "metric", "catalogue_hash"])
def test_rejected_evidence_never_exposes_numbers_or_downloads(monkeypatch, fault):
    r = Records()
    cards = r.catalogue()
    case = "Net1_A3_C1" if fault == "selector" else "Net2_S3_C1"
    card = cards[case]
    original_json = r.json

    if fault == "record_hash":
        card["record_sha256"] = "f" * 64
    elif fault == "path":
        card["record_path"] = "../../untrusted.json"
    elif fault == "selector":
        card["record_selector"]["decision_sha256"] = "0" * 64
    elif fault == "metric":
        card["comparison_metrics"][METRICS[0]] += 1
    else:
        def mutated(rel, expected=None):
            if fault == "catalogue_hash" and rel == CATALOG:
                return Records().json(rel, "0" * 64)
            if rel.endswith(f"{card['record_id']}/result.json"):
                if fault == "missing":
                    return original_json(rel.replace("result.json", "absent.json"), expected)
                value = copy.deepcopy(original_json(rel, expected))
                if fault == "case":
                    value["case_id"] = "Net2_S1_C2"
                if fault == "physical":
                    value["methods"]["proposal"]["r1_gate"]["pass"] = False
                return value
            return original_json(rel, expected)
        monkeypatch.setattr(r, "json", mutated)

    if fault != "catalogue_hash":
        monkeypatch.setattr(r, "catalogue", lambda: cards)
    monkeypatch.setattr(final_api, "Records", lambda: r)
    client = TestClient(app)
    result = client.get("/api/final/v1/catalog").json()
    assert next(x for x in result if x["case_id"] == case) == {
        "case_id": case, "group": CASE_GROUPS[case], "status": "unverified"}
    for suffix in ("", "/evidence", "/chart.svg"):
        response = client.get(f"/api/final/v1/cases/{case}{suffix}")
        assert response.status_code == 409
        assert response.json() == {"message": "Kaynak doğrulanamadı."}


def test_record_reader_rejects_traversal_and_directory_junction(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = tmp_path / "external"
    target.mkdir()
    sample = target / "record.json"
    sample.write_bytes(b"{}")
    hashed = hashlib.sha256(sample.read_bytes()).hexdigest()
    r = Records(allowed)
    with pytest.raises(ValueError, match="İzin dışı"):
        r.bytes("../external/record.json", hashed)
    link = allowed / "junction"
    if __import__("os").name == "nt":
        import subprocess
        subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="İzin dışı"):
            r.bytes("junction/record.json", hashed)
    finally:
        Path(link).rmdir() if __import__("os").name == "nt" else link.unlink()

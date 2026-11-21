import pytest
from fastapi.testclient import TestClient

from sebekekalkan_core.api_v2 import app


@pytest.mark.parametrize(("patch", "hint"), [
    ({"network": "Net3"}, "Örnek şebeke (Net2 veya Skeletonize)"),
    ({"crews": 3}, "Ekip sayısı (1–2)"),
    ({"faults": [{"pipe_id": "1", "repair_hours": 3}]}, "Arızalar (3–4 farklı boru)"),
    ({"faults": [{"pipe_id": p, "repair_hours": 6} for p in ("1", "6", "12")]}, "Onarım süresi (2–5 tam saat)"),
])
def test_free_scenario_validation_names_its_actual_limits(patch, hint):
    client = TestClient(app)
    payload = {
        "network": "Net2", "crews": 1, "search": "fast",
        "faults": [{"pipe_id": p, "repair_hours": 3} for p in ("1", "6", "12")],
        **patch,
    }
    reply = client.post("/api/final/v2/custom/jobs", json=payload)
    assert reply.status_code == 422
    assert hint in reply.json()["message"]
    assert "job_id" not in reply.json()


def test_net3_validation_still_accepts_three_crews():
    client = TestClient(app)
    example = client.get("/api/v2/example").json()

    accepted = client.post("/api/v2/scenario/validate", json={**example, "crews": 3})
    assert accepted.status_code == 200
    assert accepted.json()["crews"] == 3

    rejected = client.post("/api/v2/scenario/validate", json={**example, "crews": 4})
    assert rejected.status_code == 422
    assert "Ekip sayısı (1–3)" in rejected.json()["message"]

"""Regression checks for the research input boundary and physical diagnostics."""
import pandas as pd
import pytest
import wntr

from sebekekalkan_core import research_s01 as research


@pytest.fixture
def registered_input(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "SPRINT", tmp_path)
    folder = tmp_path / "MODELLER/v1/orijinal"
    folder.mkdir(parents=True)
    data = b"[JUNCTIONS]\nJ 0 0\n[RESERVOIRS]\nR 20\n[PIPES]\nP R J 10 100 100 0 OPEN\n[OPTIONS]\nUNITS LPS\n[END]\n"
    model = folder / "sample.inp"
    model.write_bytes(data)
    notice = b"local test notice"
    (folder / "WNTR-LICENSE.md").write_bytes(notice)
    entry = {"local_path": model.relative_to(tmp_path).as_posix(), "bytes": len(data),
             "working_sha256": research.sha(data), "original_sha256": research.sha(data),
             "license_notice_sha256": research.sha(notice)}
    return model, entry


def test_research_input_is_verified_and_instances_are_fresh(registered_input):
    _, entry = registered_input
    first = research.load_model(entry)
    second = research.load_model(entry)
    first.get_node("J").elevation = 2
    assert second.get_node("J").elevation == 0
    assert second.num_pipes == 1


def test_research_model_path_cannot_leave_the_catalog_folder(registered_input):
    _, entry = registered_input
    with pytest.raises(ValueError, match="model yolu"):
        research.load_model({**entry, "local_path": "MODELLER/v1/orijinal/../../other.inp"})


def test_changed_bytes_at_the_same_size_are_rejected(registered_input):
    model, entry = registered_input
    model.write_bytes(model.read_bytes().replace(b"J 0 0", b"J 1 0"))
    with pytest.raises(ValueError, match="SHA-256"):
        research.load_model(entry)


def test_modified_license_notice_is_rejected(registered_input):
    model, entry = registered_input
    model.with_name("WNTR-LICENSE.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="lisans bildirimi"):
        research.load_model(entry)


def test_research_continuity_separates_isolated_nodes_from_false_service():
    model = wntr.network.WaterNetworkModel()
    model.add_reservoir("R", base_head=30)
    model.add_junction("J", base_demand=.01)
    model.add_pipe("P", "R", "J")
    frames = {
        "flowrate": pd.DataFrame({"P": [.01, 0]}),
        "status": pd.DataFrame({"P": [1, 0]}),
        "demand": pd.DataFrame({"J": [.01, 0], "R": [-.01, 0]}),
        "head": pd.DataFrame({"J": [29, -2], "R": [30, 30]}),
        "pressure": pd.DataFrame({"J": [29, -2], "R": [0, 0]}),
    }
    accepted = research.additional_gate(model, frames)
    assert accepted["pass"] and accepted["source_free_junction_event_samples"] == 1
    assert accepted["raw_min_junction_pressure_m"] == -2
    frames["demand"].loc[1, "J"] = .01
    frames["flowrate"].loc[1, "P"] = .01
    rejected = research.additional_gate(model, frames)
    assert not rejected["pass"]
    assert rejected["closed_link_max_abs_flow_m3s"] == .01
    assert rejected["source_free_max_positive_delivery_m3s"] == .01

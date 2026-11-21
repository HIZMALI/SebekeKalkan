"""Verify report snapshots before a diagram or metric can be shown."""
import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
import math
from zipfile import ZipFile

from .final_records import require
from .s02_physics import METRICS, same_metrics


def member(archive, name):
    entries = [info for info in archive.infolist() if info.filename == name]
    require(len(entries) == 1 and 0 < entries[0].file_size <= 2_000_000,
            f"Ham ZIP üyesi eksik, yinelenmiş veya sınır dışında ({name}).")
    return archive.read(entries[0]).decode("utf-8-sig")


def grid(archive, name, times):
    reader = csv.reader(StringIO(member(archive, name)), strict=True)
    header = next(reader)
    require(1 < len(header) <= 200 and header[0] == "zaman_saniye"
            and len(set(header)) == len(header) and all(header),
            f"Ham tablo sütunları doğrulanamadı ({name}).")
    rows = []
    for seconds, line in zip(times, reader, strict=True):
        require(len(line) == len(header) and float(line[0]) == seconds,
                f"Ham zaman ızgarası eksik veya sırasız ({name}).")
        values = tuple(map(float, line[1:]))
        require(all(math.isfinite(x) for x in values), f"Sonlu olmayan ham değer ({name}).")
        rows.append(values)
    return header[1:], rows


def read_trace(raw, raw_hash, scenario, plan, diagram):
    """Retain signed WNTR values and integrate the same grid as the locked run."""
    require(sha256(raw).hexdigest() == raw_hash, "Ham zaman kaydının SHA-256 değeri yanlış.")
    step = scenario["step_minutes"] * 60
    horizon = scenario["horizon_hours"] * 3600
    require(step == 900 and horizon == 86400, "Gösterim 0–24 saat ve 15 dakika ızgara gerektirir.")
    times = list(range(0, horizon + 1, step))
    with ZipFile(BytesIO(raw)) as archive:
        hydraulic = json.loads(member(archive, "physical-gate.json"))
        extra = json.loads(member(archive, "s02-gate.json"))
        require(all(hydraulic.get(key) is True for key in ("pass", "pdd_pass", "converged"))
                and extra.get("pass") is True, "Ham kaydın WNTR/PDD kabulü geçersiz.")
        nodes, pressure = grid(archive, "pressure.csv", times)
        receivers, delivered = grid(archive, "demand.csv", times)
        customers, expected = grid(archive, "expected-demand.csv", times)
        links, status = grid(archive, "link-status.csv", times)
        flows, flow = grid(archive, "flowrate.csv", times)

    require(set(receivers) == set(nodes) and set(customers) <= set(receivers)
            and set(links) == set(flows) and set(diagram.nodes) <= set(nodes)
            and set(diagram.pipes) <= set(links)
            and all(x in (0, 1, 2) for row in status for x in row), "Ham model kimlikleri uyuşmuyor.")
    by_pipe = {row["pipe_id"]: row for row in plan["assignments"]}
    pipe_ids = plan["order"]
    require(set(pipe_ids) == by_pipe.keys() and set(pipe_ids) <= diagram.pipes.keys(),
            "Onarım çizelgesi veya boru kimliği eksik.")
    status_columns = [links.index(p) for p in pipe_ids]
    flow_columns = [flows.index(p) for p in pipe_ids]
    states = [[int(row[i]) for i in status_columns] for row in status]
    flows_m3s = [[row[i] for i in flow_columns] for row in flow]
    for k, pipe in enumerate(pipe_ids):
        end = by_pipe[pipe]["ends_at_h"] * 3600
        start = scenario["failure_start_hour"] * 3600
        require(all((states[i][k] == 0 and abs(flows_m3s[i][k]) < 1e-7) if start <= t < end
                    else states[i][k] != 0 for i, t in enumerate(times)),
                "Ham boru durumu veya kapalı akış çizelgeye uymuyor.")

    receiver_columns = [receivers.index(n) for n in customers]
    weights = scenario["critical_weights"]
    priorities = [weights.get(n, 1) for n in customers]
    critical_columns = [nodes.index(n) for n in weights]
    demand_series, served_series, deficit_series = [], [], []
    weighted_total, total, critical_time = 0., 0., 0.
    for i, row in enumerate(expected):
        positive = [(want, delivered[i][column], priority) for want, column, priority
                    in zip(row, receiver_columns, priorities) if want > 0]
        missing = sum(max(0., want - got) for want, got, _ in positive)
        demand_series.append(sum(want for want, _, _ in positive) * 1000)
        served_series.append(sum(got for _, got, _ in positive) * 1000)
        deficit_series.append(missing * 1000)
        if i < len(times) - 1:
            total += missing * step
            weighted_total += sum(max(0., want - got) * weight for want, got, weight in positive) * step
            critical_time += sum(pressure[i][j] < scenario["low_pressure_m"] for j in critical_columns) * step / 3600
    computed = dict(zip(METRICS, (weighted_total, total, critical_time, max(a["ends_at_h"] for a in by_pipe.values()))))
    require(same_metrics(computed, plan["metrics"]), "Dört ölçüt ham zaman serisiyle eşleşmedi.")
    return {"minutes": [t // 60 for t in times], "node_ids": nodes, "pipe_ids": pipe_ids, "pressure_m": pressure,
            "link_status": states, "flow_m3s": flows_m3s, "expected_lps": demand_series,
            "delivered_lps": served_series, "deficit_lps": deficit_series, "raw_sha256": raw_hash}

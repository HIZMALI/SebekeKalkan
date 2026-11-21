"""Bounded local live jobs, with separate identity and exports from recorded cases."""
from contextlib import asynccontextmanager
import csv
import io
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Lock
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .final_api import BROKEN, METHOD_LABELS, tr
from .final_records import Records, require, metrics
from .final_worker import JOBS, METHODS, SOLVER, TIMEOUT, diagnostic, packet, protocol
from .networks import ROOT
from .s02_physics import METRICS, METHOD_VERSION, load, utc, write

logger = logging.getLogger(__name__)
states = {}
workers = {}
worker_guard = Lock()
stopping = False


@asynccontextmanager
async def lifespan(_app):
    global stopping
    with worker_guard:
        stopping = False
    yield
    with worker_guard:
        stopping = True
        for process in workers.values():
            if process.poll() is None:
                process.kill()


router = APIRouter(prefix="/api/final/v1/live", lifespan=lifespan)


class LiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_]+$")


def verified_result(folder, p):
    value = load(folder / "outcome.json")
    require(value["job_id"] == folder.name and value["input_sha256"] == p["input_sha256"]
            and value["source_sha256"] == p["source_sha256"] and value["physical_pass"] is True
            and list(value["methods"]) == list(METHODS), "Eksik veya farklı canlı sonuç.")
    events = [json.loads(line) for line in (folder / "solver.jsonl").read_text("utf-8").splitlines()]
    begin = [(e["trial"], e["seq"]) for e in events if e["op"] == "begin"]
    end = [(e["trial"], e["seq"]) for e in events if e["op"] == "end" and e["solver_status"] == "returned"]
    require(begin == end and len(begin) == len(set(begin)) == value["wntr_calls"] == value["trial_count"] * 2 > 0,
            "Çözücü çağrı kaydı eksik.")
    for method in value["methods"].values():
        metrics(method)
        require(method["physical"]["hydraulic"]["pass"] is True and method["physical"]["additional"]["pass"] is True,
                "Fizik kapısı tamamlanmadı.")
    return value


def run(job, p):
    from . import api as shared

    folder = JOBS / job
    start = time.monotonic()
    state = {**states[job], "started_utc": utc(), "status": "running", "worker_exit_code": None}
    states[job] = state.copy()
    try:
        folder.mkdir(parents=True, exist_ok=False)
        write(folder / "input.json", {"job_id": job, "data": p})
        tmp = ROOT / ".cache/tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1",
                   OMP_NUM_THREADS="1", TEMP=str(tmp), TMP=str(tmp), PYTHONPATH=str(ROOT / "backend"))
        with (folder / "worker.log").open("xb") as log:
            with worker_guard:
                require(not stopping, "Yerel sunucu kapanıyor.")
                proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "sebekekalkan_core.final_worker", job],
                                        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                workers[job] = proc
            try:
                state["worker_exit_code"] = proc.wait(timeout=max(0, TIMEOUT - (time.monotonic() - start)))
            except subprocess.TimeoutExpired:
                proc.kill()
                state["worker_exit_code"] = proc.wait(timeout=10)
                state.update(status="timeout", message="WNTR 180 saniye sınırına ulaştı. Sonuç yayımlanmadı.")
            if state["status"] == "running" and state["worker_exit_code"] != 0:
                state.update(status="failed", message="WNTR veya fizik denetimi tamamlanamadı. Sonuç yayımlanmadı.")
                path = folder / "diagnostic.json"
                if path.is_file():
                    state["failure_code"] = load(path)["status"]
            if state["status"] == "running":
                result = verified_result(folder, p)
                state.update(status="completed", result=result, message="Gerçek WNTR ve yeniden çözüm kontrolleri tamamlandı.")
    except (RuntimeError, subprocess.SubprocessError, *BROKEN) as exc:
        logger.exception("Canlı iş %s doğrulanamadı: %s", job, exc)
        state.pop("result", None)
        state.update(status="failed", message="Canlı hesap doğrulanamadı. Sonuç yayımlanmadı.")
    finally:
        state.update(elapsed_seconds=time.monotonic() - start, finished_utc=utc())
        with worker_guard:
            proc = workers.pop(job, None)
            if proc is not None and proc.poll() is None:
                proc.kill()
                state["worker_exit_code"] = proc.wait()
        try:
            if folder.is_dir():
                write(folder / "job.json", {k: v for k, v in state.items() if k != "result"})
        except OSError:
            logger.exception("İş durumu diske yazılamadı %s", job)
            state.pop("result", None)
            state.update(status="failed", message="Canlı iş kaydı saklanamadı. Sonuç yayımlanmadı.")
        finally:
            states[job] = state
            with shared.guard:
                shared.active = False


@router.get("/scenarios")
def scenarios():
    try:
        tasks, _, _ = protocol(Records())
    except BROKEN as exc:
        raise HTTPException(409, "Kilitli canlı senaryolar doğrulanamadı.") from exc
    return {"solver": SOLVER, "method_version": METHOD_VERSION, "timeout_seconds": TIMEOUT,
            "diagnostic": diagnostic(), "scenarios": [
            {"case_id": t["case_id"], "network": t["model_id"], "crews": t["scenario"]["crews"]}
            for t in tasks.values()]}


@router.post("/jobs", status_code=202)
def submit(request: LiveRequest):
    from . import api as shared

    try:
        p = packet(request.case_id)
    except KeyError as exc:
        raise HTTPException(422, "Yalnız listelenen dört arızalı senaryolar kullanılabilir.") from exc
    except BROKEN as exc:
        logger.warning("Canlı kaynak doğrulanamadı: %s", exc)
        raise HTTPException(409, "Canlı hesap kaynağı doğrulanamadı.") from exc
    with shared.guard:
        if stopping or shared.active:
            raise HTTPException(429, "Yerel hesaplama kapasitesi dolu. Mevcut işin bitmesini bekleyin.")
        shared.active = True
        job = uuid4().hex
        state = {"status": "queued", "job_id": job, "mode": "live", "case_id": request.case_id,
                 "network": p["input"]["model_id"], "solver": SOLVER, "method_version": METHOD_VERSION,
                 "timeout_seconds": TIMEOUT, "diagnostic": p["diagnostic"], "queued_utc": utc(),
                 **{k: p[k] for k in ("input_sha256", "source_sha256", "adapter_sha256", "protocol_sha256", "scenario_sha256")},
                 "network_sha256": p["input"]["network_sha256"], "message": "Canlı iş sıraya alındı."}
        # Keep the queryable index bounded. Run evidence is retained on disk.
        if len(states) >= 64:
            del states[next(iter(states))]
        states[job] = state
        try:
            shared.pool.submit(run, job, p)
        except RuntimeError as exc:
            del states[job]
            shared.active = False
            raise HTTPException(503, "Yerel hesap işçisi açılamadı.") from exc
    return state


@router.get("/jobs/{job}")
def status(job: str):
    if not re.fullmatch("[a-f0-9]{32}", job) or job not in states:
        raise HTTPException(404, "Canlı iş bulunamadı.")
    return JSONResponse(states[job], headers={"Cache-Control": "no-store"})


def live_pdf(state):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    from matplotlib import get_data_path
    from .pdf_report import LOCK

    with LOCK:
        name = "FinalTR"
        pdfmetrics.registerFont(TTFont(name, str(Path(get_data_path()) / "fonts/ttf/DejaVuSans.ttf")))
        normal = ParagraphStyle("final-body", fontName=name, fontSize=9.5, leading=15, spaceAfter=7)
        title = ParagraphStyle("final-title", parent=normal, fontSize=19, leading=27, spaceAfter=16)
        p = lambda message, style=normal: Paragraph(escape(str(message)), style)
        body = [p("ŞebekeKalkan | Canlı hesap", title), p(f"İş kimliği {state['job_id']}"),
                p(f"{state['case_id']} | {state['network']} | {state['method_version']} | {SOLVER}"),
                p(f"Girdi SHA-256 {state['input_sha256']}"), p(f"Kaynak SHA-256 {state['source_sha256']}"),
                p(f"Fizik kapıları geçti. İşçi çıkış kodu {state['worker_exit_code']}."),
                Spacer(1, 12)]
        rows = [["Yöntem", "Ağırlıklı açık", "Açık (m³)", "Düğüm·saat", "Son onarım (saat)"]]
        for key, m in state["result"]["methods"].items():
            rows.append([METHOD_LABELS[key], *(tr(m["metrics"][metric]) for metric in METRICS)])
        table = Table([[p(value) for value in row] for row in rows], colWidths=[125, 96, 88, 86, 106])
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f2f3")),
                                   ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#c4d4da")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        body.extend([table, Spacer(1, 16), p("Ağırlıklı açık birimi ağırlıklı m³. Küçük değer daha iyi."),
                     p("Açık kıyaslama ağı üzerinde simülasyon. Altı aday bütçesi. Tam sayım bu canlı hesapta çalıştırılmadı.")])
        output = io.BytesIO()
        SimpleDocTemplate(output, pagesize=(595.276, 841.89), leftMargin=47, rightMargin=47,
                          topMargin=49, title="ŞebekeKalkan canlı hesap").build(body)
    return output.getvalue()


@router.get("/jobs/{job}/export/{kind}")
def export(job: str, kind: str):
    if not re.fullmatch("[a-f0-9]{32}", job) or job not in states:
        raise HTTPException(404, "Canlı iş bulunamadı.")
    state = states[job]
    if state["status"] != "completed" or not state["result"]["physical_pass"]:
        raise HTTPException(409, "Dışa aktarmak için fizik kapısından geçmiş canlı sonuç gerekli.")
    headers = {"Content-Disposition": f'attachment; filename="SebekeKalkan-canli-{job}.{kind}"',
               "Cache-Control": "no-store"}
    if kind == "json":
        return JSONResponse(state, headers=headers)
    if kind == "pdf":
        return Response(live_pdf(state), media_type="application/pdf", headers=headers)
    if kind != "csv":
        raise HTTPException(404, "Bu çıktı biçimi desteklenmiyor.")
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["job_id", "case_id", "input_sha256", "source_sha256", "method", *METRICS])
    for method, value in state["result"]["methods"].items():
        writer.writerow([job, state["case_id"], state["input_sha256"], state["source_sha256"],
                         method, *(value["metrics"][m] for m in METRICS)])
    return Response(out.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8", headers=headers)

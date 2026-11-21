"""Local, versioned job API. All public results require immutable WNTR receipts."""
from contextlib import asynccontextmanager
import csv
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO, StringIO
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import RLock
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from .final_api import BROKEN, METHOD_LABELS, tr
from .final_records import Records, metrics, require
from .final_v4_custom_input import (CustomRequest, JOBS, MODE, Network, VERSION,
                                   diagnostic_enabled, model_source, prepare, revisions)
from .final_v4_recorded import NO_STORE, json_result
from .final_v4_trace import read_trace
from .final_worker import MODELS, SOLVER, TIMEOUT
from .networks import AnalysisError, ROOT
from .s02_physics import METRICS, identity, utc, write

logger = logging.getLogger(__name__)
LIVE = {"queued", "running"}
FAILURES = (*BROKEN, csv.Error, ArithmeticError)
RUN_LIMIT_S = TIMEOUT
NAMES = {**METHOD_LABELS, "oracle": "Kapsamlı (24 sıra)"}


@dataclass
class Run:
    folder: Path
    state: dict
    process: subprocess.Popen | None = None
    cancelled: bool = False


guard = RLock()
active_runs = {}
stopping = False


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        process.kill()
    if process.poll() is None:
        process.wait(timeout=8)


def cancel_run(run):
    run.cancelled = True
    if run.process is not None:
        stop_process(run.process)


@asynccontextmanager
async def lifespan(_app):
    global stopping
    with guard:
        stopping = False
    try:
        yield
    finally:
        with guard:
            stopping = True
            for run in list(active_runs.values()):
                try:
                    cancel_run(run)
                except (OSError, subprocess.SubprocessError):
                    logger.exception("Kapanış sırasında canlı işçi durdurulamadı: %s", run.folder.name)


router = APIRouter(prefix="/api/final/v2/custom", lifespan=lifespan)


def read_file(folder, name, digest=None):
    return Records(ROOT).bytes((folder / name).relative_to(ROOT).as_posix(), digest)


def read_json(folder, name, digest=None):
    return json.loads(read_file(folder, name, digest).decode("utf-8-sig"))


def publish(run, status, message, **fields):
    value = {**run.state, **fields, "status": status, "message": message}
    update = run.folder / ".state-next"
    update.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    update.replace(run.folder / "state.json")
    run.state = value


def verified_result(folder, state, include_traces=False):
    identity_fields = ("input_sha256", "scenario_sha256", "source_sha256", "code_sha256")
    stored = read_json(folder, "input.json", state["packet_sha256"])
    p = stored["packet"]
    result = read_json(folder, "outcome.json", state["result_sha256"])
    engine, revision = revisions()
    require(stored["job_id"] == result["job_id"] == state["job_id"] == folder.name and result["mode"] == MODE
            and state["worker_exit_code"] == 0 and result["physical_pass"] is True and p["diagnostic"] is False
            and engine == p["source_sha256"] and revision == p["code_sha256"]
            and all(p[k] == result[k] == state[k] for k in identity_fields)
            and identity(p["inputs"]) == p["input_sha256"] and identity(p["inputs"]["scenario"]) == p["scenario_sha256"],
            "Canlı iş veya kaynak kimliği doğrulanamadı.")
    source = model_source(p["request"]["network"])
    require(source.entry["original_sha256"] == state["network_sha256"]
            and source.lock_sha256 == state["protocol_sha256"], "Ağ veya fizik protokolü değişti.")
    raw_events = read_file(folder, "solver.jsonl", state["solver_sha256"])
    events = [json.loads(line) for line in raw_events.splitlines()]
    begin = [(e["trial"], e["seq"]) for e in events if e["op"] == "begin"]
    end = [(e["trial"], e["seq"]) for e in events if e["op"] == "end" and e["solver_status"] == "returned"]
    require(begin == end and len(begin) == len(set(begin)) == result["wntr_calls"] == result["trial_count"]*2 > 0
            and sum(c["wntr_calls"] for c in result["costs"].values()) == len(begin)
            and result["comparison"] in result["methods"], "Hiçbir veya eksik gerçek çözücü çağrısı.")
    inventory = read_json(folder, "trials.json", state["trials_sha256"])
    require(len(inventory) == result["trial_count"]
            and {(name, seq) for name in inventory for seq in (1, 2)} == set(begin), "Deneme dizini eksik.")
    verified = {}
    for name, entry in inventory.items():
        require(re.fullmatch(r"[a-z0-9_]+-[a-z0-9]+", name), "İzin dışı deneme kimliği.")
        report = read_json(folder, name+".json", entry["trial_sha256"])
        require(report["status"] == "PASS" and report["name"] == name and report["raw"] == name+".zip"
                and report["r1"]["pass"] is True and report["r1"]["pdd_pass"] is True
                and report["extra"]["pass"] is True and report["raw_sha256"] == entry["raw_sha256"],
                "Deneme kanıtı eşleşmiyor.")
        verified[name] = (report, read_file(folder, name+".zip", entry["raw_sha256"]))
    requested = set(f["pipe_id"] for f in p["inputs"]["scenario"]["failures"])
    traces = {}
    for key, method in result["methods"].items():
        require(set(method["order"]) == requested and len(method["order"]) == len(requested)
                and len(method["receipts"]) == 3
                and method["physics"]["hydraulic"]["pass"] is True and method["physics"]["additional"]["pass"] is True,
                "Yöntem fizik doğrulaması eksik.")
        for i, receipt in enumerate(method["receipts"]):
            trial = receipt["name"]
            raw_plan, raw = verified[trial]
            require(inventory[trial] == {k: v for k, v in receipt.items() if k != "name"}
                    and raw_plan["order"] == method["order"] and raw_plan["assignments"] == method["assignments"],
                    "Yöntem ve deneme kanıtı uyuşmuyor.")
            if i == 0:
                require(metrics(raw_plan) == method["metrics"], "Canlı dört ölçüt ham kayıtla uyuşmuyor.")
                if include_traces:
                    traces[key] = read_trace(raw, receipt["raw_sha256"], p["inputs"]["scenario"], method, source.chart)
    return result, source, p, traces


def execute(run):
    from . import api as shared

    job = run.folder.name
    started = time.monotonic()
    terminal, message, fields = "failed", "Canlı hesap doğrulanamadı. Sonuç ve indirmeler kapalı.", {}
    try:
        with guard:
            if run.cancelled or stopping:
                return
            publish(run, "running", "WNTR çözümü ve fizik kontrolleri yürütülüyor.", started_utc=utc())
        tmp = ROOT / ".cache/tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                   TEMP=str(tmp), TMP=str(tmp), PYTHONPATH=str(ROOT / "backend"),
                   SEBEKE_V4_DIAGNOSTIC_WNTR_FAILURE="1" if run.state["diagnostic"] else "0")
        with (run.folder / "worker.log").open("xb") as log:
            with guard:
                if run.cancelled:
                    return
                run.process = subprocess.Popen([sys.executable, "-X", "utf8", "-m",
                                               "sebekekalkan_core.final_v4_custom_worker", job],
                                               cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                exit_code = run.process.wait(timeout=max(0, RUN_LIMIT_S-(time.monotonic()-started)))
            except subprocess.TimeoutExpired:
                stop_process(run.process)
                exit_code = run.process.wait(timeout=8)
                terminal, message = "timeout", "180 saniye sınırına ulaşıldı. Sonuç ve indirmeler kapalı."
        fields["worker_exit_code"] = exit_code
        if terminal == "timeout" or run.cancelled:
            return
        if exit_code == 0:
            fields.update(result_sha256=sha256(read_file(run.folder, "outcome.json")).hexdigest(),
                          solver_sha256=sha256(read_file(run.folder, "solver.jsonl")).hexdigest(),
                          trials_sha256=sha256(read_file(run.folder, "trials.json")).hexdigest())
            verified_result(run.folder, {**run.state, **fields})
            if time.monotonic()-started >= RUN_LIMIT_S:
                terminal, message = "timeout", "180 saniyelik doğrulama sınırına ulaşıldı. Sonuç yayımlanmadı."
            else:
                terminal, message = "completed", "Fizik kapıları ve bağımsız tekrarlar tamamlandı."
        elif (run.folder / "failure.json").is_file():
            detail = read_json(run.folder, "failure.json")
            fields.update(failure_code=detail["code"], wntr_calls=detail["wntr_calls"])
            message = "WNTR ya da fizik denetimi tamamlanamadı. Sonuç ve indirmeler kapalı."
    except (*FAILURES, RuntimeError, subprocess.SubprocessError):
        logger.exception("V4 canlı iş reddedildi: %s", job)
    finally:
        with guard:
            try:
                if run.process is not None and run.process.poll() is None:
                    stop_process(run.process)
                if run.cancelled or stopping:
                    terminal, message = "cancelled", "Canlı iş durduruldu. Sonuç ve indirmeler kapalı."
                if terminal != "completed":
                    fields = {k: v for k, v in fields.items() if k not in {"result_sha256", "solver_sha256", "trials_sha256"}}
                publish(run, terminal, message, elapsed_seconds=time.monotonic()-started, finished_utc=utc(), **fields)
            except (OSError, subprocess.SubprocessError):
                logger.exception("V4 işçi veya durum kapanışı: %s", job)
            finally:
                active_runs.pop(job, None)
                with shared.guard:
                    shared.active = False


@router.get("/models")
def models():
    return json_result({"mode": MODE, "networks": list(MODELS), "timeout_seconds": TIMEOUT,
                        "search": ["fast", "comprehensive"], "diagnostic": diagnostic_enabled()})


@router.get("/models/{network}")
def describe(network: Network):
    try:
        source = model_source(network)
    except FAILURES as exc:
        logger.warning("V4 model doğrulanamadı: %s", exc)
        raise HTTPException(409, "Yerel ağ kaynağı doğrulanamadı.") from exc
    return json_result({"network": network, "diagram": source.chart.model_dump(), "eligible": sorted(source.eligible),
                        "critical_weights": source.weights, "source_sha256": source.entry["original_sha256"],
                        "settings": {"start_hour": 2, "horizon_hours": 24, "step_minutes": 15,
                                     "minimum_pressure_m": 0, "required_pressure_m": 20, "low_pressure_m": 15}})


@router.post("/jobs", status_code=202)
def submit(request: CustomRequest):
    from . import api as shared

    try:
        p, _ = prepare(request, diagnostic_enabled())
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    except FAILURES as exc:
        logger.warning("V4 girdi kaynağı doğrulanamadı: %s", exc)
        raise HTTPException(409, "Yerel WNTR kaynağı doğrulanamadı.") from exc
    with guard, shared.guard:
        if stopping or shared.active:
            raise HTTPException(429, "Yerel hesap yuvası dolu. Aktif işin kapanmasını bekleyin.")
        job = uuid4().hex
        folder = JOBS / job
        try:
            JOBS.mkdir(parents=True, exist_ok=True)
            require(JOBS.resolve(strict=True) == JOBS, "Canlı kayıt yolu izin dışı.")
            folder.mkdir()
            write(folder / "input.json", {"job_id": job, "packet": p})
            packet_hash = sha256(read_file(folder, "input.json")).hexdigest()
            public = {k: v for k, v in p.items() if k not in {"request", "inputs"}}
            run = Run(folder, {"mode": MODE, "job_id": job, "request": p["request"], "network": request.network,
                               "solver": SOLVER, "timeout_seconds": TIMEOUT, "packet_sha256": packet_hash, **public})
            publish(run, "queued", "Yeni canlı iş sıraya alındı.", queued_utc=utc())
            active_runs[job] = run
            shared.active = True
            shared.pool.submit(execute, run)
        except (OSError, ValueError, RuntimeError) as exc:
            active_runs.pop(job, None)
            shared.active = False
            logger.exception("V4 iş açılamadı")
            raise HTTPException(503, "Canlı iş yerel diskte açılamadı.") from exc
        return JSONResponse(run.state, status_code=202, headers=NO_STORE)


def stored_job(job):
    if not re.fullmatch("[a-f0-9]{32}", job):
        raise HTTPException(404, "Canlı kullanıcı işi bulunamadı.")
    folder = JOBS / job
    with guard:
        run = active_runs.get(job)
        if run:
            return run.folder, run.state
        if not (folder / "state.json").is_file():
            raise HTTPException(404, "Canlı kullanıcı işi bulunamadı.")
        try:
            state = read_json(folder, "state.json")
            require(state["job_id"] == job and state["mode"] == MODE and state["version"] == VERSION,
                    "Canlı iş kimliği uyuşmuyor.")
            if state["status"] in LIVE:
                saved = Run(folder, state)
                publish(saved, "interrupted", "Sunucu yeniden başladı. Yarım kalan işlemin sonuç ve indirmeleri kapalı.",
                        finished_utc=utc())
                state = saved.state
            return folder, state
        except FAILURES as exc:
            raise HTTPException(409, "Canlı iş kaydı doğrulanamadı.") from exc


def completed(folder, state, traces=False):
    if state["status"] != "completed":
        raise HTTPException(409, "Doğrulanmış tamamlanmış canlı sonuç gerekli.")
    try:
        return verified_result(folder, state, traces)
    except FAILURES as exc:
        logger.warning("Canlı kanıt reddedildi (%s): %s", state["job_id"], exc)
        raise HTTPException(409, "Canlı işin ham kanıtı doğrulanamadı. Ölçüt ve indirmeler kapalı.") from exc


@router.get("/jobs/{job}")
def status(job: str):
    folder, state = stored_job(job)
    if state["status"] != "completed":
        return json_result(state)
    result, _, _, _ = completed(folder, state)
    return json_result({**state, "result": result})


@router.post("/jobs/{job}/cancel", status_code=202)
def cancel(job: str):
    with guard:
        stored_job(job)
        run = active_runs.get(job)
        if not run or run.state["status"] not in LIVE:
            raise HTTPException(409, "Bu canlı iş artık durdurulabilir durumda değil.")
        try:
            cancel_run(run)
        except (OSError, subprocess.SubprocessError) as exc:
            raise HTTPException(409, "İptal istendi. İşçi durumu henüz doğrulanamadı.") from exc
        return JSONResponse({"status": "cancelling", "job_id": job}, status_code=202, headers=NO_STORE)


@router.get("/jobs/{job}/view")
def view(job: str):
    folder, state = stored_job(job)
    result, source, p, traces = completed(folder, state, True)
    sc = p["inputs"]["scenario"]
    return json_result({"case_id": job, "network": state["network"], "group": "custom", "mode": MODE,
                        "baseline": "greedy", "comparison": result["comparison"], "crews": sc["crews"],
                        "failures": [f["pipe_id"] for f in sc["failures"]], "horizon_hours": sc["horizon_hours"],
                        "failure_start_hour": sc["failure_start_hour"], "diagram": source.chart.model_dump(),
                        "methods": result["methods"], "traces": traces,
                        "evidence": {k: v for k, v in state.items() if k.endswith("sha256") or k == "solver"}})


def pdf_report(state, result):
    from matplotlib import get_data_path
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    from .pdf_report import LOCK

    with LOCK:
        font = "FinalV4TR"
        pdfmetrics.registerFont(TTFont(font, str(Path(get_data_path()) / "fonts/ttf/DejaVuSans.ttf")))
        style = ParagraphStyle("v4body", fontName=font, fontSize=9.5, leading=14, spaceAfter=7)
        title = ParagraphStyle("v4title", parent=style, fontSize=18, leading=24, spaceAfter=14)

        def text(value, use=style):
            return Paragraph(escape(str(value)), use)

        rows = [["Yöntem", "Ağırlıklı açık", "Açık (m³)", "Düğüm·saat", "Son onarım (saat)"]]
        for key, method in result["methods"].items():
            rows.append([NAMES[key], *(tr(method["metrics"][m]) for m in METRICS)])
        table = Table([[text(value) for value in row] for row in rows],
                      colWidths=[120, 88, 88, 85, 106])
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f2ee")),
                                   ("GRID", (0, 0), (-1, -1), .45, colors.HexColor("#c4d4da")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story = [text("ŞebekeKalkan | Kullanıcı senaryosu", title), text("LIVE_USER_SCENARIO"),
                 text(f"İş kimliği {state['job_id']}"),
                 text(f"{state['network']} | {state['method_version']} | {state['solver']}"),
                 text(f"Girdi SHA-256 {state['input_sha256']}"), text(f"Kod SHA-256 {state['code_sha256']}"),
                 text(f"Fizik kabulü geçti. {result['wntr_calls']} WNTR çağrısı. İşçi çıkış kodu 0."),
                 Spacer(1, 10), table, Spacer(1, 12),
                 text("Ağırlıklı hizmet açığının birimi ağırlıklı m³. Küçük ölçüt değerleri tercih edilir."),
                 text("Bu keşif işi 14 kayıtlı araştırma koşulunun paydasına katılmaz.")]
        if result["comparison"] == "oracle":
            story.append(text("Kapsamlı tarama dört arızanın 24 beklemesiz onarım önceliğini kapsar."))
        output = BytesIO()
        SimpleDocTemplate(output, pagesize=(595.276, 841.89), leftMargin=47, rightMargin=47,
                          topMargin=48, title="ŞebekeKalkan kullanıcı senaryosu").build(story)
    return output.getvalue()


@router.get("/jobs/{job}/export/{kind}")
def export(job: str, kind: str):
    if kind not in {"json", "csv", "pdf"}:
        raise HTTPException(404, "Bu çıktı türü desteklenmiyor.")
    folder, state = stored_job(job)
    result, _, _, _ = completed(folder, state)
    headers = {**NO_STORE, "Content-Disposition": f'attachment; filename="SebekeKalkan-V4-{job}.{kind}"'}
    if kind == "json":
        return JSONResponse({**state, "result": result}, headers=headers)
    if kind == "pdf":
        return Response(pdf_report(state, result), media_type="application/pdf", headers=headers)
    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    names = ("job_id", "mode", "input_sha256", "code_sha256")
    writer.writerow([*names, "method", *METRICS])
    for key, method in result["methods"].items():
        writer.writerow([*(state[name] for name in names), key, *(method["metrics"][m] for m in METRICS)])
    return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8", headers=headers)

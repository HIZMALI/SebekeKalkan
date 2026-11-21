"""Separate V4 presentation API over the original two Sprint 02 records."""
from csv import Error as CsvError
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .final_api import BROKEN, attachment, case_svg, research_data
from .final_records import Records, require
from .final_v4_trace import read_trace

router = APIRouter(prefix="/api/final/v2")
logger = logging.getLogger(__name__)
V4_CASES = {"Net2_G4_C1", "Skeletonize_G1_C1"}
NO_STORE = {"Cache-Control": "no-store"}


def json_result(data):
    return JSONResponse(data, headers=NO_STORE)


def recorded(case):
    if case not in V4_CASES:
        raise HTTPException(404, "Basınç animasyonuna uygun kayıt bulunamadı.")
    records = Records()
    try:
        card = records.catalogue()[case]
        detail = records.verify(card)
        relative = detail.evidence["record_path"]
        root = relative.rsplit("/", 1)[0]
        result = records.json(relative, detail.evidence["record_sha256"])
        traces = {}
        for name, plan in detail.methods.items():
            trial = result["methods"][name]["record"]
            raw_hash = plan.physics["raw_sha256"]
            require(re.fullmatch(r"(fifo|greedy|s02_b6)-candidate[0-9]{0,2}", trial),
                    "İzin dışı ham çizelge adı.")
            raw = records.bytes(f"{root}/{trial}.zip", raw_hash)
            traces[name] = read_trace(raw, raw_hash, result["task"]["scenario"], plan.model_dump(), detail.diagram)
        return detail, traces
    except (*BROKEN, ArithmeticError, CsvError) as exc:
        logger.warning("V4 kayıt ve zaman serisi doğrulanamadı (%s): %s", case, exc)
        raise HTTPException(409, "Kayıt ve ham zaman serisi doğrulanamadı. Ölçüt ve animasyon kapalı.") from exc


@router.get("/recorded/{case}")
def recorded_view(case: str):
    detail, traces = recorded(case)
    return json_result({**detail.model_dump(mode="json"), "traces": traces})


@router.get("/recorded/{case}/chart.svg")
def recorded_chart(case: str):
    detail, _ = recorded(case)
    return attachment(case_svg(detail), case)


@router.get("/research")
def research():
    return json_result(research_data())

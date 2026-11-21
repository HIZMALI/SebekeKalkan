"""Public final demonstration endpoints. File paths never form part of a request."""
import logging
from html import escape
from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from .final_records import CASE_GROUPS, Card, Detail, Records
from .s02_physics import METRICS

router = APIRouter(prefix="/api/final/v1")
logger = logging.getLogger(__name__)
BROKEN = (ValueError, OSError, KeyError, TypeError, AttributeError, StopIteration, BadZipFile)
LABELS = ("Ağırlıklı hizmet açığı", "Ağırlıksız hizmet açığı", "Kritik düşük basınç", "Son onarım")
UNITS = ("ağırlıklı m³", "m³", "düğüm·saat", "saat")
METHOD_LABELS = {"fifo": "Bildirim sırası (FIFO)", "greedy": "Tekli etki/süre",
                 "s02_b6": "ŞebekeKalkan S02-B6", "proposal": "ŞebekeKalkan v2"}
GROUP_LABELS = {"dev": "Net2 geliştirme", "internal_holdout": "Net2 iç değerlendirme",
                "external_holdout": "Skeletonize dış değerlendirme"}


def checked(records, case, cards):
    if case not in CASE_GROUPS:
        raise HTTPException(404, "Gösterim vakası bulunamadı.")
    try:
        return records.verify(cards[case])
    except BROKEN as exc:
        logger.warning("Kayıtlı vaka doğrulanamadı %s: %s", case, exc)
        raise HTTPException(409, "Kaynak doğrulanamadı.") from exc


def current(case):
    if case not in CASE_GROUPS:
        raise HTTPException(404, "Gösterim vakası bulunamadı.")
    records = Records()
    try:
        cards = records.catalogue()
    except BROKEN as exc:
        logger.warning("Katalog doğrulanamadı: %s", exc)
        raise HTTPException(409, "Kaynak doğrulanamadı.") from exc
    return checked(records, case, cards)


@router.get("/catalog", response_model=list[Card], response_model_exclude_none=True)
def catalogue():
    records = Records()
    try:
        cards = records.catalogue()
    except BROKEN as exc:
        logger.warning("Katalog doğrulanamadı: %s", exc)
        cards = {}
    result = []
    for case, group in CASE_GROUPS.items():
        try:
            detail = checked(records, case, cards)
        except HTTPException:
            result.append(Card(case_id=case, group=group, status="unverified"))
            continue
        a, b = (detail.methods[key].metrics[METRICS[0]] for key in (detail.baseline, detail.comparison))
        result.append(Card(case_id=case, group=group, status="verified", network=detail.network,
                           baseline=detail.baseline, comparison=detail.comparison,
                           metrics={"baseline": a, "comparison": b}))
    return result


@router.get("/cases/{case}", response_model=Detail)
def detail(case: str):
    return current(case)


@router.get("/cases/{case}/evidence")
def evidence(case: str):
    return JSONResponse(current(case).model_dump(mode="json", exclude={"diagram"}), headers={"Cache-Control": "no-store"})


def research_data():
    try:
        return Records().research()
    except BROKEN as exc:
        logger.warning("Araştırma verisi doğrulanamadı: %s", exc)
        raise HTTPException(409, "Araştırma kaynağı doğrulanamadı.") from exc


@router.get("/research")
def research():
    return research_data()


def tr(value, places=6):
    return f"{value:,.{places}f}".translate(str.maketrans(",.", ".,"))


def svg_document(title, subtitle, parts, height):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" '
            f'viewBox="0 0 1100 {height}" role="img" aria-label="{escape(title)}">'
            f'<rect width="1100" height="{height}" fill="#f7fafb"/>'
            '<g font-family="Segoe UI, sans-serif" fill="#102c3c">'
            f'<text x="36" y="46" font-size="27" font-weight="700">{escape(title)}</text>'
            f'<text x="36" y="75" font-size="15">{escape(subtitle)}</text>{"".join(parts)}</g></svg>')


def case_svg(case):
    parts = []
    a, b = (case.methods[key] for key in (case.baseline, case.comparison))
    for index, (key, label, unit) in enumerate(zip(METRICS, LABELS, UNITS)):
        top = 136 + 126 * index
        scale = max(a.metrics[key], b.metrics[key]) or 1
        parts.append(f'<text x="36" y="{top}" font-size="20" font-weight="650">{label} ({unit})</text>')
        for i, (name, method, color) in enumerate(zip((case.baseline, case.comparison), (a, b), ("#56738c", "#007b70"))):
            y = top + 29 + i * 33
            width = 490 * method.metrics[key] / scale
            order = " → ".join(method.order or ())
            parts.append(f'<text x="36" y="{y}" font-size="14">{METHOD_LABELS[name]} · {escape(order)}</text>'
                         f'<rect x="320" y="{y-16}" width="{width:.3f}" height="18" rx="3" fill="{color}"/>'
                         f'<text x="833" y="{y}" font-size="17">{tr(method.metrics[key])}</text>')
    delta = a.metrics[METRICS[0]] - b.metrics[METRICS[0]]
    percent = "% " + tr(100 * delta / a.metrics[METRICS[0]], 2) if a.metrics[METRICS[0]] else ""
    footer = case.evidence["record_id"]
    parts.append(f'<text x="36" y="648" font-size="17">Ağırlıklı fark (referans − öneri) {tr(delta)} · {escape(percent)}</text>'
                 f'<text x="36" y="687" font-size="13">Kayıt {escape(footer)} · {escape(case.evidence["method_version"])}</text>')
    return svg_document(f"{case.case_id} · Onarım planı karşılaştırması",
                        "Kayıtlı ve doğrulanmış sonuç · Küçük değer daha iyi · Test ağı simülasyonu", parts, 714)


def group_svg(data):
    parts = []
    colors = {"WIN": "#007b70", "TIE": "#56738c", "LOSS": "#ab462d"}
    for i, group in enumerate((*GROUP_LABELS, "total")):
        counts = data["total"] if group == "total" else data["groups"][group]
        size = sum(counts.values())
        y = 132 + 76 * i
        parts.append(f'<text x="36" y="{y}" font-size="18">{GROUP_LABELS.get(group, "Toplam")} · {size}</text>')
        x = 384
        for key, color in colors.items():
            n = counts.get(key, 0)
            width = n * 39
            if n:
                parts.append(f'<rect x="{x}" y="{y-20}" width="{width}" height="31" fill="{color}"/>'
                             f'<text x="{x+12}" y="{y+1}" fill="white" font-size="16">{n}</text>')
            x += width
        parts.append(f'<text x="36" y="{y+24}" font-size="14">'
                     f'{counts.get("WIN",0)} kazanım / {counts.get("TIE",0)} eşitlik / {counts.get("LOSS",0)} kayıp</text>')
    parts.append(f'<text x="36" y="424" font-size="13">{data["source"]} · {data["source_sha256"]}</text>')
    return svg_document("Ağırlıklı hizmet açığında araştırma karşılaştırması",
                        "S02-B6 ve tekli etki/süre · Her birim ön kayıtlı bir koşulu gösterir", parts, 454)


def attachment(svg, name):
    return Response(svg, media_type="image/svg+xml", headers={"Content-Disposition": f'attachment; filename="{name}.svg"',
                                                             "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/cases/{case}/chart.svg")
def chart(case: str):
    return attachment(case_svg(current(case)), case)


@router.get("/research/chart.svg")
def research_chart():
    return attachment(group_svg(research_data()), "Sprint02-karsilastirma")

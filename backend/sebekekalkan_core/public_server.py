"""Optional isolated HTTPS API behind an approved reverse proxy."""
from collections import OrderedDict, deque
import os
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .final_v4_custom_api import router
from .final_v4_custom_input import JOBS, diagnostic_enabled
from .networks import ROOT

PREFIX = "/api/final/v2/custom"
MAX_BODY = 8192
MAX_JOBS = 24
MAX_BYTES = 384 * 1024 * 1024
WINDOW = 60
gate = Lock()
recent = deque()
clients = OrderedDict()


def permitted_origins(raw):
    origins = [value.strip() for value in raw.split(",") if value.strip()]
    for origin in origins:
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("CORS için yalnız doğrulanmış HTTPS origin değerleri kullanılabilir.")
    return origins


if diagnostic_enabled():
    raise RuntimeError("Tanı amaçlı WNTR hata modu kamuya açık serviste kullanılamaz.")

app = FastAPI(title="ŞebekeKalkan WNTR", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)
frontend = ROOT / "frontend/dist"


def denied(status, message):
    headers = {"Cache-Control": "no-store"}
    if status == 429:
        headers["Retry-After"] = str(WINDOW)
    return JSONResponse({"detail": message}, status_code=status, headers=headers)


def allow_start(host):
    now = monotonic()
    with gate:
        while recent and now - recent[0] >= WINDOW:
            recent.popleft()
        while clients and now - next(iter(clients.values())) >= WINDOW:
            clients.popitem(last=False)
        if len(recent) >= 4 or host in clients:
            return False
        recent.append(now)
        clients[host] = now
    return True


def within_quota():
    jobs = [path for path in JOBS.glob("*") if path.is_dir() and not path.is_symlink()]
    if len(jobs) >= MAX_JOBS:
        return False
    total = sum(path.stat().st_size for job in jobs for path in job.rglob("*")
                if path.is_file() and not path.is_symlink())
    return total < MAX_BYTES


@app.middleware("http")
async def public_guard(request: Request, call_next):
    if request.method == "POST" and request.url.path == PREFIX + "/jobs":
        length = request.headers.get("content-length", "")
        if not length.isascii() or not length.isdecimal() or len(length) > 5:
            return denied(411, "İstek uzunluğu gerekli.")
        if int(length) > MAX_BODY:
            return denied(413, "Senaryo gövdesi boyut sınırını aştı.")
        if request.headers.get("transfer-encoding"):
            return denied(400, "Birleşik gövde aktarımı kullanılmalı.")
        if not allow_start(request.client.host if request.client else "proxy"):
            return denied(429, "Yeni iş sınırına ulaşıldı. Bir dakika sonra yeniden deneyin.")
        if not within_quota():
            return denied(503, "Canlı çalışma kotası dolu. Kayıtlı gösterim kullanılabilir.")
    return await call_next(request)


app.add_middleware(
    CORSMiddleware, allow_origins=permitted_origins(os.getenv("SE_ALLOWED_ORIGINS", "")),
    allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition", "Retry-After"],
)


@app.get("/healthz", include_in_schema=False)
def health():
    return {"status": "ok", "live": "isolated", "solver": "WNTR"}


@app.get("/final-v4/senaryo", include_in_schema=False)
def scenario():
    return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/final-v4", include_in_schema=False)
def recorded():
    return RedirectResponse("/demo/", status_code=307)


app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="product-assets")
app.mount("/demo", StaticFiles(directory=ROOT / "showcase", html=True), name="recorded")

"""Local release entry point for the original V4.1 routes and recorded demo."""
from fastapi.staticfiles import StaticFiles

from .api_v2 import app
from .networks import ROOT


@app.get("/healthz", include_in_schema=False)
def health():
    return {"status": "ok", "recorded": "recorded_verified", "live": "local", "solver": "WNTR"}


app.mount("/demo", StaticFiles(directory=ROOT / "showcase", html=True), name="recorded-demo")

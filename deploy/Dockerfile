FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib \
    PYTHONPATH=/srv/runtime/01_GELISTIRME_KAYNAK/backend OPENBLAS_NUM_THREADS=1
WORKDIR /srv/source
COPY requirements-lock.txt .
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements-lock.txt \
    && python -m pip check
COPY backend backend
COPY data data
COPY experiments/configs experiments/configs
COPY frontend/dist frontend/dist
COPY scripts scripts
COPY docs docs
RUN python scripts/stage_runtime.py /srv/runtime \
    && chmod -R a+rX /srv/runtime \
    && mkdir -p /srv/runtime/01_GELISTIRME_KAYNAK/.calisma /srv/runtime/01_GELISTIRME_KAYNAK/.cache/tmp \
    && chown -R 10001:10001 /srv/runtime/01_GELISTIRME_KAYNAK/.calisma /srv/runtime/01_GELISTIRME_KAYNAK/.cache
WORKDIR /srv/runtime/01_GELISTIRME_KAYNAK
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD ["python","-c","import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).read()"]
CMD ["python","-m","uvicorn","sebekekalkan_core.release_server:app","--host","0.0.0.0","--port","8000","--no-proxy-headers","--workers","1"]

"""Local independent API. Each bounded hydraulic job executes in its own process."""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .contracts import Scenario
from .hydraulics import validate_network
from .networks import MODEL, ROOT, AnalysisError, load_model, network_data
from .planning import write_json

TIMEOUT_SECONDS = 90
EVIDENCE = ROOT / '.calisma/legacy_api'
app = FastAPI(title='ŞebekeKalkan', docs_url=None, redoc_url=None, openapi_url=None)
pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='sebeke')
guard = threading.Lock()
jobs = {}
active = False


@app.exception_handler(StarletteHTTPException)
async def http_error(request, error):
    standard = {404: 'İstenen adres bulunamadı.', 405: 'Bu işlem bu adreste desteklenmiyor.'}
    message = standard.get(error.status_code, 'İşlem tamamlanamadı.') if error.detail in ('Not Found', 'Method Not Allowed') else str(error.detail)
    return JSONResponse({'message': message}, status_code=error.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    fields = {'crews': 'Ekip sayısı (1–3)', 'failures': 'Arızalar (1–3 boru)', 'repair_hours': 'Onarım süresi (0–12 saat)',
              'horizon_hours': 'Analiz ufku (2–48 saat)', 'critical_weights': 'Kritik düğüm katsayısı (1–10)',
              'failure_start_hour': 'Arıza başlangıcı', 'step_minutes': 'Örnekleme adımı', 'hydraulic_trials': 'Çözücü deneme sınırı'}
    if request.url.path == '/api/final/v2/custom/jobs':
        fields.update({'crews': 'Ekip sayısı (1–2)', 'faults': 'Arızalar (3–4 farklı boru)',
                       'repair_hours': 'Onarım süresi (2–5 tam saat)', 'network': 'Örnek şebeke (Net2 veya Skeletonize)',
                       'search': 'Arama kapsamı (hızlı veya kapsamlı)', 'pipe_id': 'Boru kimliği'})
    messages = []
    for item in error.errors():
        context = item.get('ctx', {})
        custom = str(context['error']) if 'error' in context else None
        field = next((fields[str(x)] for x in reversed(item['loc']) if str(x) in fields), 'Girdi')
        messages.append(custom or field + ': geçerli aralıkta bir değer girin.')
    return JSONResponse({'message': 'Girdiler doğrulanamadı. ' + ' '.join(dict.fromkeys(messages))}, status_code=422)


@app.exception_handler(AnalysisError)
async def analysis_error(request, error):
    return JSONResponse({'message': str(error)}, status_code=422)


@app.get('/api/health')
def health():
    return {'application': 'ŞebekeKalkan', 'status': 'hazır', 'solver': 'EPANET 2.2', 'timeout_seconds': TIMEOUT_SECONDS}


@app.get('/api/network')
def network():
    return network_data()


@app.get('/api/example')
def example():
    return Scenario.model_validate_json((ROOT / 'experiments/configs/example.json').read_text(encoding='utf-8')).model_dump()


@app.post('/api/scenario/validate')
def validate_scenario(scenario: Scenario):
    validate_network(scenario, load_model())
    return scenario.model_dump()


@app.post('/api/network/verify')
async def verify_network(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 2_000_000:
            raise HTTPException(413, 'Ağ dosyası 2 MB sınırını aşıyor.')
    if not data:
        return JSONResponse({'message': 'Ağ dosyası boş. Tam Net3 .inp dosyasını seçin.'}, status_code=422)
    if hashlib.sha256(data).digest() != hashlib.sha256(MODEL.read_bytes()).digest():
        return JSONResponse({'message': 'Bu dosya doğrulanmış tam Net3 modeliyle eşleşmiyor. Bu sürüm yalnız kayıtlı Net3 ağını destekler.'}, status_code=422)
    return network_data()


def run_job(identifier, scenario):
    global active
    folder = EVIDENCE / identifier
    started = time.monotonic()
    jobs[identifier] = {'status': 'running', 'message': 'Gerçek EPANET hidrolik çözümleri hesaplanıyor.'}
    try:
        folder.mkdir(parents=True, exist_ok=False)
        write_json(folder / 'input.json', scenario.model_dump())
        temp = ROOT / '.cache/tmp'
        temp.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONUTF8='1', MPLCONFIGDIR=str(ROOT / '.cache/matplotlib'), TEMP=str(temp), TMP=str(temp))
        with (folder / 'worker.log').open('wb') as logfile:
            # Share the launcher's console so Windows Ctrl+C also stops the worker.
            process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'sebekekalkan_core.experiment',
                                        '--config', str(folder / 'input.json'), '--output', str(folder)],
                                       cwd=ROOT, env=env, stdout=logfile, stderr=subprocess.STDOUT)
            try:
                process.wait(timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10)
                else:
                    process.kill()
                process.wait(timeout=10)
                raise AnalysisError('Hesaplama 90 saniye sınırına ulaştı. Analiz ufkunu veya arıza sayısını azaltın.')
        if process.returncode != 0:
            failure = folder / 'failure.json'
            message = json.loads(failure.read_text(encoding='utf-8'))['message'] if failure.exists() else 'Hidrolik hesaplama tamamlanamadı; deney günlüğünü kontrol edin.'
            raise AnalysisError(message)
        result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        jobs[identifier] = {'status': 'completed', 'message': 'Hesaplama ve bağımsız sıra doğrulaması tamamlandı.', 'result': result}
    except Exception as error:
        jobs[identifier] = {'status': 'failed', 'message': str(error) if isinstance(error, AnalysisError) else 'Hesaplama tamamlanamadı. Deney kaydını kontrol edin.'}
    finally:
        jobs[identifier]['elapsed_seconds'] = time.monotonic() - started
        with guard:
            active = False
        if folder.is_dir():
            write_json(folder / 'job.json', {k: v for k, v in jobs[identifier].items() if k != 'result'})


@app.post('/api/experiments', status_code=202)
def submit(scenario: Scenario):
    global active
    validate_network(scenario, load_model())
    with guard:
        if active:
            return JSONResponse({'message': 'Bir hesaplama sürüyor. Tamamlanmasını bekleyip yeniden deneyin.'}, status_code=429)
        active = True
    identifier = uuid.uuid4().hex
    jobs[identifier] = {'status': 'queued', 'message': 'Girdiler doğrulandı; hesaplama hazırlanıyor.'}
    pool.submit(run_job, identifier, scenario)
    return {'id': identifier, 'status': 'queued'}


def require_job(identifier):
    if not re.fullmatch('[a-f0-9]{32}', identifier) or identifier not in jobs:
        raise HTTPException(404, 'Deney bulunamadı. Yeni bir hesaplama başlatın.')
    return jobs[identifier]


@app.get('/api/experiments/{identifier}')
def job(identifier: str):
    state = require_job(identifier)
    return {'id': identifier, **state}


@app.get('/api/experiments/{identifier}/export/{kind}')
def export(identifier: str, kind: str):
    if require_job(identifier)['status'] != 'completed':
        raise HTTPException(409, 'Dışa aktarmak için başarılı hesaplamayı bekleyin.')
    files = {'json': ('result.json', 'application/json'), 'csv': ('summary.csv', 'text/csv; charset=utf-8')}
    if kind not in files:
        raise HTTPException(404, 'Bu dışa aktarma türü desteklenmiyor.')
    name, media = files[kind]
    return FileResponse(EVIDENCE / identifier / name, media_type=media, filename='SebekeKalkan-' + identifier[:8] + '.' + kind)


from .final_api import router as final_router
from .final_live import router as final_live_router
from .final_v4_recorded import router as final_v4_recorded_router
from .final_v4_custom_api import router as final_v4_custom_router

app.include_router(final_router)
app.include_router(final_live_router)
app.include_router(final_v4_recorded_router)
app.include_router(final_v4_custom_router)
dist = ROOT / 'frontend/dist'
if (dist / 'assets').is_dir():
    app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')


@app.get('/favicon.svg', include_in_schema=False)
def favicon():
    path = dist / 'favicon.svg'
    if not path.is_file():
        raise HTTPException(404, 'Arayüz simgesi bulunamadı.')
    return FileResponse(path, media_type='image/svg+xml')


@app.get('/')
@app.get('/final')
@app.get('/final-v4')
@app.get('/final-v4/senaryo')
def home():
    if not (dist / 'index.html').is_file():
        return JSONResponse({'message': 'Arayüz henüz derlenmedi. scripts/start-web.ps1 komutunu çalıştırın.'}, status_code=503)
    return FileResponse(dist / 'index.html', headers={'Cache-Control': 'no-cache'})

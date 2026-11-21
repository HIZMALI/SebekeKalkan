"""Sürüm bilgili WNTR/v2 API; v1 algoritması kendi uçlarında korunur."""
from pathlib import Path
import csv
from io import StringIO
import json,os,re,subprocess,sys,time,uuid
from fastapi import HTTPException
from fastapi.responses import JSONResponse,Response
from . import api as legacy
from .contracts_v2 import ScenarioV2
from .hydraulics import validate_network
from .networks import ROOT,load_model,AnalysisError
from .planning import write_json
from .planning_v2 import VERSION

app=legacy.app
EVIDENCE=ROOT/'.calisma/api_v2'
jobs={};processes={};cancelled=set()

def stop(process):
    if process.poll() is None:
        if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10)
        else:process.kill()

@app.get('/api/v2/health')
def health_v2():
    return {'application':'ŞebekeKalkan','status':'hazır','model_version':VERSION,'solver':'WNTRSimulator 1.5.0','decision_policy':'decision_policy_v2','physical_gate':'Her gerçek koşuda zorunlu','scientific_decision':'NO-GO-BILIMSEL','timeout_seconds':180}

@app.get('/api/v2/example')
def example_v2():
    return ScenarioV2.model_validate_json((ROOT/'experiments/configs/master_jury.json').read_text(encoding='utf-8')).model_dump()

@app.post('/api/v2/scenario/validate')
def validate_v2(scenario:ScenarioV2):
    validate_network(scenario,load_model());return scenario.model_dump()

def run_job(identifier,scenario):
    folder=EVIDENCE/identifier;started=time.monotonic()
    jobs[identifier]={'status':'running','message':'Gerçek WNTR çözümleri ve iç olay fizik kapıları hesaplanıyor.'}
    try:
        folder.mkdir(parents=True,exist_ok=False);write_json(folder/'input.json',scenario.model_dump())
        tmp=ROOT/'.cache/tmp';tmp.mkdir(parents=True,exist_ok=True)
        env=dict(os.environ,PYTHONUTF8='1',TEMP=str(tmp),TMP=str(tmp),MPLCONFIGDIR=str(ROOT/'.cache/matplotlib'))
        with (folder/'worker.log').open('wb') as log:
            process=subprocess.Popen([sys.executable,'-X','utf8','-m','sebekekalkan_core.experiment_v2','--config',str(folder/'input.json'),'--output',str(folder)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            processes[identifier]=process
            if identifier in cancelled:stop(process)
            try:process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                stop(process);process.wait(timeout=10)
                raise AnalysisError('WNTR hesaplaması 180 saniye sınırına ulaştı. Analiz ufkunu azaltın.')
        if identifier in cancelled:raise AnalysisError('Hesaplama kullanıcı tarafından iptal edildi; geçerli sonuç sunulmadı.')
        if process.returncode:
            p=folder/'failure.json';failure=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
            raise AnalysisError(failure.get('message','WNTR hesaplaması tamamlanamadı; deney kaydını kontrol edin.'))
        result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
        if result.get('model_version')!=VERSION or not result.get('physical_validation',{}).get('pass'):raise AnalysisError('Sürüm/fizik kabulü doğrulanmadı; sonuç reddedildi.')
        result['record_id'] = identifier
        jobs[identifier]={'status':'completed','message':'WNTR fizik kapıları ve bağımsız v2 sıra doğrulaması tamamlandı.','result':result}
    except Exception as error:
        jobs[identifier]={'status':'failed','message':str(error) if isinstance(error,AnalysisError) else 'Hesaplama tamamlanamadı; deney kaydını kontrol edin.'}
    finally:
        processes.pop(identifier,None);jobs[identifier]['elapsed_seconds']=time.monotonic()-started
        with legacy.guard:legacy.active=False
        if folder.is_dir():write_json(folder/'job.json',{k:v for k,v in jobs[identifier].items() if k!='result'})

@app.post('/api/v2/experiments',status_code=202)
def submit_v2(scenario:ScenarioV2):
    validate_network(scenario,load_model())
    with legacy.guard:
        if legacy.active:return JSONResponse({'message':'Bir hesaplama sürüyor; tamamlanmasını bekleyin veya iptal edin.'},status_code=429)
        legacy.active=True
    identifier=uuid.uuid4().hex;jobs[identifier]={'status':'queued','message':'WNTR/v2 hesabı hazırlanıyor.'}
    legacy.pool.submit(run_job,identifier,scenario)
    return {'id':identifier,'status':'queued','model_version':VERSION}

def require(identifier):
    if not re.fullmatch('[a-f0-9]{32}',identifier) or identifier not in jobs:raise HTTPException(404,'Deney bulunamadı; yeni hesaplama başlatın.')
    return jobs[identifier]

@app.get('/api/v2/experiments/{identifier}')
def get_v2(identifier:str):return {'id':identifier,**require(identifier)}

@app.post('/api/v2/experiments/{identifier}/cancel')
def cancel_v2(identifier:str):
    job=require(identifier)
    if job['status'] in ['completed','failed']:raise HTTPException(409,'Bu hesaplama zaten tamamlandı.')
    cancelled.add(identifier)
    if identifier in processes:stop(processes[identifier])
    return {'status':'cancelling','message':'İptal istendi; geçerli sonuç üretilmeyecek.'}

@app.get('/api/v2/experiments/{identifier}/export/{kind}')
def export_v2(identifier:str,kind:str):
    job = require(identifier)
    if job['status'] != 'completed' or not job['result']['physical_validation']['pass']:
        raise HTTPException(409, 'Dışa aktarmak için fizik kapısından geçmiş sonucu bekleyin.')
    if kind not in {'json', 'csv', 'pdf'}:
        raise HTTPException(404, 'Bu dosya türü desteklenmiyor.')
    headers = {'Content-Disposition': f'attachment; filename="SebekeKalkan-{identifier}.{kind}"'}
    result = job['result']
    if kind == 'json':
        return JSONResponse(result, headers=headers)
    if kind == 'pdf':
        from .pdf_report import report_bytes
        return Response(report_bytes(result), media_type='application/pdf', headers=headers)

    output = StringIO()
    writer = csv.writer(output, delimiter=';')
    with (EVIDENCE / identifier / 'summary.csv').open(encoding='utf-8-sig', newline='') as source:
        reader = csv.reader(source, delimiter=';')
        writer.writerow([*next(reader), 'Kayıt kimliği'])
        writer.writerows([*row, identifier] for row in reader)
    return Response(output.getvalue().encode('utf-8-sig'), media_type='text/csv', headers=headers)

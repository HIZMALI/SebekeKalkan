import csv
import time
from io import StringIO
import pytest
from fastapi.testclient import TestClient
from sebekekalkan_core import api_v2
from sebekekalkan_core.contracts_v2 import ScenarioV2
from sebekekalkan_core.pdf_report import report_bytes
from sebekekalkan_core.planning_v2 import reference_matches

def wait(c,ident):
    # API contract allows 180 seconds plus process teardown. A fixed 40-second
    # test deadline rejected an actual valid 81.485-second cold run.
    budget=c.get('/api/v2/health').json()['timeout_seconds']
    deadline=time.monotonic()+budget+15
    while time.monotonic()<deadline:
        r=c.get('/api/v2/experiments/'+ident).json()
        if r['status'] in ['failed','completed']:return r
        time.sleep(.1)
    c.post(f'/api/v2/experiments/{ident}/cancel')
    pytest.fail(f'V2 hesabı API süresi + 15 saniye kapanış payında tamamlanmadı: {r}')

@pytest.fixture(scope='module')
def real_v2(tmp_path_factory):
    api_v2.EVIDENCE=tmp_path_factory.mktemp('master-api-v2')
    with TestClient(api_v2.app) as c:
        p=c.get('/api/v2/example').json();submitted=c.post('/api/v2/experiments',json=p)
        assert submitted.status_code==202
        ident=submitted.json()['id']
        try:
            job=wait(c,ident)
            assert job['status']=='completed',job
            yield c,ident,job['result']
        finally:
            current=c.get('/api/v2/experiments/'+ident).json()
            if current['status'] in ['queued','running']:
                c.post(f'/api/v2/experiments/{ident}/cancel')
                wait(c,ident)

def test_versioned_health_and_separate_newton_parameter():
    with TestClient(api_v2.app) as c:
        h=c.get('/api/v2/health').json();assert h['decision_policy']=='decision_policy_v2' and 'WNTR' in h['solver']
        assert c.get('/api/health').json()['solver']=='EPANET 2.2'
        p=c.get('/api/v2/example').json();assert p['wntr_max_iterations']==3000 and p['hydraulic_trials']==40
        p['wntr_max_iterations']=0;assert c.post('/api/v2/experiments',json=p).status_code==422

def test_real_t11_c2_v2_is_seven_hours(real_v2):
    _,_,r=real_v2
    assert r['model_version']=='SK-WNTR-v2.0'
    assert r['decision']['selected']['order']==['153','193','112']
    assert r['methods']['proposal']['metrics']['repair_completion_hour']==7
    assert r['search']['candidate_count']==6 and r['search']['oracle_verified']

def test_every_actual_candidate_and_oracle_has_physical_gate(real_v2):
    _,_,r=real_v2
    assert r['physical_validation']=={'pass':True,'plans_checked':16,'scope':r['physical_validation']['scope']}
    for m in [r['baseline'],*r['methods'].values()]:
        assert m['physical_gate']['pass'] and m['physical_gate']['maxiter']==3000
        assert all(t['mass_balance_pass'] and t['bounds_pass'] for t in m['physical_gate']['tanks'].values())
    assert r['leakage_volume_m3'] is None

def test_v2_exports_and_comparators_use_one_policy(real_v2):
    c,ident,r=real_v2
    prefix = f'/api/v2/experiments/{ident}/export'
    assert r['record_id'] == ident
    downloaded_json = c.get(f'{prefix}/json')
    downloaded_csv = c.get(f'{prefix}/csv')
    pdf = c.get(f'{prefix}/pdf')
    assert downloaded_json.json() == r
    rows = list(csv.DictReader(StringIO(downloaded_csv.content.decode('utf-8-sig')), delimiter=';'))
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-') and pdf.headers['content-type']=='application/pdf'
    assert len(rows) > 20
    assert all(row['Kayıt kimliği'] == ident and row['Girdi SHA-256'] == r['input_sha256'] for row in rows)
    for response in (downloaded_json, downloaded_csv, pdf):
        assert ident in response.headers['content-disposition']
    for m in r['methods'].values():assert m['decision_classification']['decision_sha256']==r['decision']['decision_sha256']


def test_pdf_accepts_successful_scenario_without_manual_order(real_v2):
    _, _, result = real_v2
    methods = {key: method for key, method in result['methods'].items() if key != 'manual'}
    assert report_bytes({**result, 'methods': methods}).startswith(b'%PDF-')

def test_v2_unknown_job_cannot_export():
    with TestClient(api_v2.app) as c:
        assert c.get('/api/v2/experiments/not-an-id/export/json').status_code==404
        assert c.post('/api/v2/experiments/not-an-id/cancel').status_code==404

def test_actual_wntr_failure_is_not_reported_as_success():
    with TestClient(api_v2.app) as c:
        p=c.get('/api/v2/example').json();p['wntr_max_iterations']=1
        q=c.post('/api/v2/experiments',json=p);assert q.status_code==202
        ident=q.json()['id'];r=wait(c,ident)
        assert r['status']=='failed' and 'WNTR' in r['message'] and 'result' not in r
        for kind in ('json', 'csv', 'pdf'):
            assert c.get(f'/api/v2/experiments/{ident}/export/{kind}').status_code == 409

def test_real_worker_cancellation_blocks_export():
    with TestClient(api_v2.app) as c:
        p=c.get('/api/v2/example').json();q=c.post('/api/v2/experiments',json=p);assert q.status_code==202
        ident=q.json()['id'];assert c.post(f'/api/v2/experiments/{ident}/cancel').status_code==200
        r=wait(c,ident);assert r['status']=='failed' and 'iptal' in r['message']
        assert c.get(f'/api/v2/experiments/{ident}/export/json').status_code==409

@pytest.mark.parametrize('offset,expected',[(2.3e-13,True),(1.,False)])
def test_oracle_uses_registered_numeric_tolerance(offset,expected):
    a={'selected':{'order':['195','201','179'],'objective':[555.4341347425249,.25,8]}}
    b={'selected':{'order':['195','201','179'],'objective':[555.4341347425249+offset,.25,8]}}
    assert reference_matches(a,b)==expected

def test_oracle_rejects_different_selected_order_even_if_metrics_equal():
    a={'selected':{'order':['A','B'],'objective':[1,0,2]}}
    b={'selected':{'order':['B','A'],'objective':[1,0,2]}}
    assert not reference_matches(a,b)

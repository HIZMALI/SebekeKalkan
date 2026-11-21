import json
import time
import uuid

from fastapi.testclient import TestClient
import pytest

from sebekekalkan_core import api
from sebekekalkan_core.networks import MODEL

client=TestClient(api.app)


def wait(identifier):
    # The server's wall-clock deadline includes a separate worker startup.
    limit = client.get('/api/health').json()['timeout_seconds']
    deadline = time.monotonic() + limit + 15
    while time.monotonic() < deadline:
        response=client.get('/api/experiments/'+identifier)
        assert response.status_code==200
        data=response.json()
        if data['status'] in ('completed','failed'):
            return data
        time.sleep(.25)
    pytest.fail(f'Gerçek API işi {limit} saniyelik sunucu sınırı ve kapanış payında bitmedi: {data}')


def test_health_and_original_network():
    assert client.get('/api/health').json()['application']=='ŞebekeKalkan'
    assert client.get('/api/network').json()['inventory']['nodes']==97
    assert client.get('/api/example').json()['failures'][0]['pipe_id']=='137'


@pytest.mark.parametrize('data',[b'',b'broken model'])
def test_invalid_model_file(data):
    result=client.post('/api/network/verify',content=data)
    assert result.status_code==422
    assert 'message' in result.json()


def test_pinned_upload_and_size_limit():
    assert client.post('/api/network/verify',content=MODEL.read_bytes()).status_code==200
    assert client.post('/api/network/verify',content=b'x'*2_000_001).status_code==413


@pytest.mark.parametrize('patch',[{'crews':0},{'failures':[]},{'failures':[{'pipe_id':'bad','repair_hours':1}]}])
def test_turkish_validation_errors(scenario,patch):
    result=client.post('/api/experiments',json={**scenario.model_dump(),**patch})
    assert result.status_code==422
    assert 'message' in result.json()
    assert 'Input should' not in result.text


def test_real_async_job_exports_and_no_result_on_failure(scenario):
    response=client.post('/api/experiments',json=scenario.model_dump())
    assert response.status_code==202
    identifier=response.json()['id']
    second=client.post('/api/experiments',json=scenario.model_dump())
    assert second.status_code==429
    assert 'hesaplama sürüyor' in second.json()['message']
    data=wait(identifier)
    assert data['status']=='completed',data
    assert data['result']['search']['oracle_verified']
    exported=client.get(f'/api/experiments/{identifier}/export/json').json()
    assert exported['input']==scenario.model_dump()
    assert exported['input_sha256']==data['result']['input_sha256']
    csv=client.get(f'/api/experiments/{identifier}/export/csv')
    assert 'Karşılanamayan talep' in csv.content.decode('utf-8-sig')
    assert client.get(f'/api/experiments/{identifier}/export/unsupported').status_code==404
    scenario.hydraulic_trials=1
    response=client.post('/api/experiments',json=scenario.model_dump())
    assert response.status_code == 202, response.text
    failed=wait(response.json()['id'])
    assert failed['status']=='failed'
    assert 'result' not in failed
    assert 'EPANET' in failed['message']
    assert client.get(f"/api/experiments/{response.json()['id']}/export/json").status_code==409


def test_unknown_routes_are_turkish():
    assert client.get('/api/missing').json()['message']=='İstenen adres bulunamadı.'
    assert client.get('/api/experiments/../../etc/passwd').status_code==404


def test_owned_worker_timeout_is_visible(monkeypatch,scenario):
    monkeypatch.setattr(api,'TIMEOUT_SECONDS',.001)
    response=client.post('/api/experiments',json=scenario.model_dump())
    assert response.status_code == 202, response.text
    failed=wait(response.json()['id'])
    assert failed['status']=='failed'
    assert 'sınırına ulaştı' in failed['message']
    assert 'result' not in failed

"""Comprobaciones adicionales de seguridad ejecutables con el conftest real."""
import base64
import json
import time
import pytest
from tests.conftest import API, envelope, example, full_session

def test_jwt_none_rejected(client, api):
    user = api.make_user()
    def enc(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=').decode()
    token = enc({'alg':'none','typ':'JWT'}) + '.' + enc({'sub':user['id'],'role':'admin','exp':int(time.time())+600}) + '.'
    r = client.get(f'{API}/me', headers={'Authorization':f'Bearer {token}'})
    assert r.status_code >= 400
    assert r.headers['content-type'].startswith('application/problem+json')

def test_register_admin_mass_assignment(client, api):
    body = example('auth_register.request.json')
    body.update(email='security-mass@example.com', role='admin')
    r = client.post(f'{API}/auth/register', json=body)
    assert r.status_code >= 400
    from app.db.session import get_engine
    from sqlalchemy import text
    with get_engine().connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM identity.users WHERE email=:email'), {'email':body['email']}).scalar_one() == 0

@pytest.mark.parametrize('payload', ["' OR '1'='1", "x'; SELECT 1; --", "O'Reilly"])
def test_sql_text_literal(client, api, admin, payload):
    patient = api.make_user()
    pro, headers = api.user_with_headers('professional')
    api.assign(admin[1], pro, patient)
    path = f"{API}/patients/{patient['id']}/notes"
    r = client.post(path, json={'text':payload}, headers=headers)
    assert 200 <= r.status_code < 300
    result = client.get(path, headers=headers)
    assert result.status_code == 200
    assert payload in [note['text'] for note in result.json()['items']]
    assert client.get(f'{API}/admin/users', headers=headers).status_code >= 400

def test_patient_session_bola(client, api):
    _, own = api.user_with_headers('patient')
    _, other = api.user_with_headers('patient')
    device = api.pair(own)
    sid = full_session(api, device['headers'])
    assert client.get(f'{API}/me/sessions/{sid}', headers=own).status_code == 200
    r = client.get(f'{API}/me/sessions/{sid}', headers=other)
    assert r.status_code >= 400
    assert sid not in r.text

@pytest.mark.parametrize('delta', [-1,0,1])
def test_exact_record_size(client, api, delta):
    _, headers = api.user_with_headers('patient')
    device = api.pair(headers)
    limit = 256*1024
    body = json.dumps(envelope('session_start'), separators=(',',':')).encode()
    body += b' '*(limit+delta-len(body))
    r = client.post(f'{API}/device/records', content=body, headers={**device['headers'],'Content-Type':'application/json'})
    assert r.status_code == 413 if delta > 0 else 200 <= r.status_code < 300

def test_forged_ip_cannot_evade_quota(client, app, monkeypatch):
    from app.core.config import get_settings
    from pydantic import SecretStr
    monkeypatch.setattr(get_settings(), 'proxy_secret', SecretStr('x'*48))
    for i in range(11):
        r = client.post(f'{API}/auth/login', json={'email':f'unknown{i}@example.com','password':'invalid-password'}, headers={'x-np-client-ip':f'192.0.2.{i+1}'})
        assert r.status_code == 429 if i == 10 else r.status_code != 429
    assert int(r.headers['retry-after']) > 0

def test_sensitive_cache_header(client, api):
    _, headers = api.user_with_headers('patient')
    r = client.get(f'{API}/me', headers=headers)
    assert r.status_code == 200
    assert 'no-store' in r.headers.get('cache-control','').lower(), 'Respuesta de perfil sin Cache-Control no-store'

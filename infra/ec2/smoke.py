"""Verify the deployed HTTPS origin without printing credentials or tokens."""
import http.cookiejar
import json
import re
import secrets
from pathlib import Path
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent


class Api:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.token = None

    def call(self, path, method='GET', body=None, expected=200):
        headers = {'Accept': 'application/json'}
        if self.token: headers['Authorization'] = 'Bearer '+self.token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.base+'/api/v1'+path, data=data, method=method, headers=headers)
        try: response = self.http.open(request, timeout=40)
        except urllib.error.HTTPError as exc: response = exc
        status = response.status
        payload = response.read()
        if status != expected: raise RuntimeError(f'{method} {path} returned {status}; expected {expected}')
        if path.startswith('/auth/'):
            if 'no-store' not in response.headers.get('Cache-Control', ''): raise RuntimeError('Authentication response is cacheable')
        if path == '/auth/login' and status == 200:
            cookies = ';'.join(response.headers.get_all('Set-Cookie') or []).lower()
            for attribute in ['httponly', 'secure', 'samesite=strict', 'path=/api/v1/auth']:
                if attribute not in cookies: raise RuntimeError('Refresh cookie missing '+attribute)
        return json.loads(payload) if payload else None


def main():
    out = json.loads((HERE/'outputs.json').read_text())
    base = out['WebUrl']
    html = urllib.request.urlopen(base, timeout=40).read().decode()
    if '<div id="root">' not in html: raise RuntimeError('Frontend not served')
    route = urllib.request.urlopen(base+'/paciente', timeout=40).read().decode()
    if html != route: raise RuntimeError('SPA fallback failed')
    for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html):
        if urllib.request.urlopen(base+asset, timeout=40).status != 200: raise RuntimeError('Asset failed')
    api = Api(base)
    if api.call('/health/ready')['database'] != 'ok': raise RuntimeError('Database unavailable')
    api.call('/public/product-info')
    credentials = json.loads((HERE.parents[2]/'NP_Coordinacion/privado/neurophobia-admin-inicial.json').read_text(encoding='utf-8'))
    login = api.call('/auth/login', 'POST', {'email': credentials['email'], 'password': credentials['password']})
    if login['user']['role'] != 'admin': raise RuntimeError('Unexpected administrator role')
    api.token = login['accessToken']
    api.call('/admin/users')
    api.call('/patients', expected=403)
    api.token = api.call('/auth/refresh', 'POST', {})['accessToken']
    api.call('/auth/logout', 'POST', {}, expected=204)
    api.call('/auth/refresh', 'POST', {}, expected=401)
    # Fictitious end-to-end patient/visor check; withdraw consent afterwards.
    patient = Api(base)
    email, password = 'aws-smoke-'+secrets.token_hex(6)+'@example.com', secrets.token_urlsafe(24)
    patient.call('/auth/register', 'POST', {'fullName': 'Prueba técnica AWS', 'email': email, 'password': password, 'consent': {'accepted': True, 'consentVersion': 'technical-smoke-no-participant'}}, expected=201)
    patient.token = patient.call('/auth/login', 'POST', {'email': email, 'password': password})['accessToken']
    patient.call('/me/therapy')
    patient.call('/admin/users', expected=403)
    code = patient.call('/pairing-codes', 'POST', {}, expected=201)['code']
    device = Api(base)
    paired = device.call('/device/pair', 'POST', {'code': code, 'deviceModel': 'TechnicalTest', 'appVersion': '0.2.0'}, expected=201)
    device.token = paired['deviceToken']
    device.call('/device/context')
    patient.call('/me/consents/withdraw', 'POST', {}, expected=202)
    device.call('/device/context', expected=401)
    print(json.dumps({'web': base, 'https': 'ok', 'spa': 'ok', 'database': 'ok', 'adminLoginRefreshLogout': 'ok', 'roles': 'ok', 'patientPairingRevocation': 'ok'}, indent=2))


if __name__ == '__main__': main()

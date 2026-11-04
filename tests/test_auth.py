"""Registro, inicio y cierre de sesión, refresco rotativo (contrato, secciones 4.1 y 4.2)."""

import time

import jwt

from tests.conftest import API, example


def _register_body(**changes) -> dict:
    body = example("auth_register.request.json")
    body.update({"email": "nueva@example.com", "password": "clave-segura-123", **changes})
    return body


def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json() == example("health.response.200.json")


def test_register_creates_patient_without_professional(client, api, admin):
    r = client.post(f"{API}/auth/register", json=_register_body())
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "patient" and set(body) == {"userId", "role"}
    # D18: nadie lo tiene asignado.
    _, admin_headers = admin
    assert client.get(f"{API}/admin/assignments", headers=admin_headers).json()["items"] == []


def test_register_email_taken(client):
    assert client.post(f"{API}/auth/register", json=_register_body()).status_code == 201
    r = client.post(f"{API}/auth/register", json=_register_body(email="NUEVA@example.com"))
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "EMAIL_TAKEN"


def test_register_requires_consent(client):
    for consent in ({"accepted": False, "consentVersion": "2026-10-v1"}, None):
        body = _register_body()
        if consent is None:
            body.pop("consent")
        else:
            body["consent"] = consent
        r = client.post(f"{API}/auth/register", json=body)
        assert r.status_code == 422
        assert r.json()["code"] == "CONSENT_REQUIRED"


def test_register_validation_errors_by_field(client):
    r = client.post(f"{API}/auth/register", json=_register_body(email="no-es-correo", password="corta"))
    assert r.status_code == 422
    problem = r.json()
    assert problem["code"] == "VALIDATION_ERROR"
    fields = {e["field"]: e["code"] for e in problem["errors"]}
    assert fields["email"] == "invalid_format"
    assert fields["password"] == "too_short"
    # Nunca se repite el valor recibido.
    assert "no-es-correo" not in r.text


def test_register_malformed_json(client):
    r = client.post(f"{API}/auth/register", content=b"{no json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["code"] == "BAD_REQUEST"


def test_register_rate_limited(client):
    from app.core.config import get_settings

    for i in range(get_settings().register_max_per_window):
        client.post(f"{API}/auth/register", json=_register_body(email=f"r{i}@example.com"))
    r = client.post(f"{API}/auth/register", json=_register_body(email="otra@example.com"))
    assert r.status_code == 429
    assert r.json()["code"] == "RATE_LIMITED"
    assert "retry-after" in r.headers


def test_login_returns_token_and_refresh_cookie(client, api):
    user = api.make_user("professional")
    r = client.post(f"{API}/auth/login", json={"email": user["email"], "password": user["password"]})
    assert r.status_code == 200
    body = r.json()
    assert body["expiresIn"] == 900
    assert body["user"] == {"id": user["id"], "role": "professional"}
    claims = jwt.decode(body["accessToken"], options={"verify_signature": False})
    # El JWT solo lleva sub, role y exp: nada de nombre ni correo.
    assert set(claims) == {"sub", "role", "exp"}
    cookie = r.headers["set-cookie"]
    for flag in ("np_refresh=", "HttpOnly", "Secure", "SameSite=strict", "Path=/api/v1/auth"):
        assert flag.lower() in cookie.lower()


def test_login_invalid_credentials_does_not_say_what_failed(client, api):
    user = api.make_user()
    wrong_password = client.post(f"{API}/auth/login", json={"email": user["email"], "password": "otra-clave-x"})
    unknown_email = client.post(f"{API}/auth/login", json={"email": "nadie@example.com", "password": "otra-clave-x"})
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["code"] == "INVALID_CREDENTIALS"


def test_login_account_disabled(client, api):
    user = api.make_user(active=False)
    r = client.post(f"{API}/auth/login", json={"email": user["email"], "password": user["password"]})
    assert r.status_code == 423
    assert r.json()["code"] == "ACCOUNT_DISABLED"


def test_login_rate_limited(client, api):
    from app.core.config import get_settings

    user = api.make_user()
    for _ in range(get_settings().login_max_per_window):
        client.post(f"{API}/auth/login", json={"email": user["email"], "password": "mala-clave-1"})
    r = client.post(f"{API}/auth/login", json={"email": user["email"], "password": user["password"]})
    assert r.status_code == 429


def test_refresh_rotates_cookie_and_detects_reuse(client, api):
    user = api.make_user()
    api.login(user)
    old = client.cookies.get("np_refresh")
    r = client.post(f"{API}/auth/refresh")
    assert r.status_code == 200
    assert set(r.json()) == {"accessToken", "expiresIn"}
    new = client.cookies.get("np_refresh")
    assert new and new != old
    # Reutilizar el token viejo revoca toda la familia.
    client.cookies.clear()
    client.cookies.set("np_refresh", old, path="/api/v1/auth")
    assert client.post(f"{API}/auth/refresh").status_code == 401
    client.cookies.clear()
    client.cookies.set("np_refresh", new, path="/api/v1/auth")
    assert client.post(f"{API}/auth/refresh").status_code == 401


def test_refresh_without_cookie(client):
    r = client.post(f"{API}/auth/refresh")
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHENTICATED"


def test_refresh_expired(client, api):
    from sqlalchemy import update

    from app.core.security import utcnow
    from app.db.models import RefreshToken
    from app.db.session import get_engine

    api.login(api.make_user())
    with get_engine().begin() as conn:
        conn.execute(update(RefreshToken).values(expires_at=utcnow()))
    r = client.post(f"{API}/auth/refresh")
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_EXPIRED"


def test_logout_revokes_refresh(client, api):
    api.login(api.make_user())
    token = client.cookies.get("np_refresh")
    assert client.post(f"{API}/auth/logout").status_code == 204
    client.cookies.clear()
    client.cookies.set("np_refresh", token, path="/api/v1/auth")
    assert client.post(f"{API}/auth/refresh").status_code == 401
    # Cerrar sesión sin cookie también responde 204.
    client.cookies.clear()
    assert client.post(f"{API}/auth/logout").status_code == 204


def test_access_token_expired_and_invalid(client, api):
    from app.core.config import get_settings

    user = api.make_user()
    secret = get_settings().secret_key.get_secret_value()
    expired = jwt.encode({"sub": user["id"], "role": "patient", "exp": int(time.time()) - 5}, secret, algorithm="HS256")
    r = client.get(f"{API}/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_EXPIRED"
    forged = jwt.encode({"sub": user["id"], "role": "admin", "exp": int(time.time()) + 60}, "otra-clave" * 5, algorithm="HS256")
    r = client.get(f"{API}/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401 and r.json()["code"] == "UNAUTHENTICATED"
    assert client.get(f"{API}/me").json()["code"] == "UNAUTHENTICATED"


def test_cors_only_web_origin(client):
    allowed = client.options(
        f"{API}/auth/login", headers={"Origin": "https://web.test", "Access-Control-Request-Method": "POST"}
    )
    assert allowed.headers.get("access-control-allow-origin") == "https://web.test"
    assert allowed.headers.get("access-control-allow-credentials") == "true"
    other = client.options(
        f"{API}/auth/login", headers={"Origin": "https://otro.test", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in other.headers

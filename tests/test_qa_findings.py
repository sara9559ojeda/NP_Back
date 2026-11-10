"""Regresiones de los hallazgos de QA H-01 a H-04 (informe de seguridad del 09-11-2026).

- H-01: los logs no contienen datos personales ni hashes, tampoco en las trazas de excepción.
- H-02: un registro que pierde la carrera del correo responde 409 EMAIL_TAKEN, no 500.
- H-03: dos administradores que se desactivan a la vez no dejan el sistema sin administradores.
- H-04: las respuestas de la API llevan Cache-Control: no-store y X-Content-Type-Options: nosniff.
"""

import logging
import secrets
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from tests.conftest import API

# ───────────── H-01 ─────────────


def test_formatter_redacts_exception_tracebacks():
    from app.core.logging import RedactingFormatter

    email = f"traza{secrets.token_hex(3)}@example.com"
    argon = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA"
    try:
        raise ValueError(f"Key (email)=({email}) already exists. [parameters: {{'password_hash': '{argon}'}}]")
    except ValueError:
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "Exception in ASGI application", None, sys.exc_info())
    text = RedactingFormatter("%(message)s").format(record)
    assert "Traceback" in text, "la traza se conserva (control positivo)"
    assert email not in text and "$argon2id$" not in text and "m=65536" not in text


def test_engine_hides_sql_parameters(app):
    from app.db.session import get_engine

    assert get_engine().hide_parameters is True


# ───────────── H-02 ─────────────


def test_register_losing_the_email_race_is_409(client, api, monkeypatch):
    """Simula la carrera: la comprobación previa no ve el correo y el INSERT choca con uq_users_email."""
    from app.repositories import identity

    existing = api.make_user("patient")
    monkeypatch.setattr(identity, "email_exists", lambda *a, **k: False)
    r = client.post(f"{API}/auth/register", json={
        "fullName": "Carrera", "email": existing["email"], "password": secrets.token_urlsafe(12),
        "consent": {"accepted": True, "consentVersion": "2026-10-v1"}})
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_TAKEN", r.text


def test_admin_create_user_losing_the_email_race_is_409(client, api, admin, monkeypatch):
    from app.repositories import identity

    _, admin_headers = admin
    existing = api.make_user("professional")
    monkeypatch.setattr(identity, "email_exists", lambda *a, **k: False)
    r = client.post(f"{API}/admin/users", json={"fullName": "Carrera", "email": existing["email"],
                                                "role": "professional", "temporaryPassword": secrets.token_urlsafe(12)},
                    headers=admin_headers)
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_TAKEN", r.text


# ───────────── H-03 ─────────────


def test_mutual_concurrent_admin_deactivation_keeps_one_admin(app, api):
    from app.core.ratelimit import limiter
    from app.db.session import get_engine
    from sqlalchemy import text

    for _ in range(6):
        limiter.reset()
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE identity.users SET active = false WHERE role = 'admin'"))
        a, ha = api.user_with_headers("admin")
        b, hb = api.user_with_headers("admin")
        barrier = threading.Barrier(2)
        statuses = {}

        def act(name, target, headers):
            with TestClient(app, base_url="https://testserver") as c:
                barrier.wait()
                statuses[name] = c.patch(f"{API}/admin/users/{target['id']}", json={"active": False}, headers=headers).status_code

        threads = [threading.Thread(target=act, args=("a", b, ha)), threading.Thread(target=act, args=("b", a, hb))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with get_engine().begin() as conn:
            active = conn.execute(text("SELECT count(*) FROM identity.users WHERE role = 'admin' AND active")).scalar_one()
        assert active == 1, statuses
        assert sorted(statuses.values()) in ([200, 409], [200, 423]), statuses


# ───────────── H-04 ─────────────


@pytest.mark.parametrize("path", ["/me", "/me/sessions", "/health", "/no-existe"])
def test_security_headers_on_api_responses(client, api, path):
    _, headers = api.user_with_headers("patient")
    r = client.get(API + path, headers=headers)
    assert "no-store" in r.headers.get("cache-control", "")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("referrer-policy") == "no-referrer"

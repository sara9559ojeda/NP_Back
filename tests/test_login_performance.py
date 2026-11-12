"""Coste del hash de contraseñas, conexiones reutilizadas y tiempos del inicio de sesión."""

import re
import statistics
import time

import pytest
from argon2 import PasswordHasher, Type
from pydantic import SecretStr
from sqlalchemy import event

from tests.conftest import API

SERVER_TIMING = re.compile(r'^app;dur=(?P<app>[\d.]+), db;dur=(?P<db>[\d.]+);desc="(?P<queries>\d+) consultas"$')
# Un inicio de sesión correcto hace 5 consultas: límite de intentos (3), usuario (1) y token de refresco (1).
# El margen detecta un N+1 o una consulta repetida sin volver frágil la prueba.
LOGIN_QUERY_BUDGET = 8


def _timed(fn, runs: int = 3) -> float:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def _server_timing(response) -> dict[str, float]:
    match = SERVER_TIMING.match(response.headers["server-timing"])
    assert match, response.headers["server-timing"]
    return {name: float(value) for name, value in match.groupdict().items()}


# ── Argon2id ──


def test_password_profile_is_rfc9106_low_memory():
    from app.core.security import _hasher, hash_password

    assert (_hasher.type, _hasher.time_cost, _hasher.memory_cost, _hasher.parallelism) == (Type.ID, 3, 65536, 4)
    assert hash_password("clave-de-prueba").startswith("$argon2id$v=19$m=65536,t=3,p=4$")


def test_password_hash_cost_stays_within_budget():
    """Ni tan barato que pierda protección ni tan caro que el inicio de sesión se note lento."""
    from app.core.security import hash_password, verify_password

    stored = hash_password("clave-de-prueba")
    hash_s = _timed(lambda: hash_password("clave-de-prueba"))
    verify_s = _timed(lambda: verify_password(stored, "clave-de-prueba"))
    for label, seconds in (("hash", hash_s), ("verify", verify_s)):
        assert 0.005 < seconds < 0.5, f"{label}: {seconds * 1000:.0f} ms"


def test_unknown_email_costs_the_same_as_a_wrong_password():
    from app.core.security import hash_password, verify_password

    stored = hash_password("clave-de-prueba")
    wrong = _timed(lambda: verify_password(stored, "otra-clave"), runs=5)
    unknown = _timed(lambda: verify_password(None, "otra-clave"), runs=5)
    assert unknown == pytest.approx(wrong, rel=0.5)


def test_current_hashes_are_not_rehashed():
    """Los hashes ya guardados (argon2-cffi por defecto) tienen los mismos parámetros que el perfil fijado."""
    from app.core.security import password_needs_rehash

    assert password_needs_rehash(PasswordHasher().hash("clave-de-prueba")) is False


def test_login_upgrades_a_weaker_hash(client, api):
    from app.db.session import _session_factory
    from app.repositories import identity

    user = api.make_user("patient")
    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(user["password"])
    with _session_factory()() as db:
        identity.get_user_by_email(db, user["email"]).password_hash = weak
        db.commit()

    api.login(user)

    with _session_factory()() as db:
        upgraded = identity.get_user_by_email(db, user["email"]).password_hash
    assert upgraded.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    api.login(user)  # la contraseña sigue siendo la misma


# ── Pool de conexiones ──


@pytest.mark.parametrize(
    ("configured", "vercel", "port", "expected"),
    [
        (None, False, 5432, 5),  # EC2 y Docker Compose
        (None, True, 5432, 0),  # Vercel: instancias de corta vida
        (None, False, 6543, 0),  # Transaction pooler de Supabase
        (2, True, 6543, 2),  # el valor explícito manda
        (0, False, 5432, 0),
    ],
)
def test_pool_size_resolution(app, monkeypatch, configured, vercel, port, expected):
    from app.core.config import get_settings
    from app.db.session import pool_size

    settings = get_settings().model_copy(
        update={"db_pool_size": configured, "database_url": SecretStr(f"postgresql+psycopg://u:p@db.example:{port}/np")}
    )
    if vercel:
        monkeypatch.setenv("VERCEL", "1")
    else:
        monkeypatch.delenv("VERCEL", raising=False)
    assert pool_size(settings) == expected


def test_login_reuses_pooled_connections(client, api):
    from app.db.session import get_engine

    user = api.make_user("patient")
    api.login(user)  # calienta el pool
    opened = []
    listener = lambda *_: opened.append(1)  # noqa: E731
    event.listen(get_engine(), "connect", listener)
    try:
        for _ in range(3):
            api.login(user)
    finally:
        event.remove(get_engine(), "connect", listener)
    assert opened == [], "cada inicio de sesión abrió conexiones nuevas a PostgreSQL"


# ── Inicio de sesión ──


def test_login_reports_server_timing_within_budget(client, api):
    user = api.make_user("patient")
    body = {"email": user["email"], "password": user["password"]}
    client.post(f"{API}/auth/login", json=body)  # calienta el pool

    start = time.perf_counter()
    r = client.post(f"{API}/auth/login", json=body)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert r.status_code == 200
    measured = _server_timing(r)
    assert measured["queries"] <= LOGIN_QUERY_BUDGET
    assert 0 < measured["db"] <= measured["app"] <= elapsed_ms
    assert elapsed_ms < 1000, f"inicio de sesión: {elapsed_ms:.0f} ms"


def test_register_and_refresh_within_budget(client):
    from tests.test_auth import _register_body

    start = time.perf_counter()
    r = client.post(f"{API}/auth/register", json=_register_body())
    assert r.status_code == 201
    assert (time.perf_counter() - start) < 1.0

    login = client.post(f"{API}/auth/login", json={"email": "nueva@example.com", "password": "clave-segura-123"})
    assert login.status_code == 200
    start = time.perf_counter()
    refreshed = client.post(f"{API}/auth/refresh")
    assert refreshed.status_code == 200
    assert (time.perf_counter() - start) < 0.5
    # El refresco no calcula Argon2: pocas consultas y sin coste de hash.
    assert _server_timing(refreshed)["queries"] <= 6


def test_server_timing_has_no_personal_data(client, api):
    user = api.make_user("patient")
    r = client.post(f"{API}/auth/login", json={"email": user["email"], "password": user["password"]})
    header = r.headers["server-timing"]
    assert SERVER_TIMING.match(header)
    assert user["email"] not in header and "SELECT" not in header.upper()

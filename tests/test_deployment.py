"""Arranque, dependencia fijada, confianza del proxy y contador compartido."""
import importlib
import secrets
import tomllib
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import Request
from sqlalchemy.pool import NullPool

from tests.conftest import ROOT


def test_dependency_manifests_agree():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = (ROOT / "requirements.txt").read_text().splitlines()
    assert set(project["project"]["dependencies"]) == set(requirements)
    assert project["tool"]["vercel"]["entrypoint"] == "main:app"


def test_vercel_entrypoint_and_supabase_engine(app):
    from app.db.session import get_engine
    deployed = importlib.import_module("main").app
    from fastapi.testclient import TestClient
    with TestClient(deployed) as client:
        assert client.get('/api/v1/health').status_code == 200
    assert isinstance(get_engine().pool, NullPool)
    with get_engine().connect() as conn:
        assert conn.connection.driver_connection.prepare_threshold is None


def test_proxy_ip_requires_secret(app, monkeypatch):
    from app.api.deps import client_ip
    from app.core.config import get_settings
    from app.core.errors import ApiError
    secret = secrets.token_urlsafe(40)
    monkeypatch.setattr(get_settings(), "proxy_secret", __import__('pydantic').SecretStr(secret))
    monkeypatch.delenv("VERCEL", raising=False)
    def req(headers):
        return Request({"type": "http", "client": ("127.0.0.1", 1234), "headers": [(k.encode(), v.encode()) for k, v in headers.items()]})
    headers = {"x-np-client-ip": "192.0.2.10", "x-forwarded-for": "192.0.2.20"}
    assert client_ip(req(headers)) == "127.0.0.1"
    assert client_ip(req({**headers, "x-np-proxy-secret": "incorrecto"})) == "127.0.0.1"
    assert client_ip(req({**headers, "x-np-proxy-secret": secret})) == "192.0.2.10"
    with pytest.raises(ApiError):
        client_ip(req({"x-np-proxy-secret": secret, "x-np-client-ip": "no-ip"}))


def test_shared_limiter_is_atomic_between_instances(app):
    from app.core.ratelimit import PostgresWindowLimiter
    from app.core.errors import ApiError
    first, second = PostgresWindowLimiter(), PostgresWindowLimiter()
    key = first.key("test", secrets.token_hex(12))
    def attempt(i):
        try:
            (first if i % 2 else second).check_and_hit(key, 3, 60)
            return True
        except ApiError as exc:
            assert exc.status == 429
            return False
    with ThreadPoolExecutor(max_workers=6) as workers:
        assert sum(workers.map(attempt, range(8))) == 3
    assert second.count(key, 60) == 3

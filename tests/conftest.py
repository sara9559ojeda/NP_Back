"""Configuración de pytest.

- PostgreSQL efímero (``tests/ephemeral_pg.py``) migrado con Alembic, como en producción.
- Clave del servidor y credenciales de prueba generadas en tiempo de ejecución.
- Cada prueba empieza con las tablas vacías y los límites de frecuencia a cero.
"""

import copy
import json
import os
import secrets
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "api" / "examples"
API = "/api/v1"


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def database_url():
    from tests.ephemeral_pg import ephemeral_postgres

    with ephemeral_postgres() as url:
        yield url


@pytest.fixture(scope="session")
def app(database_url):
    os.environ["NP_DATABASE_URL"] = database_url
    os.environ["NP_SECRET_KEY"] = secrets.token_urlsafe(48)
    os.environ["NP_CORS_ORIGIN"] = "https://web.test"
    os.environ["NP_COOKIE_SECURE"] = "true"

    from app.core.config import get_settings
    from app.db import session as db_session

    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = database_url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    from app.main import create_app

    yield create_app()
    db_session.get_engine().dispose()


@pytest.fixture(autouse=True)
def _clean(request):
    if "app" not in request.fixturenames:
        yield
        return
    from app.core.ratelimit import limiter
    from app.db.session import get_engine

    with get_engine().begin() as conn:
        tables = conn.execute(
            text("SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname IN ('identity', 'clinical')")
        ).scalars()
        conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    limiter.reset()
    yield


@pytest.fixture
def client(app):
    with TestClient(app, base_url="https://testserver") as c:
        yield c


class Api:
    """Ayudantes de alto nivel sobre el cliente de pruebas."""

    def __init__(self, client: TestClient) -> None:
        self.c = client

    # ── cuentas ──
    def make_user(self, role: str = "patient", *, active: bool = True) -> dict:
        from app.db.session import _session_factory
        from app.repositories import identity
        from app.services.auth import create_account

        user = {
            "email": f"u{secrets.token_hex(5)}@example.com",
            "password": secrets.token_urlsafe(12),
            "fullName": f"Nombre {secrets.token_hex(3)} Apellido",
            "role": role,
        }
        db = _session_factory()()
        try:
            user_id = create_account(db, email=user["email"], password=user["password"], role=role, full_name=user["fullName"])
            if role == "patient":
                from app.core.security import utcnow

                identity.add_consent(db, user_id, "2026-10-v1", utcnow())
            if not active:
                identity.get_user(db, user_id).active = False
            db.commit()
        finally:
            db.close()
        user["id"] = str(user_id)
        return user

    def login(self, user: dict) -> dict:
        r = self.c.post(f"{API}/auth/login", json={"email": user["email"], "password": user["password"]})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['accessToken']}"}

    def user_with_headers(self, role: str) -> tuple[dict, dict]:
        user = self.make_user(role)
        return user, self.login(user)

    def assign(self, admin_headers: dict, professional: dict, patient: dict) -> str:
        r = self.c.post(
            f"{API}/admin/assignments",
            json={"professionalId": professional["id"], "patientId": patient["id"]},
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text
        return r.json()["assignmentId"]

    # ── visor ──
    def pairing_code(self, patient_headers: dict) -> str:
        r = self.c.post(f"{API}/pairing-codes", headers=patient_headers)
        assert r.status_code == 201, r.text
        return r.json()["code"]

    def pair(self, patient_headers: dict) -> dict:
        code = self.pairing_code(patient_headers)
        r = self.c.post(f"{API}/device/pair", json={"code": code, "deviceModel": "quest3", "appVersion": "0.2.0"})
        assert r.status_code == 201, r.text
        body = r.json()
        return {"deviceId": body["deviceId"], "headers": {"Authorization": f"Bearer {body['deviceToken']}"}}

    def send(self, device_headers: dict, envelope: dict):
        return self.c.post(f"{API}/device/records", json=envelope, headers=device_headers)


@pytest.fixture
def api(client) -> Api:
    return Api(client)


@pytest.fixture
def admin(api) -> tuple[dict, dict]:
    return api.user_with_headers("admin")


def envelope(kind: str, session_id: str | None = None, **payload_changes) -> dict:
    """Sobre del ejemplo del contrato con ``recordId`` nuevo y, si se pide, otra sesión."""
    env = copy.deepcopy(example(f"record_{kind}.request.json"))
    env["recordId"] = str(uuid.uuid4())
    if session_id:
        env["sessionId"] = session_id
    env["payload"].update(payload_changes)
    return env


def full_session(api: Api, device_headers: dict, *, test_session: bool = False, **level_changes) -> str:
    """Envía inicio, un nivel y cierre de una sesión nueva. Devuelve su ``sessionId``."""
    session_id = str(uuid.uuid4())
    for env in (
        envelope("session_start", session_id, testSession=test_session),
        envelope("level_record", session_id, **level_changes),
        envelope("session_end", session_id),
    ):
        r = api.send(device_headers, env)
        assert r.status_code == 201, r.text
    return session_id

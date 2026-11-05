"""BPMN gateway "¿Almacena datos? -> no -> mensaje de error" and the deployment DB link (v1.1.0)."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from tests.conftest import API, envelope


def _database_down(*_args, **_kwargs):
    raise OperationalError("SELECT 1", {}, Exception("connection lost"))


class _DownSession:
    """Stand-in for a SQLAlchemy session whose database is unreachable."""

    execute = staticmethod(_database_down)

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


def _open_session_with_level(api, device: dict) -> str:
    session_id = str(uuid.uuid4())
    api.send(device, envelope("session_start", session_id))
    api.send(device, envelope("level_record", session_id))
    return session_id


def test_storage_failure_returns_503_and_saves_nothing(client, api, care_team, monkeypatch):
    from app.repositories import clinical

    device = care_team["device"]
    session_id = _open_session_with_level(api, device)
    end_envelope = envelope("session_end", session_id)

    monkeypatch.setattr(clinical, "upsert_analysis", _database_down)
    r = api.send(device, end_envelope)
    assert r.status_code == 503
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.headers["retry-after"] == "5"
    assert r.json()["code"] == "STORAGE_UNAVAILABLE"
    assert "connection lost" not in r.text
    monkeypatch.undo()

    # Atomic: neither the session end nor the inbound ledger entry was stored.
    status = client.get(f"{API}/device/sessions/{session_id}", headers=device).json()
    assert status["status"] == "open" and status["feedback"]["status"] == "pending"

    # The headset resends the same envelope and this time everything is stored.
    retry = api.send(device, end_envelope)
    assert retry.status_code == 201 and retry.json()["feedback"]["status"] == "saved"


def test_analysis_failure_rolls_back_the_metrics(app, client, api, care_team, monkeypatch):
    from app.services import analysis

    def broken_analyzer(_method: str):
        raise RuntimeError("analyzer failure")

    device = care_team["device"]
    session_id = _open_session_with_level(api, device)
    monkeypatch.setattr(analysis, "get_analyzer", broken_analyzer)
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as raw:
        r = raw.post(f"{API}/device/records", json=envelope("session_end", session_id), headers=device)
    assert r.status_code == 500 and r.json()["code"] == "SERVER_ERROR"
    monkeypatch.undo()
    assert client.get(f"{API}/device/sessions/{session_id}", headers=device).json()["status"] == "open"


def test_health_ready_checks_the_database(app, client):
    from app.db.session import get_db

    r = client.get(f"{API}/health/ready")
    assert r.status_code == 200 and r.json()["database"] == "ok"

    app.dependency_overrides[get_db] = _DownSession
    try:
        down = client.get(f"{API}/health/ready")
    finally:
        app.dependency_overrides.pop(get_db)
    assert down.status_code == 503 and down.json()["code"] == "STORAGE_UNAVAILABLE"
    assert client.get(f"{API}/health").status_code == 200  # /health never touches the database

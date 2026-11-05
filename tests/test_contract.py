"""El OpenAPI publicado coincide con el código y cubre todas las rutas del contrato."""

import json
import re
import uuid

from tests.conftest import API, ROOT, envelope, example

CONTRACT = ROOT / "docs" / "api" / "CONTRATO_API_v1.md"
OPENAPI = ROOT / "docs" / "api" / "openapi.json"
ROUTE_RE = re.compile(r"`(GET|POST|PUT|PATCH|DELETE) (/[^`?\s]+)")


def _contract_routes() -> set[tuple[str, str]]:
    text = CONTRACT.read_text(encoding="utf-8")
    routes = {(m.group(1).lower(), m.group(2)) for m in ROUTE_RE.finditer(text)}
    # «GET /me/sessions y GET /me/sessions/{sessionId}» y rutas antiguas de Unity (sección 10) se excluyen.
    return {(method, path) for method, path in routes if not path.startswith("/api/")}


def test_published_openapi_is_up_to_date(app):
    generated = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert OPENAPI.read_text(encoding="utf-8") == generated, "ejecuta python scripts/export_openapi.py"


def test_every_contract_route_exists(app):
    paths = app.openapi()["paths"]
    implemented = {(method, path.removeprefix("/api/v1")) for path, ops in paths.items() for method in ops}
    expected = _contract_routes()
    assert len(expected) >= 30
    assert expected <= implemented, sorted(expected - implemented)


def test_errors_documented_as_problem_json(app):
    schema = app.openapi()
    assert "Problem" in schema["components"]["schemas"]
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    record_body = schema["paths"]["/api/v1/device/records"]["post"]["requestBody"]
    assert record_body["content"]["application/json"]["schema"]["$ref"].endswith("/RecordEnvelope")
    for name in ("SessionStartPayload", "LevelRecordPayload", "SessionEndPayload"):
        assert name in schema["components"]["schemas"]


def _shape(value):
    """Keys of a JSON value, recursively, ignoring the concrete values."""
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return None


def test_v1_1_examples_match_real_responses(client, api, care_team):
    pid, device = care_team["patient"]["id"], care_team["device"]
    session_id = str(uuid.uuid4())
    start = api.send(device, envelope("session_start", session_id)).json()
    api.send(device, envelope("level_record", session_id))
    end = api.send(device, envelope("session_end", session_id)).json()
    client.post(f"{API}/patients/{pid}/notes", json={"text": "n", "sessionId": session_id}, headers=care_team["pro_headers"])
    grade = client.put(f"{API}/device/phobia-grade", json=example("phobia_grade.request.json"), headers=device).json()
    real = {
        "records_session_start.response.201.json": start,
        "records_session_end.response.201.json": end,
        "phobia_grade.response.200.json": grade,
        "device_session.response.200.json": client.get(f"{API}/device/sessions/{session_id}", headers=device).json(),
        "device_context.v1_1.response.200.json": client.get(f"{API}/device/context", headers=device).json(),
        "me_therapy.response.200.json": client.get(f"{API}/me/therapy", headers=care_team["patient_headers"]).json(),
        "feedback.response.200.json": client.get(f"{API}/patients/{pid}/feedback", headers=care_team["pro_headers"]).json(),
        "health_ready.response.200.json": client.get(f"{API}/health/ready").json(),
    }
    for name, body in real.items():
        assert _shape(body) == _shape(example(name)), name

"""El OpenAPI publicado coincide con el código y cubre todas las rutas del contrato."""

import json
import re

from tests.conftest import ROOT

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

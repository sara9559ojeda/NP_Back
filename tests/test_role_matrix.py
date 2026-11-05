"""Matriz de acceso completa (contrato, sección 2.3).

Columnas: anónimo, paciente, profesional asignado, profesional no asignado, administrador y
token del visor. Cada celda es el código HTTP esperado.
"""

import uuid

import pytest

from tests.conftest import API, envelope, full_session

ANON, PATIENT, PRO, OTHER_PRO, ADMIN, DEVICE = "anonymous", "patient", "professional", "other_professional", "admin", "device"


@pytest.fixture
def world(api, admin):
    admin_user, admin_headers = admin
    patient, patient_headers = api.user_with_headers("patient")
    professional, professional_headers = api.user_with_headers("professional")
    _, other_headers = api.user_with_headers("professional")
    api.assign(admin_headers, professional, patient)
    device = api.pair(patient_headers)
    session_id = full_session(api, device["headers"])
    return {
        "patient": patient,
        "session_id": session_id,
        "device_id": device["deviceId"],
        "headers": {
            ANON: {},
            PATIENT: patient_headers,
            PRO: professional_headers,
            OTHER_PRO: other_headers,
            ADMIN: admin_headers,
            DEVICE: device["headers"],
        },
    }


def _matrix(w):
    pid, sid = w["patient"]["id"], w["session_id"]
    #      método, ruta, cuerpo, {actor: estado}
    return [
        # /me (datos propios)
        ("get", "/me", None, {ANON: 401, PATIENT: 200, PRO: 200, ADMIN: 200, DEVICE: 401}),
        # Códigos de emparejamiento
        ("post", "/pairing-codes", None, {ANON: 401, PATIENT: 201, PRO: 403, ADMIN: 403}),
        ("post", f"/patients/{pid}/pairing-codes", None, {ANON: 401, PATIENT: 403, PRO: 201, OTHER_PRO: 404, ADMIN: 403}),
        # /device/* solo con el token del visor
        ("get", "/device/context", None, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 403, DEVICE: 200}),
        ("post", "/device/records", "record", {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 403, DEVICE: 201}),
        # Progreso y sesiones propias
        ("get", "/me/progress", None, {ANON: 401, PATIENT: 200, PRO: 403, ADMIN: 403}),
        ("get", "/me/sessions", None, {ANON: 401, PATIENT: 200, PRO: 403, ADMIN: 403}),
        ("get", f"/me/sessions/{sid}", None, {ANON: 401, PATIENT: 200, PRO: 403, ADMIN: 403}),
        ("get", "/me/devices", None, {ANON: 401, PATIENT: 200, PRO: 403, ADMIN: 403}),
        # Seguimiento de un paciente
        ("get", "/patients", None, {ANON: 401, PATIENT: 403, PRO: 200, OTHER_PRO: 200, ADMIN: 403}),
        ("get", f"/patients/{pid}/progress", None, {ANON: 401, PATIENT: 403, PRO: 200, OTHER_PRO: 404, ADMIN: 403}),
        ("get", f"/patients/{pid}/sessions", None, {ANON: 401, PATIENT: 403, PRO: 200, OTHER_PRO: 404, ADMIN: 403}),
        ("get", f"/patients/{pid}/sessions/{sid}", None, {ANON: 401, PATIENT: 403, PRO: 200, OTHER_PRO: 404, ADMIN: 403}),
        # Notas
        ("get", f"/patients/{pid}/notes", None, {ANON: 401, PATIENT: 403, PRO: 200, OTHER_PRO: 404, ADMIN: 403}),
        ("post", f"/patients/{pid}/notes", {"text": "n"}, {ANON: 401, PATIENT: 403, PRO: 201, OTHER_PRO: 404, ADMIN: 403}),
        # Plan del paciente
        ("put", f"/patients/{pid}/plan", {"allowedStartLevel": 1}, {ANON: 401, PATIENT: 403, PRO: 200, OTHER_PRO: 404, ADMIN: 403}),
        # Usuarios, roles, asignaciones
        ("get", "/admin/users", None, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 200}),
        ("post", "/admin/users", "new_user", {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 201}),
        ("patch", f"/admin/users/{pid}", {"active": True}, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 200}),
        ("get", "/admin/assignments", None, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 200}),
        ("post", "/admin/assignments", {"professionalId": str(uuid.uuid4()), "patientId": pid}, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 422}),
        ("delete", f"/admin/assignments/{uuid.uuid4()}", None, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 404}),
        # Exportación anónima
        ("get", "/admin/exports/analysis-dataset", None, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 200}),
        # ── v1.1.0 (UML/BPMN diagrams) ──
        ("get", "/public/product-info", None, {ANON: 200, PATIENT: 200, PRO: 200, ADMIN: 200}),
        ("get", "/me/therapy", None, {ANON: 401, PATIENT: 200, PRO: 403, ADMIN: 403, DEVICE: 401}),
        ("put", "/me/phobia-grade", {"phobiaGrade": 3}, {ANON: 401, PATIENT: 200, PRO: 403, ADMIN: 403}),
        ("put", "/device/phobia-grade", {"phobiaGrade": 3}, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 403, DEVICE: 200}),
        ("get", f"/device/sessions/{sid}", None, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 403, DEVICE: 200}),
        ("post", "/device/unpair", None, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 403}),
        ("get", f"/patients/{pid}/feedback", None, {ANON: 401, PATIENT: 403, PRO: 200, OTHER_PRO: 404, ADMIN: 403}),
        ("get", f"/admin/users/{pid}", None, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 200}),
        ("put", f"/admin/users/{pid}/password", {"temporaryPassword": "temporal-123"}, {ANON: 401, PATIENT: 403, PRO: 403, ADMIN: 204}),
    ]


def _body(kind):
    if kind == "record":
        return envelope("level_record")
    if kind == "new_user":
        return {
            "fullName": "Persona Nueva",
            "email": f"n{uuid.uuid4().hex[:8]}@example.com",
            "role": "patient",
            "temporaryPassword": "temporal-123",
        }
    return kind


def test_role_matrix(client, world):
    failures = []
    for method, path, body, expected in _matrix(world):
        for actor, status in expected.items():
            r = client.request(method, f"{API}{path}", json=_body(body), headers=world["headers"][actor])
            if r.status_code != status:
                failures.append(f"{method.upper()} {path} como {actor}: {r.status_code}, esperado {status}")
            elif status >= 400:
                assert r.headers["content-type"].startswith("application/problem+json")
    assert not failures, "\n".join(failures)


def test_admin_never_sees_clinical_data(client, world):
    admin_headers = world["headers"][ADMIN]
    responses = [
        client.get(f"{API}/admin/users", headers=admin_headers),
        client.get(f"{API}/admin/assignments", headers=admin_headers),
        client.get(f"{API}/admin/exports/analysis-dataset", headers=admin_headers),
    ]
    for r in responses:
        assert world["session_id"] not in r.text
        assert "toleranceIndex" not in r.text or "subjectKey" in r.text  # solo en la exportación anónima
    # La exportación no lleva identidad del paciente.
    export = responses[2].text
    assert world["patient"]["id"] not in export and world["patient"]["fullName"] not in export

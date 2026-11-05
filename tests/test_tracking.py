"""Seguimiento: progreso, sesiones, plan y notas (contrato, sección 5)."""

import uuid

import pytest

from tests.conftest import API, example, full_session


@pytest.fixture
def care(api, admin):
    """Paciente con visor y dos sesiones, asignado a un profesional."""
    _, admin_headers = admin
    patient, patient_headers = api.user_with_headers("patient")
    professional, professional_headers = api.user_with_headers("professional")
    api.assign(admin_headers, professional, patient)
    device = api.pair(patient_headers)
    sessions = [full_session(api, device["headers"]) for _ in range(2)]
    return {
        "patient": patient,
        "patient_headers": patient_headers,
        "professional": professional,
        "headers": professional_headers,
        "sessions": sessions,
        "admin_headers": admin_headers,
    }


def test_patient_progress_and_sessions(client, care):
    h = care["patient_headers"]
    progress = client.get(f"{API}/me/progress", headers=h).json()
    assert progress["sessionsCount"] == 2 and progress["levelReached"] == 2
    item = progress["lastSessions"][0]
    assert set(item) == set(example("progress.response.200.json")["lastSessions"][0])
    assert item["recommendation"] in ("advance", "repeat", "step_back")

    page = client.get(f"{API}/me/sessions", params={"limit": 1}, headers=h).json()
    assert len(page["items"]) == 1 and page["nextCursor"]
    second = client.get(f"{API}/me/sessions", params={"limit": 1, "cursor": page["nextCursor"]}, headers=h).json()
    assert {page["items"][0]["sessionId"], second["items"][0]["sessionId"]} == set(care["sessions"])
    assert second["nextCursor"] is None

    detail = client.get(f"{API}/me/sessions/{care['sessions'][0]}", headers=h).json()
    assert "notes" not in detail
    assert detail["levels"][0]["suds"][0] == {"phase": "before", "value": 60, "at": 0.0}
    analysis = detail["analysis"]
    assert analysis["method"] == "rules-baseline" and analysis["methodVersion"] == "0.1.0"
    assert 0 <= analysis["toleranceIndex"] <= 1
    assert {b["feature"] for b in analysis["basis"]} >= {"sudsDrop", "avoidanceCount"}
    assert client.get(f"{API}/me/sessions/{uuid.uuid4()}", headers=h).status_code == 404


def test_professional_views_assigned_patient(client, care):
    h, pid = care["headers"], care["patient"]["id"]
    patients = client.get(f"{API}/patients", headers=h).json()["items"]
    assert patients == [
        {
            "patientId": pid,
            "fullName": care["patient"]["fullName"],
            "lastSessionAt": "2026-10-30T21:00:00Z",
            "levelReached": 2,
            "lastRecommendation": patients[0]["lastRecommendation"],
            "phobiaGrade": 3,
        }
    ]
    assert patients[0]["lastRecommendation"] in ("advance", "repeat", "step_back")
    assert client.get(f"{API}/patients/{pid}/progress", headers=h).json()["sessionsCount"] == 2
    assert len(client.get(f"{API}/patients/{pid}/sessions", headers=h).json()["items"]) == 2
    detail = client.get(f"{API}/patients/{pid}/sessions/{care['sessions'][0]}", headers=h).json()
    assert detail["notes"] == [] and detail["analysis"] is not None


def test_plan(client, care):
    h, pid = care["headers"], care["patient"]["id"]
    r = client.put(f"{API}/patients/{pid}/plan", json=example("plan.request.json"), headers=h)
    assert r.status_code == 200 and r.json()["allowedStartLevel"] == 2 and r.json()["patientId"] == pid
    for bad in (0, 6, "3", 2.5):
        assert client.put(f"{API}/patients/{pid}/plan", json={"allowedStartLevel": bad}, headers=h).status_code == 422


def test_notes(client, api, care):
    h, pid = care["headers"], care["patient"]["id"]
    session_id = care["sessions"][0]
    r = client.post(f"{API}/patients/{pid}/notes", json={"text": "Primera nota", "sessionId": session_id}, headers=h)
    assert r.status_code == 201 and set(r.json()) >= {"noteId", "createdAt"}
    assert r.json()["text"] == "Primera nota" and r.json()["sessionId"] == session_id
    note_id = r.json()["noteId"]
    client.post(f"{API}/patients/{pid}/notes", json={"text": "Segunda nota"}, headers=h)

    items = client.get(f"{API}/patients/{pid}/notes", headers=h).json()["items"]
    assert [n["text"] for n in items] == ["Segunda nota", "Primera nota"]
    assert items[1]["authorName"] == care["professional"]["fullName"]
    detail = client.get(f"{API}/patients/{pid}/sessions/{session_id}", headers=h).json()
    assert [n["noteId"] for n in detail["notes"]] == [note_id]

    r = client.patch(f"{API}/patients/{pid}/notes/{note_id}", json={"text": "Editada"}, headers=h)
    assert r.status_code == 200 and r.json()["text"] == "Editada" and r.json()["editedAt"]

    # Otro profesional asignado al mismo paciente puede leer, pero no editar.
    other, other_headers = api.user_with_headers("professional")
    api.assign(care["admin_headers"], other, care["patient"])
    assert len(client.get(f"{API}/patients/{pid}/notes", headers=other_headers).json()["items"]) == 2
    r = client.patch(f"{API}/patients/{pid}/notes/{note_id}", json={"text": "No"}, headers=other_headers)
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"

    assert client.post(f"{API}/patients/{pid}/notes", json={"text": "  "}, headers=h).status_code == 422
    r = client.post(f"{API}/patients/{pid}/notes", json={"text": "x", "sessionId": str(uuid.uuid4())}, headers=h)
    assert r.status_code == 422 and r.json()["errors"] == [{"field": "sessionId", "code": "not_found"}]
    assert client.patch(f"{API}/patients/{pid}/notes/{uuid.uuid4()}", json={"text": "x"}, headers=h).status_code == 404


def test_unassigned_patient_is_404_for_every_route(client, api, care):
    _, stranger = api.user_with_headers("professional")
    pid, sid = care["patient"]["id"], care["sessions"][0]
    note = client.post(f"{API}/patients/{pid}/notes", json={"text": "n"}, headers=care["headers"]).json()["noteId"]
    calls = [
        ("get", f"/patients/{pid}/progress", None),
        ("get", f"/patients/{pid}/sessions", None),
        ("get", f"/patients/{pid}/sessions/{sid}", None),
        ("put", f"/patients/{pid}/plan", {"allowedStartLevel": 2}),
        ("get", f"/patients/{pid}/notes", None),
        ("post", f"/patients/{pid}/notes", {"text": "x"}),
        ("patch", f"/patients/{pid}/notes/{note}", {"text": "x"}),
        ("post", f"/patients/{pid}/pairing-codes", None),
    ]
    for method, path, body in calls:
        r = client.request(method, f"{API}{path}", json=body, headers=stranger)
        assert r.status_code == 404, path
        assert r.json()["code"] == "NOT_FOUND"
    # Lo mismo que si el paciente no existiera.
    assert client.get(f"{API}/patients/{uuid.uuid4()}/progress", headers=stranger).json() == client.get(
        f"{API}/patients/{pid}/progress", headers=stranger
    ).json()


def test_unassignment_removes_access(client, care):
    assignment = client.get(f"{API}/admin/assignments", headers=care["admin_headers"]).json()["items"][0]
    client.delete(f"{API}/admin/assignments/{assignment['assignmentId']}", headers=care["admin_headers"])
    assert client.get(f"{API}/patients/{care['patient']['id']}/progress", headers=care["headers"]).status_code == 404

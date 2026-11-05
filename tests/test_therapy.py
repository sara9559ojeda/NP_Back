"""Therapy lifecycle from the UML/BPMN diagrams (contract v1.1.0).

Covers the BPMN step "Ajustar grado de fobia", the context-diagram flow "Iniciar y finalizar
terapia" and the "therapy" sequence diagram up to "Retroalimentación guardada".
"""

import uuid

import pytest

from tests.conftest import API, envelope, full_session

EMPTY_FEEDBACK = {
    "status": "not_applicable",
    "recommendation": None,
    "toleranceIndex": None,
    "method": None,
    "clinicalStatus": None,
    "createdAt": None,
}


# ───────────── phobia grade ─────────────


def test_phobia_grade_set_on_web_reaches_device_context(client, care_team):
    r = client.put(f"{API}/me/phobia-grade", json={"phobiaGrade": 4}, headers=care_team["patient_headers"])
    assert r.status_code == 200
    assert r.json()["phobiaGrade"] == 4 and r.json()["updatedAt"].endswith("Z")

    context = client.get(f"{API}/device/context", headers=care_team["device"]).json()
    assert context["phobiaGrade"] == 4
    assert context["phobiaGradeUpdatedAt"] == r.json()["updatedAt"]

    patients = client.get(f"{API}/patients", headers=care_team["pro_headers"]).json()["items"]
    assert patients[0]["phobiaGrade"] == 4


def test_phobia_grade_set_on_device_reaches_therapy_state(client, care_team):
    r = client.put(f"{API}/device/phobia-grade", json={"phobiaGrade": 2}, headers=care_team["device"])
    assert r.status_code == 200 and r.json()["phobiaGrade"] == 2
    state = client.get(f"{API}/me/therapy", headers=care_team["patient_headers"]).json()
    assert state["phobiaGrade"] == 2


@pytest.mark.parametrize("bad", [0, 6, "3", 2.5, None])
def test_phobia_grade_rejects_invalid_values(client, care_team, bad):
    for path, headers in (("/me/phobia-grade", care_team["patient_headers"]), ("/device/phobia-grade", care_team["device"])):
        r = client.put(f"{API}{path}", json={"phobiaGrade": bad}, headers=headers)
        assert r.status_code == 422
        assert r.json()["errors"][0]["field"] == "phobiaGrade"


def test_session_start_updates_phobia_grade_only_when_newer(client, api, care_team):
    device = care_team["device"]
    # No prior adjustment: the session_start (2026-10-30) becomes the latest self-report.
    assert api.send(device, envelope("session_start", str(uuid.uuid4()), phobiaGrade=5)).status_code == 201
    context = client.get(f"{API}/device/context", headers=device).json()
    assert context["phobiaGrade"] == 5 and context["phobiaGradeUpdatedAt"] == "2026-10-30T21:00:00Z"

    # A later adjustment wins over an older session_start that arrives late.
    client.put(f"{API}/me/phobia-grade", json={"phobiaGrade": 2}, headers=care_team["patient_headers"])
    assert api.send(device, envelope("session_start", str(uuid.uuid4()), phobiaGrade=4)).status_code == 201
    assert client.get(f"{API}/device/context", headers=device).json()["phobiaGrade"] == 2


# ───────────── therapy state ─────────────


def test_therapy_state_follows_start_and_end(client, api, care_team):
    headers, device = care_team["patient_headers"], care_team["device"]
    assert client.get(f"{API}/me/therapy", headers=headers).json() == {
        "phobiaGrade": None,
        "phobiaGradeUpdatedAt": None,
        "allowedStartLevel": 1,
        "pairedDevices": 1,
        "openSession": None,
        "lastSession": None,
        "lastFeedback": None,
    }

    session_id = str(uuid.uuid4())
    api.send(device, envelope("session_start", session_id))
    started = client.get(f"{API}/me/therapy", headers=headers).json()
    assert started["openSession"] == {"sessionId": session_id, "startedAt": "2026-10-30T21:00:00Z"}
    assert started["phobiaGrade"] == 3

    api.send(device, envelope("level_record", session_id))
    api.send(device, envelope("session_end", session_id))
    finished = client.get(f"{API}/me/therapy", headers=headers).json()
    assert finished["openSession"] is None
    assert finished["lastSession"]["sessionId"] == session_id
    assert finished["lastFeedback"]["sessionId"] == session_id
    assert finished["lastFeedback"]["analysis"]["method"] == "rules-baseline"
    assert "notesCount" not in finished["lastFeedback"]  # patients never see notes


# ───────────── record responses ─────────────


def test_record_response_reports_session_and_saved_feedback(api, care_team):
    device, session_id = care_team["device"], str(uuid.uuid4())
    start = api.send(device, envelope("session_start", session_id)).json()
    assert start["status"] == "stored"
    assert start["session"] == {"sessionId": session_id, "status": "open"}
    assert start["feedback"]["status"] == "pending"

    api.send(device, envelope("level_record", session_id))
    end_envelope = envelope("session_end", session_id)
    end = api.send(device, end_envelope).json()
    assert end["session"]["status"] == "closed"
    assert end["feedback"]["status"] == "saved"
    assert end["feedback"]["recommendation"] in ("advance", "repeat", "step_back")
    assert 0 <= end["feedback"]["toleranceIndex"] <= 1
    assert end["feedback"]["clinicalStatus"] == "pendiente_de_validar"

    duplicate = api.send(device, end_envelope)
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate" and duplicate.json()["feedback"]["status"] == "saved"


def test_record_response_for_out_of_order_and_test_sessions(client, api, care_team):
    device = care_team["device"]
    orphan = api.send(device, envelope("level_record", str(uuid.uuid4()))).json()
    assert orphan["session"]["status"] == "pending_start" and orphan["feedback"]["status"] == "pending"

    test_session = full_session(api, device, test_session=True)
    status = client.get(f"{API}/device/sessions/{test_session}", headers=device).json()
    assert status["feedback"] == EMPTY_FEEDBACK


# ───────────── device session status ─────────────


def test_device_session_status(client, api, care_team):
    device = care_team["device"]
    session_id = full_session(api, device)
    r = client.get(f"{API}/device/sessions/{session_id}", headers=device)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "closed" and body["levelsStored"] == 1 and body["phobiaGrade"] == 3
    assert body["feedback"]["status"] == "saved"
    assert client.get(f"{API}/device/sessions/{uuid.uuid4()}", headers=device).status_code == 404


def test_device_session_of_another_patient_is_not_found(client, api, care_team):
    session_id = full_session(api, care_team["device"])
    _, other_headers = api.user_with_headers("patient")
    other_device = api.pair(other_headers)["headers"]
    assert client.get(f"{API}/device/sessions/{session_id}", headers=other_device).status_code == 404


# ───────────── headset logout ─────────────


def test_device_unpair_revokes_its_own_token(client, care_team):
    assert client.post(f"{API}/device/unpair", headers=care_team["device"]).status_code == 204
    after = client.get(f"{API}/device/context", headers=care_team["device"])
    assert after.status_code == 401 and after.json()["code"] == "DEVICE_REVOKED"
    devices = client.get(f"{API}/me/devices", headers=care_team["patient_headers"]).json()["items"]
    assert devices[0]["revokedAt"] is not None

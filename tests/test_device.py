"""Visor: emparejamiento, contexto y bandeja de salida (contrato, sección 6)."""

import json
import uuid

from sqlalchemy import update

from tests.conftest import API, envelope, example, full_session

PAIR = f"{API}/device/pair"


def _pair_body(code: str) -> dict:
    return {**example("device_pair.request.json"), "code": code}


# ───────────── emparejamiento ─────────────


def test_pairing_code_format(client, api):
    _, headers = api.user_with_headers("patient")
    r = client.post(f"{API}/pairing-codes", headers=headers)
    assert r.status_code == 201
    code = r.json()["code"]
    assert len(code) == 7 and code[3] == "-"
    assert not set(code.replace("-", "")) & set("0O1I")
    assert r.json()["expiresAt"].endswith("Z")


def test_pair_single_use(client, api):
    _, headers = api.user_with_headers("patient")
    code = api.pairing_code(headers)
    r = client.post(PAIR, json=_pair_body(code.replace("-", "").lower()))
    assert r.status_code == 201
    assert set(r.json()) == {"deviceId", "deviceToken"}
    again = client.post(PAIR, json=_pair_body(code))
    assert again.status_code == 410 and again.json()["code"] == "PAIRING_CODE_EXPIRED"


def test_pair_expired(client, api):
    from app.core.security import utcnow
    from app.db.models import PairingCode
    from app.db.session import get_engine

    _, headers = api.user_with_headers("patient")
    code = api.pairing_code(headers)
    with get_engine().begin() as conn:
        conn.execute(update(PairingCode).values(expires_at=utcnow()))
    r = client.post(PAIR, json=_pair_body(code))
    assert r.status_code == 410 and r.json()["code"] == "PAIRING_CODE_EXPIRED"


def test_new_code_invalidates_previous(client, api):
    _, headers = api.user_with_headers("patient")
    first = api.pairing_code(headers)
    second = api.pairing_code(headers)
    assert client.post(PAIR, json=_pair_body(first)).status_code == 404
    assert client.post(PAIR, json=_pair_body(second)).status_code == 201


def test_pair_invalid_code_and_rate_limit_after_five_failures(client, api):
    _, headers = api.user_with_headers("patient")
    good = api.pairing_code(headers)
    for _ in range(5):
        r = client.post(PAIR, json=_pair_body("ZZZ-ZZZ"))
        assert r.status_code == 404 and r.json()["code"] == "PAIRING_CODE_INVALID"
    blocked = client.post(PAIR, json=_pair_body(good))
    assert blocked.status_code == 429 and blocked.json()["code"] == "RATE_LIMITED"


def test_pair_validation(client):
    r = client.post(PAIR, json={"code": "K7Q-4MZ", "deviceModel": "quest 3; DROP", "appVersion": "0.2.0"})
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "deviceModel"


def test_professional_creates_code_for_assigned_patient_only(client, api, admin):
    _, admin_headers = admin
    patient = api.make_user("patient")
    other = api.make_user("patient")
    professional, headers = api.user_with_headers("professional")
    api.assign(admin_headers, professional, patient)
    r = client.post(f"{API}/patients/{patient['id']}/pairing-codes", headers=headers)
    assert r.status_code == 201
    assert client.post(PAIR, json=_pair_body(r.json()["code"])).status_code == 201
    assert client.post(f"{API}/patients/{other['id']}/pairing-codes", headers=headers).status_code == 404


def test_list_and_revoke_devices(client, api):
    _, headers = api.user_with_headers("patient")
    device = api.pair(headers)
    items = client.get(f"{API}/me/devices", headers=headers).json()["items"]
    assert [d["deviceId"] for d in items] == [device["deviceId"]]
    assert items[0]["deviceModel"] == "quest3" and items[0]["revokedAt"] is None

    assert client.delete(f"{API}/me/devices/{device['deviceId']}", headers=headers).status_code == 204
    assert client.delete(f"{API}/me/devices/{device['deviceId']}", headers=headers).status_code == 204
    r = api.send(device["headers"], envelope("session_start"))
    assert r.status_code == 401 and r.json()["code"] == "DEVICE_REVOKED"
    assert client.get(f"{API}/device/context", headers=device["headers"]).json()["code"] == "DEVICE_REVOKED"

    _, other_headers = api.user_with_headers("patient")
    assert client.delete(f"{API}/me/devices/{device['deviceId']}", headers=other_headers).status_code == 404


def test_device_token_required(client, api):
    assert client.get(f"{API}/device/context").json()["code"] == "UNAUTHENTICATED"
    r = client.get(f"{API}/device/context", headers={"Authorization": "Bearer npd_inventado1234567890"})
    assert r.status_code == 401 and r.json()["code"] == "UNAUTHENTICATED"


# ───────────── contexto ─────────────


def test_context_without_sessions(client, api):
    _, headers = api.user_with_headers("patient")
    device = api.pair(headers)
    r = client.get(f"{API}/device/context", headers=device["headers"])
    assert r.status_code == 200
    assert r.json() == {"allowedStartLevel": 1, "lastSession": None, "recommendation": None}


def test_context_after_session_has_no_personal_data(client, api, admin):
    _, admin_headers = admin
    patient, headers = api.user_with_headers("patient")
    professional, professional_headers = api.user_with_headers("professional")
    api.assign(admin_headers, professional, patient)
    client.put(f"{API}/patients/{patient['id']}/plan", json={"allowedStartLevel": 2}, headers=professional_headers)
    device = api.pair(headers)
    session_id = full_session(api, device["headers"])
    full_session(api, device["headers"], test_session=True)  # no cuenta para el contexto

    r = client.get(f"{API}/device/context", headers=device["headers"])
    body = r.json()
    assert body["allowedStartLevel"] == 2
    assert body["lastSession"] == {"endedAt": "2026-10-30T21:12:00Z", "levelReached": 2, "totalDurationSeconds": 720.0}
    assert body["recommendation"]["fromSessionId"] == session_id
    assert body["recommendation"]["method"] == "rules-baseline"
    assert body["recommendation"]["clinicalStatus"] == "pendiente_de_validar"
    for value in (patient["email"], patient["fullName"]):
        assert value not in r.text


# ───────────── registros ─────────────


def _device(api) -> dict:
    _, headers = api.user_with_headers("patient")
    return api.pair(headers)["headers"]


def test_records_examples_from_contract_are_stored(api):
    device = _device(api)
    for kind in ("session_start", "level_record", "session_end"):
        r = api.send(device, example(f"record_{kind}.request.json"))
        assert r.status_code == 201, r.text
        assert r.json() == example("records.response.201.json")


def test_records_idempotent_and_conflict(api):
    device = _device(api)
    env = envelope("session_start")
    assert api.send(device, env).status_code == 201
    dup = api.send(device, env)
    assert dup.status_code == 200 and dup.json() == example("records.response.200.json")

    changed = json.loads(json.dumps(env))
    changed["payload"]["phobiaGrade"] = 4
    conflict = api.send(device, changed)
    assert conflict.status_code == 409 and conflict.json()["code"] == "RECORD_CONFLICT"

    # Otro paciente que reenvía el mismo recordId tampoco ve un «duplicate».
    assert api.send(_device(api), env).status_code == 409


def test_second_start_for_same_session_is_conflict(api):
    device = _device(api)
    session_id = str(uuid.uuid4())
    assert api.send(device, envelope("session_start", session_id)).status_code == 201
    assert api.send(device, envelope("session_start", session_id)).status_code == 409


def test_session_of_other_patient_is_conflict(api):
    session_id = str(uuid.uuid4())
    assert api.send(_device(api), envelope("session_start", session_id)).status_code == 201
    assert api.send(_device(api), envelope("level_record", session_id)).status_code == 409


def test_out_of_order_records_are_linked(client, api):
    _, headers = api.user_with_headers("patient")
    device = api.pair(headers)["headers"]
    session_id = str(uuid.uuid4())

    assert api.send(device, envelope("session_end", session_id)).status_code == 201
    pending = client.get(f"{API}/me/sessions/{session_id}", headers=headers).json()
    assert pending["status"] == "pending_start" and pending["analysis"] is None

    assert api.send(device, envelope("level_record", session_id)).status_code == 201
    assert client.get(f"{API}/me/sessions/{session_id}", headers=headers).json()["analysis"] is None

    assert api.send(device, envelope("session_start", session_id)).status_code == 201
    detail = client.get(f"{API}/me/sessions/{session_id}", headers=headers).json()
    assert detail["status"] == "closed" and detail["phobiaGrade"] == 3
    assert len(detail["levels"]) == 1
    assert detail["analysis"]["clinicalStatus"] == "pendiente_de_validar"

    # Un nivel que llega después del cierre vuelve a calcular el análisis.
    late = envelope("level_record", session_id, level=2, outcome="safe_exit", criterionMet=False)
    assert api.send(device, late).status_code == 201
    detail = client.get(f"{API}/me/sessions/{session_id}", headers=headers).json()
    assert len(detail["levels"]) == 2
    assert detail["analysis"]["recommendation"] != "advance"


def test_test_sessions_are_not_analyzed(client, api):
    _, headers = api.user_with_headers("patient")
    device = api.pair(headers)["headers"]
    session_id = full_session(api, device, test_session=True)
    detail = client.get(f"{API}/me/sessions/{session_id}", headers=headers).json()
    assert detail["testSession"] is True and detail["analysis"] is None
    assert client.get(f"{API}/me/progress", headers=headers).json()["sessionsCount"] == 0


def test_records_validation_errors(api):
    device = _device(api)
    cases = [
        ({"schemaVersion": 2}, "schemaVersion"),
        ({"type": "otro"}, "type"),
        ({"recordId": "no-uuid"}, "recordId"),
        ({"inesperado": 1}, "inesperado"),
    ]
    for change, field in cases:
        env = {**envelope("session_start"), **change}
        r = api.send(device, env)
        assert r.status_code == 422, change
        assert r.json()["code"] == "VALIDATION_ERROR"
        assert field in {e["field"] for e in r.json()["errors"]}

    payload_cases = [
        ("session_start", {"phobiaGrade": 6}, "payload.phobiaGrade"),
        ("session_start", {"startedAt": "2026-10-30T21:00:00"}, "payload.startedAt"),
        ("session_start", {"deviceModel": "pico4"}, "payload.deviceModel"),
        ("level_record", {"suds": [{"phase": "before", "value": 101, "at": 0}]}, "payload.suds.0.value"),
        ("level_record", {"suds": [{"phase": "before", "value": 50.5, "at": 0}]}, "payload.suds.0.value"),
        ("level_record", {"outcome": "otro"}, "payload.outcome"),
        ("level_record", {"events": [{"t": 1, "type": "desconocido"}]}, "payload.events.0.type"),
        ("level_record", {"minDistanceM": -1}, "payload.minDistanceM"),
        ("session_end", {"endReason": "crash"}, "payload.endReason"),
    ]
    for kind, change, field in payload_cases:
        r = api.send(device, envelope(kind, **change))
        assert r.status_code == 422, (kind, change)
        assert field in {e["field"] for e in r.json()["errors"]}, r.json()

    r = api.send(device, envelope("level_record", endedAt="2026-10-30T21:00:00Z"))
    assert r.status_code == 422


def test_min_distance_null_is_accepted(api):
    assert api.send(_device(api), envelope("level_record", minDistanceM=None)).status_code == 201


def test_records_malformed_json_and_size(client, api):
    device = _device(api)
    headers = {**device, "Content-Type": "application/json"}
    r = client.post(f"{API}/device/records", content=b"{roto", headers=headers)
    assert r.status_code == 400 and r.json()["code"] == "BAD_REQUEST"
    r = client.post(f"{API}/device/records", content=b'{"x": NaN}', headers=headers)
    assert r.status_code == 400

    big = envelope("level_record")
    big["payload"]["samples"]["distanceM"] = [1.2345] * 60000
    r = api.send(device, big)
    assert r.status_code == 413 and r.json()["code"] == "PAYLOAD_TOO_LARGE"

    near = envelope("level_record")
    near["payload"]["samples"]["distanceM"] = [1.25] * 40000  # unos 240 KB, por debajo del límite
    assert len(json.dumps(near)) < 256 * 1024
    assert api.send(device, near).status_code == 201

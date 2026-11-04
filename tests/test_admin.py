"""Administración: usuarios, roles, asignaciones y exportación anónima (contrato, sección 4.4)."""

import csv
import io
import uuid

from tests.conftest import API, full_session


def test_create_and_list_users(client, api, admin):
    _, headers = admin
    body = {"fullName": "Laura Gómez", "email": "laura@example.com", "role": "professional", "temporaryPassword": "temporal-123"}
    r = client.post(f"{API}/admin/users", json=body, headers=headers)
    assert r.status_code == 201
    created = r.json()
    assert created["role"] == "professional" and created["active"] is True and created["fullName"] == "Laura Gómez"
    assert client.post(f"{API}/auth/login", json={"email": "laura@example.com", "password": "temporal-123"}).status_code == 200
    assert client.post(f"{API}/admin/users", json=body, headers=headers).json()["code"] == "EMAIL_TAKEN"

    r = client.get(f"{API}/admin/users", params={"role": "professional"}, headers=headers)
    assert [u["email"] for u in r.json()["items"]] == ["laura@example.com"]
    r = client.get(f"{API}/admin/users", params={"q": "GÓMEZ"}, headers=headers)
    assert [u["id"] for u in r.json()["items"]] == [created["id"]]
    r = client.get(f"{API}/admin/users", params={"q": "100%_"}, headers=headers)
    assert r.json()["items"] == []


def test_create_user_validation(client, admin):
    _, headers = admin
    r = client.post(
        f"{API}/admin/users",
        json={"fullName": "X", "email": "x@example.com", "role": "superuser", "temporaryPassword": "temporal-123"},
        headers=headers,
    )
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "role"


def test_users_pagination(client, api, admin):
    _, headers = admin
    for _ in range(4):
        api.make_user("patient")
    seen, cursor = [], None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = client.get(f"{API}/admin/users", params=params, headers=headers).json()
        seen += [u["id"] for u in page["items"]]
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 5
    assert client.get(f"{API}/admin/users", params={"limit": 101}, headers=headers).status_code == 422
    r = client.get(f"{API}/admin/users", params={"cursor": "no-vale"}, headers=headers)
    assert r.status_code == 422 and r.json()["errors"] == [{"field": "cursor", "code": "invalid_format"}]


def test_patch_user_role_and_active(client, api, admin):
    _, headers = admin
    user = api.make_user("patient")
    r = client.patch(f"{API}/admin/users/{user['id']}", json={"role": "professional"}, headers=headers)
    assert r.status_code == 200 and r.json()["role"] == "professional"
    r = client.patch(f"{API}/admin/users/{user['id']}", json={"active": False}, headers=headers)
    assert r.status_code == 200 and r.json()["active"] is False
    assert client.post(f"{API}/auth/login", json={"email": user["email"], "password": user["password"]}).status_code == 423
    assert client.patch(f"{API}/admin/users/{uuid.uuid4()}", json={"active": False}, headers=headers).status_code == 404


def test_deactivated_user_loses_access_immediately(client, api, admin):
    _, admin_headers = admin
    user, headers = api.user_with_headers("professional")
    client.patch(f"{API}/admin/users/{user['id']}", json={"active": False}, headers=admin_headers)
    r = client.get(f"{API}/me", headers=headers)
    assert r.status_code == 423 and r.json()["code"] == "ACCOUNT_DISABLED"


def test_last_admin_protected(client, api, admin):
    me, headers = admin
    for change in ({"role": "patient"}, {"active": False}):
        r = client.patch(f"{API}/admin/users/{me['id']}", json=change, headers=headers)
        assert r.status_code == 409 and r.json()["code"] == "LAST_ADMIN"
    second = api.make_user("admin")
    assert client.patch(f"{API}/admin/users/{second['id']}", json={"active": False}, headers=headers).status_code == 200


def test_assignments_crud(client, api, admin):
    _, headers = admin
    professional = api.make_user("professional")
    patient = api.make_user("patient")
    assignment_id = api.assign(headers, professional, patient)
    again = client.post(
        f"{API}/admin/assignments", json={"professionalId": professional["id"], "patientId": patient["id"]}, headers=headers
    )
    assert again.status_code == 200 and again.json()["assignmentId"] == assignment_id

    items = client.get(f"{API}/admin/assignments", params={"professionalId": professional["id"]}, headers=headers).json()["items"]
    assert items[0]["patientName"] == patient["fullName"] and items[0]["professionalName"] == professional["fullName"]

    assert client.delete(f"{API}/admin/assignments/{assignment_id}", headers=headers).status_code == 204
    assert client.delete(f"{API}/admin/assignments/{assignment_id}", headers=headers).status_code == 404
    assert client.get(f"{API}/admin/assignments", headers=headers).json()["items"] == []


def test_assignment_requires_right_roles(client, api, admin):
    _, headers = admin
    patient = api.make_user("patient")
    r = client.post(f"{API}/admin/assignments", json={"professionalId": patient["id"], "patientId": patient["id"]}, headers=headers)
    assert r.status_code == 422
    assert {e["field"] for e in r.json()["errors"]} == {"professionalId"}


def test_export_is_anonymous_and_excludes_test_sessions(client, api, admin):
    _, admin_headers = admin
    patient, patient_headers = api.user_with_headers("patient")
    device = api.pair(patient_headers)
    real = full_session(api, device["headers"])
    test = full_session(api, device["headers"], test_session=True)

    first = client.get(f"{API}/admin/exports/analysis-dataset", headers=admin_headers)
    assert first.status_code == 200 and first.headers["cache-control"] == "no-store"
    rows = first.json()["rows"]
    assert len(rows) == 1
    text = first.text
    for secret in (real, test, patient["id"], device["deviceId"], patient["email"], patient["fullName"]):
        assert secret not in text
    assert "pseudonym" not in text.lower()
    assert "startedAt" not in text and "2026-10-30" not in text
    assert rows[0]["toleranceIndex"] is not None and rows[0]["sudsBefore"] == 60

    second = client.get(f"{API}/admin/exports/analysis-dataset", headers=admin_headers).json()["rows"]
    assert second[0]["subjectKey"] != rows[0]["subjectKey"]
    assert second[0]["sessionKey"] != rows[0]["sessionKey"]


def test_export_csv(client, api, admin):
    _, admin_headers = admin
    _, patient_headers = api.user_with_headers("patient")
    full_session(api, api.pair(patient_headers)["headers"])
    r = client.get(f"{API}/admin/exports/analysis-dataset", headers={**admin_headers, "Accept": "text/csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 1 and rows[0]["level"] == "1"

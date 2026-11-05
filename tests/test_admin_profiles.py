"""Use case "Gestionar perfiles" for the administrator (v1.1.0)."""

import uuid

from tests.conftest import API, example

TEMPORARY_PASSWORD = "temporal-nueva-1"


def test_admin_reads_one_profile(client, api, admin):
    _, headers = admin
    user = api.make_user("professional")
    r = client.get(f"{API}/admin/users/{user['id']}", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"id": user["id"], "fullName": user["fullName"], "email": user["email"], "role": "professional", "active": True}
    assert client.get(f"{API}/admin/users/{uuid.uuid4()}", headers=headers).status_code == 404


def test_admin_edits_name_and_email(client, api, admin):
    _, headers = admin
    user = api.make_user("professional")
    r = client.patch(
        f"{API}/admin/users/{user['id']}",
        json={"fullName": "Nombre Corregido", "email": "Corregido@Example.com"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["fullName"] == "Nombre Corregido" and r.json()["email"] == "corregido@example.com"
    assert r.json()["role"] == "professional" and r.json()["active"] is True
    assert client.patch(f"{API}/admin/users/{user['id']}", json=example("admin_user_patch.request.json"), headers=headers).status_code == 200


def test_admin_profile_edit_rejects_taken_email_and_blank_name(client, api, admin):
    _, headers = admin
    user, other = api.make_user("professional"), api.make_user("patient")
    taken = client.patch(f"{API}/admin/users/{user['id']}", json={"email": other["email"]}, headers=headers)
    assert taken.status_code == 409 and taken.json()["code"] == "EMAIL_TAKEN"
    assert client.patch(f"{API}/admin/users/{user['id']}", json={"fullName": ""}, headers=headers).status_code == 422


def test_admin_password_reset_closes_web_sessions(client, api, admin):
    _, headers = admin
    user = api.make_user("patient")
    api.login(user)  # leaves a live refresh cookie for this user
    r = client.put(f"{API}/admin/users/{user['id']}/password", json={"temporaryPassword": TEMPORARY_PASSWORD}, headers=headers)
    assert r.status_code == 204
    assert client.post(f"{API}/auth/refresh").status_code == 401

    old = client.post(f"{API}/auth/login", json={"email": user["email"], "password": user["password"]})
    assert old.status_code == 401 and old.json()["code"] == "INVALID_CREDENTIALS"
    new = client.post(f"{API}/auth/login", json={"email": user["email"], "password": TEMPORARY_PASSWORD})
    assert new.status_code == 200


def test_admin_password_reset_validation(client, api, admin):
    _, headers = admin
    user = api.make_user("patient")
    short = client.put(f"{API}/admin/users/{user['id']}/password", json={"temporaryPassword": "corta"}, headers=headers)
    assert short.status_code == 422
    body = example("admin_password_reset.request.json")
    assert client.put(f"{API}/admin/users/{uuid.uuid4()}/password", json=body, headers=headers).status_code == 404

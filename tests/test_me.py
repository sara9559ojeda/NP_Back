"""Datos propios, contraseña y retirada del consentimiento (contrato, secciones 3 y 4.3)."""

from sqlalchemy import select

from tests.conftest import API, full_session


def test_get_me(client, api):
    user, headers = api.user_with_headers("patient")
    r = client.get(f"{API}/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == user["id"] and body["role"] == "patient"
    assert body["fullName"] == user["fullName"] and body["email"] == user["email"]
    assert body["consents"][0]["consentVersion"] == "2026-10-v1"
    assert body["consents"][0]["grantedAt"].endswith("Z")


def test_patch_me(client, api):
    _, headers = api.user_with_headers("professional")
    r = client.patch(f"{API}/me", json={"fullName": "  Nombre Nuevo  ", "email": "Nuevo@Example.com"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["fullName"] == "Nombre Nuevo"
    assert r.json()["email"] == "nuevo@example.com"


def test_patch_me_errors(client, api):
    other = api.make_user()
    _, headers = api.user_with_headers("patient")
    r = client.patch(f"{API}/me", json={"email": "mal", "fullName": ""}, headers=headers)
    assert r.status_code == 422
    assert {e["field"] for e in r.json()["errors"]} == {"email", "fullName"}
    r = client.patch(f"{API}/me", json={"email": other["email"]}, headers=headers)
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_TAKEN"
    assert client.patch(f"{API}/me", json={"role": "admin"}, headers=headers).status_code == 422


def test_change_password(client, api):
    user, headers = api.user_with_headers("patient")
    r = client.put(f"{API}/me/password", json={"currentPassword": "incorrecta", "newPassword": "nueva-clave-123"}, headers=headers)
    assert r.status_code == 422
    assert r.json()["errors"] == [{"field": "currentPassword", "code": "incorrect"}]
    r = client.put(
        f"{API}/me/password", json={"currentPassword": user["password"], "newPassword": "nueva-clave-123"}, headers=headers
    )
    assert r.status_code == 204
    # Todas las sesiones web quedan cerradas, también la actual.
    refresh = client.cookies.get("np_refresh")
    client.cookies.clear()
    client.cookies.set("np_refresh", refresh, path="/api/v1/auth")
    assert client.post(f"{API}/auth/refresh").status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": user["email"], "password": user["password"]}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": user["email"], "password": "nueva-clave-123"}).status_code == 200


def test_withdraw_consent_unlinks_and_anonymizes(client, api, admin):
    from app.db.models import IdentityLink, PersonalData, TherapySession, User
    from app.db.session import _session_factory

    _, admin_headers = admin
    patient, patient_headers = api.user_with_headers("patient")
    professional, professional_headers = api.user_with_headers("professional")
    api.assign(admin_headers, professional, patient)
    device = api.pair(patient_headers)
    session_id = full_session(api, device["headers"])

    r = client.post(f"{API}/me/consents/withdraw", headers=patient_headers)
    assert r.status_code == 202
    assert r.json() == {"status": "withdrawn"}

    db = _session_factory()()
    try:
        user = db.get(User, patient["id"])
        assert user.active is False and user.password_hash is None and patient["email"] != user.email
        assert db.get(PersonalData, patient["id"]) is None
        assert db.scalars(select(IdentityLink).where(IdentityLink.user_id == patient["id"])).first() is None
        # Los datos clínicos se conservan, sin vínculo.
        assert db.get(TherapySession, session_id) is not None
    finally:
        db.close()

    # La cuenta queda desactivada, el visor deja de enviar y el profesional ya no lo ve.
    assert client.get(f"{API}/me", headers=patient_headers).status_code == 423
    assert client.post(f"{API}/auth/login", json={"email": patient["email"], "password": patient["password"]}).status_code == 401
    r = client.get(f"{API}/device/context", headers=device["headers"])
    assert r.status_code == 401 and r.json()["code"] == "DEVICE_REVOKED"
    assert client.get(f"{API}/patients", headers=professional_headers).json()["items"] == []
    assert client.get(f"{API}/patients/{patient['id']}/progress", headers=professional_headers).status_code == 404
    # El correo queda libre para un registro nuevo.
    body = {
        "fullName": "Otra Persona",
        "email": patient["email"],
        "password": "clave-segura-123",
        "consent": {"accepted": True, "consentVersion": "2026-10-v1"},
    }
    assert client.post(f"{API}/auth/register", json=body).status_code == 201


def test_withdraw_last_admin_is_rejected(client, admin):
    _, headers = admin
    r = client.post(f"{API}/me/consents/withdraw", headers=headers)
    assert r.status_code == 409 and r.json()["code"] == "LAST_ADMIN"

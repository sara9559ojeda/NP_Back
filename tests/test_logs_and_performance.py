"""Logs sin datos personales y tiempo de respuesta (contrato, sección 1; RQFN002)."""

import logging
import time

from tests.conftest import API, full_session


def test_no_personal_data_or_tokens_in_logs(client, api, admin, caplog):
    caplog.set_level(logging.DEBUG)
    _, admin_headers = admin
    patient, patient_headers = api.user_with_headers("patient")
    professional, professional_headers = api.user_with_headers("professional")
    api.assign(admin_headers, professional, patient)
    code = api.pairing_code(patient_headers)
    paired = client.post(f"{API}/device/pair", json={"code": code, "deviceModel": "quest3", "appVersion": "0.2.0"}).json()
    device_headers = {"Authorization": f"Bearer {paired['deviceToken']}"}
    full_session(api, device_headers)
    note_text = "Observación privada de la consulta"
    client.post(f"{API}/patients/{patient['id']}/notes", json={"text": note_text}, headers=professional_headers)
    client.get(f"{API}/admin/users", params={"q": patient["email"]}, headers=admin_headers)
    client.post(f"{API}/auth/login", json={"email": patient["email"], "password": "clave-incorrecta"})
    client.post(
        f"{API}/auth/register",
        json={"fullName": "Ana Registro", "email": "ana.registro@example.com", "password": "clave-segura-123", "consent": {"accepted": True, "consentVersion": "v"}},
    )
    client.patch(f"{API}/me", json={"email": patient["email"]}, headers=professional_headers)  # 409 con el correo ajeno

    # Solo los logs del servidor: los de httpx son del cliente de pruebas.
    server_records = [r for r in caplog.records if not r.name.startswith("httpx")]
    logs = "\n".join(record.getMessage() for record in server_records)
    assert "neurophobia.access" in {r.name for r in server_records}
    secrets = [
        patient["email"],
        patient["fullName"],
        patient["password"],
        professional["email"],
        "ana.registro@example.com",
        "Ana Registro",
        code,
        code.replace("-", ""),
        paired["deviceToken"],
        patient_headers["Authorization"].split()[1],
        note_text,
        client.cookies.get("np_refresh") or "np_refresh=",
    ]
    for value in secrets:
        assert value not in logs, "dato sensible en los logs"
    assert "@" not in logs


def test_redaction_filter_masks_emails_and_tokens():
    from app.core.logging import redact

    text = redact("correo ana@example.com token npd_abcdefghijklmnop Bearer eyJa.eyJb.c")
    assert "ana@example.com" not in text and "npd_abcdefghijklmnop" not in text and "eyJa" not in text


def test_response_time_under_two_seconds(client, api, admin):
    """RQFN002: menos de 2 s en condiciones normales (incluye Argon2id en el inicio de sesión)."""
    _, admin_headers = admin
    patient, patient_headers = api.user_with_headers("patient")
    professional, professional_headers = api.user_with_headers("professional")
    api.assign(admin_headers, professional, patient)
    device = api.pair(patient_headers)
    for _ in range(5):
        full_session(api, device["headers"])

    calls = [
        ("post", "/auth/login", {"email": patient["email"], "password": patient["password"]}, {}),
        ("get", "/me", None, patient_headers),
        ("get", "/me/progress", None, patient_headers),
        ("get", "/me/sessions", None, patient_headers),
        ("get", "/patients", None, professional_headers),
        ("get", f"/patients/{patient['id']}/sessions", None, professional_headers),
        ("get", "/device/context", None, device["headers"]),
        ("get", "/admin/users", None, admin_headers),
        ("get", "/admin/exports/analysis-dataset", None, admin_headers),
    ]
    for method, path, body, headers in calls:
        start = time.perf_counter()
        r = client.request(method, f"{API}{path}", json=body, headers=headers)
        elapsed = time.perf_counter() - start
        assert r.status_code < 400, path
        assert elapsed < 2.0, f"{path}: {elapsed:.2f} s"

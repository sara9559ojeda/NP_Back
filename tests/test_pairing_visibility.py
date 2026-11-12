"""La web ve el visor recién emparejado en cuanto consulta, sin cachés intermedias (contrato, sección 6.1)."""

from tests.conftest import API


def test_new_device_is_listed_immediately_without_cache(client, api):
    _, patient_headers = api.user_with_headers("patient")
    before = client.get(f"{API}/me/devices", headers=patient_headers)
    assert before.status_code == 200 and before.json()["items"] == []

    device = api.pair(patient_headers)

    after = client.get(f"{API}/me/devices", headers=patient_headers)
    assert after.status_code == 200
    assert after.headers["cache-control"] == "no-store"
    [listed] = after.json()["items"]
    assert listed["deviceId"] == device["deviceId"]
    assert listed["deviceModel"] == "quest3" and listed["revokedAt"] is None and listed["pairedAt"]

    therapy = client.get(f"{API}/me/therapy", headers=patient_headers)
    assert therapy.headers["cache-control"] == "no-store"
    assert therapy.json()["pairedDevices"] == 1


def test_revoked_device_is_reported_as_revoked(client, api):
    _, patient_headers = api.user_with_headers("patient")
    device = api.pair(patient_headers)
    assert client.delete(f"{API}/me/devices/{device['deviceId']}", headers=patient_headers).status_code == 204

    [listed] = client.get(f"{API}/me/devices", headers=patient_headers).json()["items"]
    assert listed["revokedAt"] is not None
    assert client.get(f"{API}/me/therapy", headers=patient_headers).json()["pairedDevices"] == 0

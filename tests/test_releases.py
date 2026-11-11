import hashlib
import json
from types import SimpleNamespace

import pytest

from app.core.errors import ApiError
from app.services import releases
from tests.conftest import API


def write_release(directory, **changes):
    artifact = directory / "neurophobia.apk"
    artifact.write_bytes(b"PK\x03\x04evaluation-build")
    manifest = {
        "filename": artifact.name, "version": "0.2.0", "versionCode": 2,
        "createdAt": "2026-11-10T20:00:00Z", "bytes": artifact.stat().st_size,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "sourceCommit": "a" * 40,
        "sourceDirty": False, "backendUrl": "https://demo.example.com",
        "signedForDistribution": True, "debuggable": False,
        "headsetTested": True, "distributionReady": True,
    }
    manifest.update(changes)
    (directory / "release.json").write_text(json.dumps(manifest), encoding="utf-8")
    return artifact, manifest


@pytest.mark.parametrize("change", [
    {"headsetTested": False}, {"signedForDistribution": False}, {"debuggable": True},
    {"sourceDirty": True}, {"distributionReady": False}, {"backendUrl": "http://localhost:8000"},
])
def test_unvalidated_release_cannot_be_downloaded(tmp_path, monkeypatch, change):
    write_release(tmp_path, **change)
    monkeypatch.setattr(releases, "get_settings", lambda: SimpleNamespace(apk_release_directory=tmp_path))
    assert releases.current_release().status == "pending_validation"
    with pytest.raises(ApiError) as error:
        releases.download_release()
    assert error.value.code == "RELEASE_UNAVAILABLE"


def test_release_integrity_failure_is_not_served(tmp_path, monkeypatch):
    artifact, _ = write_release(tmp_path)
    monkeypatch.setattr(releases, "get_settings", lambda: SimpleNamespace(apk_release_directory=tmp_path))
    artifact.write_bytes(b"PK\x03\x04corrupted-build-")
    with pytest.raises(ApiError):
        releases.download_release()


def test_manifest_cannot_escape_release_directory(tmp_path, monkeypatch):
    write_release(tmp_path, filename="../private.apk")
    monkeypatch.setattr(releases, "get_settings", lambda: SimpleNamespace(apk_release_directory=tmp_path))
    with pytest.raises(ApiError):
        releases.current_release()


def test_download_is_admin_only_and_never_cached(client, api, admin, tmp_path, monkeypatch):
    artifact, manifest = write_release(tmp_path)
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "apk_release_directory", tmp_path)
    path = f"{API}/admin/app-release/download"
    assert client.get(path).status_code == 401
    for role in ("patient", "professional"):
        _, headers = api.user_with_headers(role)
        assert client.get(path, headers=headers).status_code == 403
    public = client.get(f"{API}/public/app-release")
    assert public.json()["status"] == "available"
    assert "url" not in public.json() and "filename" not in public.json()
    response = client.get(path, headers=admin[1])
    assert response.status_code == 200
    assert response.content == artifact.read_bytes()
    assert response.headers["x-content-sha256"] == manifest["sha256"]
    assert "no-store" in response.headers["cache-control"]


def test_missing_release_is_reported_without_storage_paths(client):
    response = client.get(f"{API}/public/app-release")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"

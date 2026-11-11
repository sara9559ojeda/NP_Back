import hashlib
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.errors import ApiError
from app.schemas.releases import AppRelease, ReleaseManifest

MAX_MANIFEST_BYTES = 16384


def release_files() -> tuple[ReleaseManifest, Path] | None:
    directory = get_settings().apk_release_directory
    if directory is None:
        return None
    root = directory.resolve()
    manifest_path = root / "release.json"
    try:
        with manifest_path.open("rb") as stream:
            content = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(content) > MAX_MANIFEST_BYTES:
            raise ValueError("Release manifest is too large")
        manifest = ReleaseManifest.model_validate_json(content)
        artifact = (root / manifest.filename).resolve()
        if not artifact.is_relative_to(root) or artifact.stat().st_size != manifest.bytes:
            raise ValueError("Release artifact does not match its manifest")
        return manifest, artifact
    except FileNotFoundError:
        return None
    except (OSError, ValueError, ValidationError) as exc:
        raise ApiError(503, "STORAGE_UNAVAILABLE", "La descarga no está disponible temporalmente.") from exc


def ready(manifest: ReleaseManifest) -> bool:
    return (
        manifest.distribution_ready
        and manifest.signed_for_distribution
        and not manifest.debuggable
        and manifest.headset_tested
        and not manifest.source_dirty
        and manifest.backend_url.scheme == "https"
    )


def current_release() -> AppRelease:
    files = release_files()
    if files is None:
        return AppRelease(status="unavailable")
    manifest, _ = files
    return AppRelease(
        status="available" if ready(manifest) else "pending_validation",
        version=manifest.version,
        version_code=manifest.version_code,
        bytes=manifest.bytes,
        sha256=manifest.sha256,
        created_at=manifest.created_at,
        headset_tested=manifest.headset_tested,
    )


@lru_cache(maxsize=8)
def _digest(path: str, size: int, modified_ns: int) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_release() -> tuple[Path, str]:
    files = release_files()
    if files is None or not ready(files[0]):
        raise ApiError(409, "RELEASE_UNAVAILABLE", "No hay un APK validado para distribuir.")
    manifest, artifact = files
    try:
        stat = artifact.stat()
        with artifact.open("rb") as stream:
            signature = stream.read(4)
        if signature != b"PK\x03\x04" or _digest(str(artifact), stat.st_size, stat.st_mtime_ns) != manifest.sha256:
            raise ValueError("APK integrity check failed")
    except (OSError, ValueError) as exc:
        raise ApiError(503, "STORAGE_UNAVAILABLE", "No se pudo verificar el archivo de instalación.") from exc
    return artifact, manifest.sha256

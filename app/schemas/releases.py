from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, StringConstraints

from app.schemas.common import CamelModel


class ReleaseManifest(CamelModel):
    filename: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*\.apk$")]
    version: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    version_code: Annotated[int, Field(gt=0)]
    created_at: datetime
    bytes: Annotated[int, Field(gt=0)]
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    source_commit: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
    source_dirty: bool = True
    backend_url: HttpUrl
    signed_for_distribution: bool
    debuggable: bool
    headset_tested: bool = False
    distribution_ready: bool = False


class AppRelease(CamelModel):
    status: Literal["unavailable", "pending_validation", "available"]
    version: str | None = None
    version_code: int | None = None
    bytes: int | None = None
    sha256: str | None = None
    created_at: datetime | None = None
    headset_tested: bool = False
    download_role: Literal["admin"] = "admin"

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.deps import AdminUser
from app.api.docs import problems
from app.schemas.releases import AppRelease
from app.services import releases

router = APIRouter(tags=["releases"])


@router.get("/public/app-release", response_model=AppRelease, responses=problems(503))
def app_release() -> AppRelease:
    return releases.current_release()


@router.get(
    "/admin/app-release/download",
    response_class=FileResponse,
    responses={200: {"content": {"application/vnd.android.package-archive": {}}}, **problems(401, 403, 409, 503)},
)
def download_app(actor: AdminUser) -> FileResponse:
    artifact, digest = releases.download_release()
    return FileResponse(
        artifact,
        filename="neurophobia.apk",
        media_type="application/vnd.android.package-archive",
        headers={"Cache-Control": "private, no-store", "X-Content-SHA256": digest},
    )

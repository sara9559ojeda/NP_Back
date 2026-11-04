"""``GET /health`` (contrato, sección 9). Sin datos."""

from fastapi import APIRouter

from app.core.config import APP_VERSION
from app.schemas.common import CamelModel

router = APIRouter(tags=["health"])


class HealthOut(CamelModel):
    status: str
    version: str


@router.get("/health", response_model=HealthOut, summary="Estado del servicio")
def health() -> HealthOut:
    return HealthOut(status="ok", version=APP_VERSION)

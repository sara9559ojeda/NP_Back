"""Health endpoints (contract, section 9). They never return personal data.

``GET /health`` does not touch the database. ``GET /health/ready`` (v1.1.0) also checks the
"Interfaz BD <-> PostgreSQL" link of the deployment diagram.
"""

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import Db
from app.api.docs import problems
from app.core.config import APP_VERSION
from app.schemas.common import CamelModel

router = APIRouter(tags=["health"])


class HealthOut(CamelModel):
    status: str
    version: str


class ReadyOut(CamelModel):
    status: str
    version: str
    database: str


@router.get("/health", response_model=HealthOut, summary="Estado del servicio")
def health() -> HealthOut:
    return HealthOut(status="ok", version=APP_VERSION)


@router.get(
    "/health/ready",
    response_model=ReadyOut,
    responses=problems(503),
    summary="Listo para atender: el servidor llega a PostgreSQL",
)
def ready(db: Db) -> ReadyOut:
    db.execute(text("SELECT 1"))
    return ReadyOut(status="ok", version=APP_VERSION, database="ok")

"""Tipos comunes de los esquemas de la API: ``camelCase`` hacia fuera y fechas UTC con ``Z``."""

from datetime import datetime, timezone
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


def _utc_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


UtcDateTime = Annotated[datetime, PlainSerializer(_utc_z, return_type=str, when_used="json")]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


T = TypeVar("T")


class Paginated(CamelModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class StatusOut(CamelModel):
    status: str


class Problem(BaseModel):
    """Cuerpo de error ``application/problem+json`` (RFC 9457). Solo para la documentación OpenAPI."""

    type: str
    title: str
    status: int
    code: str
    detail: str | None = None
    errors: list[dict[str, str]] | None = None

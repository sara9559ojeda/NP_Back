"""Extracción de rasgos anónimos a partir de los payloads del visor.

Recibe diccionarios (los ``payload`` JSONB) y no depende de la base de datos.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.ai.base import LevelFeatures, SessionFeatures


def _suds(payload: dict[str, Any], phase: str, *, last: bool) -> int | None:
    values = [s["value"] for s in payload.get("suds") or [] if s.get("phase") == phase]
    if not values:
        return None
    return int(values[-1] if last else values[0])


def _epoch(value: Any) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()


def level_features(payload: dict[str, Any]) -> LevelFeatures:
    return LevelFeatures(
        level=int(payload["level"]),
        attempt=int(payload["attempt"]),
        outcome=str(payload["outcome"]),
        criterion_met=bool(payload["criterionMet"]),
        permanence_seconds=float(payload["permanenceSeconds"]),
        avoidance_count=int(payload["avoidanceCount"]),
        min_distance_m=payload.get("minDistanceM"),
        suds_before=_suds(payload, "before", last=False),
        suds_after=_suds(payload, "after", last=True),
        ended_at_epoch=_epoch(payload["endedAt"]),
    )


def session_features(
    *,
    phobia_grade: int | None,
    level_reached: int | None,
    end_reason: str | None,
    level_payloads: Iterable[dict[str, Any]],
) -> SessionFeatures:
    return SessionFeatures(
        phobia_grade=phobia_grade,
        level_reached=level_reached,
        end_reason=end_reason,
        levels=tuple(level_features(p) for p in level_payloads),
    )

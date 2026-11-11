from sqlalchemy.orm import Session

from app.db.models import Analysis, TherapySession
from app.repositories import clinical
from app.schemas.tracking import SessionComparison


def explain_analysis(basis: list[dict]) -> str:
    values = {item["feature"]: item["value"] for item in basis}
    parts = []
    if "criterionMet" in values:
        parts.append("Se cumplió el criterio del nivel evaluado." if values["criterionMet"] else "No se cumplió el criterio del nivel evaluado.")
    if "avoidanceCount" in values:
        parts.append(f"Se registraron {int(values['avoidanceCount'])} eventos de alejamiento.")
    if "sudsDrop" in values:
        change = values["sudsDrop"]
        if change > 0:
            parts.append(f"El malestar declarado bajó {change:g} puntos entre las respuestas antes y después.")
        elif change < 0:
            parts.append(f"El malestar declarado subió {abs(change):g} puntos entre las respuestas antes y después.")
        else:
            parts.append("Las respuestas de malestar antes y después fueron iguales.")
    else:
        parts.append("Faltan respuestas de malestar para comparar el antes y el después.")
    if values.get("safeExit"):
        parts.append("La salida segura impide recomendar avanzar.")
    parts.append("Es una orientación técnica pendiente de revisión profesional, no una medida de mejoría clínica.")
    return " ".join(parts)


def compare_session(db: Session, current: TherapySession, analysis: Analysis) -> SessionComparison | None:
    if current.started_at is None or not current.has_end or current.test_session is not False:
        return None
    previous = clinical.previous_closed_session(db, current)
    if previous is None:
        return None
    previous_analysis = clinical.analyses_for(db, [previous.id], analysis.method).get(previous.id)
    comparable = (
        previous_analysis is not None
        and previous_analysis.method_version == analysis.method_version
        and analysis.evaluated_level is not None
        and previous_analysis.evaluated_level == analysis.evaluated_level
    )
    return SessionComparison(
        previous_session_id=previous.id,
        previous_ended_at=previous.ended_at,
        level_delta=current.level_reached - previous.level_reached
        if current.level_reached is not None and previous.level_reached is not None else None,
        duration_delta_seconds=round(current.total_duration_seconds - previous.total_duration_seconds, 3)
        if current.total_duration_seconds is not None and previous.total_duration_seconds is not None else None,
        tolerance_delta=round(analysis.tolerance_index - previous_analysis.tolerance_index, 3) if comparable else None,
        tolerance_comparable=comparable,
    )

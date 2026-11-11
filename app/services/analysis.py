"""Une el módulo de IA con los datos guardados (contrato, sección 7; D13).

Se analiza al cerrar la sesión. Si después llegan registros desordenados de la misma sesión,
se vuelve a calcular. Las sesiones de prueba (``testSession = true``) no se analizan.
"""

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.ai.features import session_features
from app.ai.registry import get_analyzer
from app.ai.groq_summary import enabled, fingerprint, make_facts
from app.core.config import get_settings
from app.core.security import utcnow
from app.db.models import TherapySession
from app.repositories import clinical
from app.schemas.device import FeedbackOut


def refresh_analysis(db: Session, session: TherapySession) -> None:
    analyzer = get_analyzer(get_settings().ai_method)
    if not (session.has_start and session.has_end) or session.test_session is not False:
        clinical.delete_analysis(db, session.id, analyzer.method)
        return
    records = clinical.level_records(db, session.id)
    features = session_features(
        phobia_grade=session.phobia_grade,
        level_reached=session.level_reached,
        end_reason=session.end_reason,
        level_payloads=[r.payload for r in records],
    )
    result = analyzer.analyze(features)
    if result is None:
        clinical.delete_analysis(db, session.id, analyzer.method)
        return
    basis = [asdict(item) for item in result.basis]
    settings = get_settings()
    target = max(features.levels, key=lambda level: (level.level, level.ended_at_epoch, level.attempt))
    facts = make_facts(
        session, result.recommendation, result.tolerance_index, basis,
        evaluated_level=target.level, evaluated_attempt=target.attempt,
        method=result.method, method_version=result.method_version,
    )
    clinical.upsert_analysis(
        db,
        {
            "session_id": session.id,
            "method": result.method,
            "method_version": result.method_version,
            "tolerance_index": result.tolerance_index,
            "recommendation": result.recommendation,
            "basis": basis,
            "clinical_status": result.clinical_status,
            "created_at": utcnow(),
            "input_fingerprint": fingerprint(facts, settings.groq_model, enabled(settings)),
            "evaluated_level": target.level,
            "evaluated_attempt": target.attempt,
            "narrative_status": "pending" if enabled(settings) else "disabled",
            "narrative_text": None,
            "narrative_model": settings.groq_model if enabled(settings) else None,
            "narrative_started_at": None,
            "narrative_created_at": None,
        },
    )


def feedback_for(db: Session, session: TherapySession) -> FeedbackOut:
    """Feedback state of a session as currently stored (v1.1.0)."""
    if not (session.has_start and session.has_end):
        return FeedbackOut(status="pending")
    if session.test_session is not False:
        return FeedbackOut(status="not_applicable")
    analysis = clinical.analyses_for(db, [session.id], get_settings().ai_method).get(session.id)
    if analysis is None:
        return FeedbackOut(status="insufficient_data")
    return FeedbackOut(
        status="saved",
        recommendation=analysis.recommendation,
        tolerance_index=analysis.tolerance_index,
        method=analysis.method,
        clinical_status=analysis.clinical_status,
        created_at=analysis.created_at,
    )

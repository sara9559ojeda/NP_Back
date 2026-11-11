"""Therapy lifecycle from the UML/BPMN diagrams (contract v1.1.0).

- "Ajustar grado de fobia" before "Click comenzar": self-reported phobia grade (1-5) per patient,
  editable from the web or the headset and returned by ``GET /device/context``.
- "Iniciar y finalizar terapia": start and end still arrive as ``session_start`` and ``session_end``
  through the offline-first headset outbox; this module exposes them as a queryable state.
- "Consultar retroalimentación": stored AI analyses per session.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.pagination import Page, next_cursor
from app.core.security import utcnow
from app.db.models import Analysis, Patient, TherapySession
from app.repositories import clinical
from app.schemas.device import DeviceSessionOut, PhobiaGradeOut, SessionRef
from app.schemas.tracking import (
    FeedbackPage,
    LastSessionItem,
    OpenSessionOut,
    ProfessionalFeedbackItem,
    SessionFeedbackItem,
    TherapyStateOut,
)
from app.services.actor import DeviceActor
from app.services.analysis import feedback_for
from app.services.feedback import compare_session
from app.services.tracking import analysis_out, session_status


def _patient(db: Session, pseudonym: uuid.UUID) -> Patient:
    patient = clinical.get_patient(db, pseudonym)
    if patient is None:
        raise ApiError(404, "NOT_FOUND")
    return patient


# ───────────── phobia grade ─────────────


def set_phobia_grade(db: Session, pseudonym: uuid.UUID, grade: int) -> PhobiaGradeOut:
    patient = _patient(db, pseudonym)
    patient.phobia_grade = grade
    patient.phobia_grade_updated_at = utcnow()
    db.commit()
    return PhobiaGradeOut(phobia_grade=patient.phobia_grade, updated_at=patient.phobia_grade_updated_at)


def sync_phobia_grade_from_session(db: Session, pseudonym: uuid.UUID, grade: int, at: datetime) -> None:
    """A ``session_start`` ``phobiaGrade`` is also a self-report: keep it when it is the most recent one."""
    patient = clinical.get_patient(db, pseudonym)
    if patient is None:
        return
    if patient.phobia_grade_updated_at is None or patient.phobia_grade_updated_at < at:
        patient.phobia_grade = grade
        patient.phobia_grade_updated_at = at


# ───────────── therapy state ─────────────


def session_feedback(db: Session, s: TherapySession, analysis: Analysis) -> SessionFeedbackItem:
    return SessionFeedbackItem(
        session_id=s.id,
        started_at=s.started_at,
        ended_at=s.ended_at,
        phobia_grade=s.phobia_grade,
        level_reached=s.level_reached,
        end_reason=s.end_reason,
        analysis=analysis_out(analysis),
        total_duration_seconds=s.total_duration_seconds,
        comparison=compare_session(db, s, analysis),
    )


def therapy_state(db: Session, pseudonym: uuid.UUID) -> TherapyStateOut:
    patient = _patient(db, pseudonym)
    sessions = clinical.progress_sessions(db, pseudonym)
    closed = [s for s in sessions if s.has_end]
    last = closed[0] if closed else None
    analyses = clinical.analyses_for(db, [s.id for s in closed], get_settings().ai_method)
    analyzed = next((s for s in closed if s.id in analyses), None)
    current = clinical.open_session(db, pseudonym)
    return TherapyStateOut(
        phobia_grade=patient.phobia_grade,
        phobia_grade_updated_at=patient.phobia_grade_updated_at,
        allowed_start_level=patient.allowed_start_level,
        paired_devices=clinical.count_active_devices(db, pseudonym),
        open_session=OpenSessionOut(session_id=current.id, started_at=current.started_at) if current else None,
        last_session=LastSessionItem(
            session_id=last.id,
            started_at=last.started_at,
            level_reached=last.level_reached,
            total_duration_seconds=last.total_duration_seconds,
            recommendation=analyses[last.id].recommendation if last.id in analyses else None,
        )
        if last
        else None,
        last_feedback=session_feedback(db, analyzed, analyses[analyzed.id]) if analyzed else None,
    )


def session_ref(s: TherapySession) -> SessionRef:
    return SessionRef(session_id=s.id, status=session_status(s))


def device_session(db: Session, device: DeviceActor, session_id: uuid.UUID) -> DeviceSessionOut:
    s = clinical.get_session(db, device.pseudonym_id, session_id)
    if s is None:
        raise ApiError(404, "NOT_FOUND")
    out = DeviceSessionOut(
        session_id=s.id,
        status=session_status(s),
        started_at=s.started_at,
        ended_at=s.ended_at,
        phobia_grade=s.phobia_grade,
        level_reached=s.level_reached,
        levels_stored=clinical.count_level_records(db, s.id),
        feedback=feedback_for(db, s),
    )
    db.commit()  # persists the device's last_seen_at
    return out


# ───────────── feedback for the professional ─────────────


def feedback_page(db: Session, pseudonym: uuid.UUID, page: Page) -> FeedbackPage:
    rows = clinical.feedback_sessions(db, pseudonym, get_settings().ai_method, page)
    visible = rows[: page.limit]
    counts = clinical.notes_count_by_session(db, pseudonym, [s.id for s, _ in visible])
    items = [
        ProfessionalFeedbackItem(**session_feedback(db, s, a).model_dump(), notes_count=counts.get(s.id, 0)) for s, a in visible
    ]
    return FeedbackPage(items=items, next_cursor=next_cursor(rows, page, lambda r: (r[0].started_at, r[0].id)))


# ───────────── headset logout ─────────────


def unpair(db: Session, device: DeviceActor) -> None:
    """"Cerrar sesión" from the headset: revoke its own token. Pairing again needs a new code."""
    target = clinical.get_device(db, device.device_id, device.pseudonym_id)
    if target is not None and target.revoked_at is None:
        target.revoked_at = utcnow()
    db.commit()

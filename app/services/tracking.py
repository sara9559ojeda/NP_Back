"""Seguimiento clínico: progreso, sesiones, plan y notas (contrato, sección 5).

Aquí se aplica la regla de acceso de RQFN004:
- el paciente solo ve lo suyo;
- el profesional solo ve a sus pacientes asignados y, si pide otro, recibe 404 (no 403);
- el administrador no llega a estas funciones (D21).
"""

import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.pagination import Page, next_cursor
from app.core.security import utcnow
from app.db.models import Analysis, LevelRecord, Note, TherapySession
from app.repositories import clinical, identity
from app.schemas.tracking import (
    AnalysisOut,
    BasisItem,
    LastSessionItem,
    LevelRecordOut,
    NoteCreated,
    NoteOut,
    NotePage,
    PatientPage,
    PatientSummary,
    PlanOut,
    ProfessionalSessionDetail,
    ProgressOut,
    SessionDetail,
    SessionPage,
    SessionSummary,
)
from app.services.actor import Actor


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND")


def own_pseudonym(db: Session, actor: Actor) -> uuid.UUID:
    pseudonym = identity.get_pseudonym(db, actor.user_id)
    if pseudonym is None:
        raise _not_found()
    return pseudonym


def assigned_pseudonym(db: Session, actor: Actor, patient_id: uuid.UUID) -> uuid.UUID:
    """Seudónimo de un paciente asignado al profesional. Cualquier otro caso es 404."""
    if not identity.is_assigned(db, actor.user_id, patient_id):
        raise _not_found()
    pseudonym = identity.get_pseudonym(db, patient_id)
    if pseudonym is None:
        raise _not_found()
    return pseudonym


def _method() -> str:
    return get_settings().ai_method


def session_status(s: TherapySession) -> str:
    if not s.has_start:
        return "pending_start"
    return "closed" if s.has_end else "open"


def _summary(s: TherapySession, analysis: Analysis | None) -> SessionSummary:
    return SessionSummary(
        session_id=s.id,
        status=session_status(s),
        started_at=s.started_at,
        ended_at=s.ended_at,
        phobia_grade=s.phobia_grade,
        test_session=s.test_session,
        end_reason=s.end_reason,
        level_reached=s.level_reached,
        total_duration_seconds=s.total_duration_seconds,
        recommendation=analysis.recommendation if analysis else None,
        tolerance_index=analysis.tolerance_index if analysis else None,
    )


def analysis_out(a: Analysis) -> AnalysisOut:
    return AnalysisOut(
        tolerance_index=a.tolerance_index,
        recommendation=a.recommendation,
        method=a.method,
        method_version=a.method_version,
        basis=[BasisItem(**item) for item in a.basis],
        clinical_status=a.clinical_status,
        created_at=a.created_at,
    )


def _level_out(r: LevelRecord) -> LevelRecordOut:
    return LevelRecordOut(
        record_id=r.id,
        level=r.level,
        attempt=r.attempt,
        outcome=r.outcome,
        criterion_met=r.criterion_met,
        started_at=r.started_at,
        ended_at=r.ended_at,
        permanence_seconds=r.permanence_seconds,
        min_distance_m=r.min_distance_m,
        avoidance_count=r.avoidance_count,
        suds=list(r.payload.get("suds") or []),
        payload=r.payload,
    )


# ───────────── progreso y sesiones ─────────────


def progress(db: Session, pseudonym: uuid.UUID) -> ProgressOut:
    sessions = clinical.progress_sessions(db, pseudonym)
    last = sessions[: get_settings().progress_last_sessions]
    analyses = clinical.analyses_for(db, [s.id for s in last], _method())
    reached = [s.level_reached for s in sessions if s.level_reached is not None]
    return ProgressOut(
        sessions_count=len(sessions),
        level_reached=max(reached) if reached else None,
        last_sessions=[
            LastSessionItem(
                session_id=s.id,
                started_at=s.started_at,
                level_reached=s.level_reached,
                total_duration_seconds=s.total_duration_seconds,
                recommendation=analyses[s.id].recommendation if s.id in analyses else None,
            )
            for s in last
        ],
    )


def list_sessions(db: Session, pseudonym: uuid.UUID, page: Page) -> SessionPage:
    rows = clinical.list_sessions(db, pseudonym, page)
    visible = rows[: page.limit]
    analyses = clinical.analyses_for(db, [s.id for s in visible], _method())
    return SessionPage(
        items=[_summary(s, analyses.get(s.id)) for s in visible],
        next_cursor=next_cursor(rows, page, lambda s: (clinical.session_sort_value(s), s.id)),
    )


def session_detail(db: Session, pseudonym: uuid.UUID, session_id: uuid.UUID, *, with_notes: bool) -> SessionDetail:
    s = clinical.get_session(db, pseudonym, session_id)
    if s is None:
        raise _not_found()
    analysis = clinical.analyses_for(db, [s.id], _method()).get(s.id)
    base = _summary(s, analysis).model_dump()
    detail = dict(
        base,
        app_version=s.app_version,
        device_model=s.device_model,
        levels=[_level_out(r) for r in clinical.level_records(db, s.id)],
        analysis=analysis_out(analysis) if analysis else None,
    )
    if with_notes:
        return ProfessionalSessionDetail(**detail, notes=_notes_out(db, clinical.notes_for_session(db, pseudonym, s.id)))
    return SessionDetail(**detail)


def my_patients(db: Session, actor: Actor, page: Page) -> PatientPage:
    rows = identity.list_assignments(db, page, professional_id=actor.user_id)
    visible = rows[: page.limit]
    names = identity.full_names(db, [a.patient_user_id for a in visible])
    items = []
    for a in visible:
        pseudonym = identity.get_pseudonym(db, a.patient_user_id)
        patient = clinical.get_patient(db, pseudonym) if pseudonym else None
        sessions = clinical.progress_sessions(db, pseudonym) if pseudonym else []
        analyses = clinical.analyses_for(db, [s.id for s in sessions], _method())
        last_analyzed = next((analyses[s.id] for s in sessions if s.id in analyses), None)
        reached = [s.level_reached for s in sessions if s.level_reached is not None]
        items.append(
            PatientSummary(
                patient_id=a.patient_user_id,
                full_name=names.get(a.patient_user_id),
                last_session_at=sessions[0].started_at if sessions else None,
                level_reached=max(reached) if reached else None,
                last_recommendation=last_analyzed.recommendation if last_analyzed else None,
                phobia_grade=patient.phobia_grade if patient else None,
            )
        )
    return PatientPage(items=items, next_cursor=next_cursor(rows, page, lambda a: (a.created_at, a.id)))


# ───────────── plan ─────────────


def set_plan(db: Session, patient_id: uuid.UUID, pseudonym: uuid.UUID, level: int) -> PlanOut:
    patient = clinical.get_patient(db, pseudonym)
    if patient is None:
        raise _not_found()
    patient.allowed_start_level = level
    patient.plan_updated_at = utcnow()
    db.commit()
    return PlanOut(patient_id=patient_id, allowed_start_level=patient.allowed_start_level, updated_at=patient.plan_updated_at)


# ───────────── notas ─────────────


def _notes_out(db: Session, notes: list[Note]) -> list[NoteOut]:
    names = identity.full_names(db, list({n.author_user_id for n in notes}))
    return [
        NoteOut(
            note_id=n.id,
            session_id=n.session_id,
            author_id=n.author_user_id,
            author_name=names.get(n.author_user_id),
            text=n.text,
            created_at=n.created_at,
            edited_at=n.edited_at,
        )
        for n in notes
    ]


def list_notes(db: Session, pseudonym: uuid.UUID, page: Page, session_id: uuid.UUID | None = None) -> NotePage:
    rows = clinical.list_notes(db, pseudonym, page, session_id)
    return NotePage(
        items=_notes_out(db, rows[: page.limit]),
        next_cursor=next_cursor(rows, page, lambda n: (n.created_at, n.id)),
    )


def add_note(db: Session, actor: Actor, pseudonym: uuid.UUID, text: str, session_id: uuid.UUID | None) -> NoteCreated:
    if session_id is not None and clinical.get_session(db, pseudonym, session_id) is None:
        raise ApiError(422, "VALIDATION_ERROR", "Revisa los campos marcados.", [{"field": "sessionId", "code": "not_found"}])
    note = clinical.add_note(db, pseudonym_id=pseudonym, session_id=session_id, author_id=actor.user_id, text=text)
    db.commit()
    # "Comentario anotado": confirm by returning the note exactly as it was stored.
    return NoteCreated(**_notes_out(db, [note])[0].model_dump())


def edit_note(db: Session, actor: Actor, pseudonym: uuid.UUID, note_id: uuid.UUID, text: str) -> NoteOut:
    note = clinical.get_note(db, pseudonym, note_id)
    if note is None:
        raise _not_found()
    if note.author_user_id != actor.user_id:
        raise ApiError(403, "FORBIDDEN", "Solo el autor puede editar la nota.")
    note.text = text
    note.edited_at = utcnow()
    db.commit()
    return _notes_out(db, [note])[0]

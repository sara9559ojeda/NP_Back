"""Rutas del profesional sobre sus pacientes asignados (contrato, sección 5.1).

Un paciente no asignado al profesional responde 404, no 403 (contrato, sección 2.3).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import Db, ProfessionalUser
from app.api.docs import problems
from app.core.pagination import Page, page_params
from app.schemas.device import PairingCodeOut
from app.schemas.tracking import (
    FeedbackPage,
    NoteCreated,
    NoteIn,
    NoteOut,
    NotePage,
    NotePatch,
    PatientPage,
    PlanIn,
    PlanOut,
    ProfessionalSessionDetail,
    ProgressOut,
    SessionPage,
)
from app.services import pairing, therapy, tracking

router = APIRouter(prefix="/patients", tags=["patients"])

Pagination = Annotated[Page, Depends(page_params)]
ERRORS = problems(401, 403, 404, 422, 423)


@router.get("", response_model=PatientPage, responses=problems(401, 403, 422, 423), summary="Pacientes asignados")
def list_patients(actor: ProfessionalUser, db: Db, page: Pagination) -> PatientPage:
    return tracking.my_patients(db, actor, page)


@router.get("/{patientId}/progress", response_model=ProgressOut, responses=ERRORS, summary="Progreso de un paciente")
def patient_progress(patientId: uuid.UUID, actor: ProfessionalUser, db: Db) -> ProgressOut:  # noqa: N803
    return tracking.progress(db, tracking.assigned_pseudonym(db, actor, patientId))


@router.get("/{patientId}/sessions", response_model=SessionPage, responses=ERRORS, summary="Sesiones de un paciente")
def patient_sessions(patientId: uuid.UUID, actor: ProfessionalUser, db: Db, page: Pagination) -> SessionPage:  # noqa: N803
    return tracking.list_sessions(db, tracking.assigned_pseudonym(db, actor, patientId), page)


@router.get(
    "/{patientId}/sessions/{sessionId}",
    response_model=ProfessionalSessionDetail,
    responses=ERRORS,
    summary="Detalle de una sesión: registros por nivel, SUDS, análisis y notas",
)
def patient_session(patientId: uuid.UUID, sessionId: uuid.UUID, actor: ProfessionalUser, db: Db):  # noqa: N803
    pseudonym = tracking.assigned_pseudonym(db, actor, patientId)
    return tracking.session_detail(db, pseudonym, sessionId, with_notes=True)


@router.put("/{patientId}/plan", response_model=PlanOut, responses=ERRORS, summary="Nivel inicial permitido (1–5)")
def put_plan(patientId: uuid.UUID, data: PlanIn, actor: ProfessionalUser, db: Db) -> PlanOut:  # noqa: N803
    pseudonym = tracking.assigned_pseudonym(db, actor, patientId)
    return tracking.set_plan(db, patientId, pseudonym, data.allowed_start_level)


@router.get(
    "/{patientId}/notes",
    response_model=NotePage,
    responses=ERRORS,
    summary="Notas, más recientes primero (v1.1.0: filtro opcional ?sessionId=)",
)
def list_notes(
    patientId: uuid.UUID,  # noqa: N803
    actor: ProfessionalUser,
    db: Db,
    page: Pagination,
    sessionId: Annotated[uuid.UUID | None, Query()] = None,  # noqa: N803
) -> NotePage:
    return tracking.list_notes(db, tracking.assigned_pseudonym(db, actor, patientId), page, sessionId)


@router.post(
    "/{patientId}/notes",
    status_code=status.HTTP_201_CREATED,
    response_model=NoteCreated,
    responses=ERRORS,
    summary="Anotar un comentario: valida, guarda y devuelve la nota guardada",
)
def add_note(patientId: uuid.UUID, data: NoteIn, actor: ProfessionalUser, db: Db) -> NoteCreated:  # noqa: N803
    pseudonym = tracking.assigned_pseudonym(db, actor, patientId)
    return tracking.add_note(db, actor, pseudonym, data.text, data.session_id)


@router.patch("/{patientId}/notes/{noteId}", response_model=NoteOut, responses=ERRORS, summary="Editar una nota (solo el autor)")
def edit_note(patientId: uuid.UUID, noteId: uuid.UUID, data: NotePatch, actor: ProfessionalUser, db: Db) -> NoteOut:  # noqa: N803
    pseudonym = tracking.assigned_pseudonym(db, actor, patientId)
    return tracking.edit_note(db, actor, pseudonym, noteId, data.text)


@router.post(
    "/{patientId}/pairing-codes",
    status_code=status.HTTP_201_CREATED,
    response_model=PairingCodeOut,
    responses=ERRORS,
    summary="Código para emparejar el visor de un paciente (profesional, D20)",
    tags=["device"],
)
def create_pairing_code(patientId: uuid.UUID, actor: ProfessionalUser, db: Db) -> PairingCodeOut:  # noqa: N803
    return pairing.create_code(db, tracking.assigned_pseudonym(db, actor, patientId))


@router.get(
    "/{patientId}/feedback",
    response_model=FeedbackPage,
    responses=ERRORS,
    summary="Consultar retroalimentación: análisis de IA por sesión, más recientes primero",
)
def patient_feedback(patientId: uuid.UUID, actor: ProfessionalUser, db: Db, page: Pagination) -> FeedbackPage:  # noqa: N803
    return therapy.feedback_page(db, tracking.assigned_pseudonym(db, actor, patientId), page)

"""Administración: usuarios, roles, asignaciones y exportación anónima (contrato, sección 4.4).

El administrador no ve datos clínicos (D21): ninguna función de aquí devuelve sesiones ni notas
identificadas. La exportación es anónima y usa identificadores nuevos en cada llamada.
"""

import csv
import io
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.pagination import Page, next_cursor
from app.core.security import hash_password, utcnow
from app.repositories import clinical, identity
from app.schemas.accounts import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserPage,
    AdminUserPatch,
    AssignmentOut,
    AssignmentPage,
)
from app.db.models import User
from app.services.accounts import change_email, commit_profile
from app.services.auth import create_account, ensure_patient_link


def _user_out(db: Session, user_id: uuid.UUID) -> AdminUserOut:
    user = identity.get_user(db, user_id)
    if user is None:
        raise ApiError(404, "NOT_FOUND")
    return AdminUserOut(id=user.id, full_name=identity.get_full_name(db, user.id), email=user.email, role=user.role, active=user.active)


def _ensure_not_withdrawn(user: User) -> None:
    if user.withdrawn_at is not None:
        raise ApiError(422, "VALIDATION_ERROR", "La cuenta retiró su consentimiento.", [{"field": "userId", "code": "withdrawn"}])


def get_user(db: Session, user_id: uuid.UUID) -> AdminUserOut:
    return _user_out(db, user_id)


def list_users(db: Session, page: Page, *, role: str | None, active: bool | None, q: str | None) -> AdminUserPage:
    rows = identity.list_users(db, page, role=role, active=active, q=q)
    items = [
        AdminUserOut(id=u.id, full_name=name, email=u.email, role=u.role, active=u.active) for u, name in rows[: page.limit]
    ]
    return AdminUserPage(items=items, next_cursor=next_cursor(rows, page, lambda r: (r[0].created_at, r[0].id)))


def create_user(db: Session, data: AdminUserCreate) -> AdminUserOut:
    user_id = create_account(db, email=data.email, password=data.temporary_password, role=data.role, full_name=data.full_name)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "EMAIL_TAKEN", "Ese correo ya tiene una cuenta.") from exc
    return _user_out(db, user_id)


def patch_user(db: Session, user_id: uuid.UUID, data: AdminUserPatch) -> AdminUserOut:
    identity.lock_admin_changes(db)  # antes del bloqueo de fila: ver LAST_ADMIN
    user = identity.get_user(db, user_id, for_update=True)
    if user is None:
        raise ApiError(404, "NOT_FOUND")
    _ensure_not_withdrawn(user)
    new_role = data.role if data.role is not None else user.role
    new_active = data.active if data.active is not None else user.active
    loses_admin = user.role == "admin" and user.active and (new_role != "admin" or not new_active)
    if loses_admin and identity.count_active_admins(db) <= 1:
        raise ApiError(409, "LAST_ADMIN", "No se puede dejar el sistema sin administradores.")
    now = utcnow()
    if new_role != user.role:
        if user.role in ("patient", "professional"):
            identity.end_assignments_of(db, user.id, now, as_role=user.role)
        if new_role == "patient":
            ensure_patient_link(db, user.id)
        user.role = new_role
    if not new_active and user.active:
        identity.revoke_user_tokens(db, user.id, now)
    user.active = new_active
    if data.email is not None:
        change_email(db, user, data.email, now)
    if data.full_name is not None:
        identity.set_full_name(db, user.id, data.full_name, now)
    user.updated_at = now
    commit_profile(db)
    return _user_out(db, user.id)


def reset_password(db: Session, user_id: uuid.UUID, temporary_password: str) -> None:
    """Set an admin-chosen temporary password and close every web session of that user."""
    user = identity.get_user(db, user_id, for_update=True)
    if user is None:
        raise ApiError(404, "NOT_FOUND")
    _ensure_not_withdrawn(user)
    now = utcnow()
    user.password_hash = hash_password(temporary_password)
    user.updated_at = now
    identity.revoke_user_tokens(db, user.id, now)
    db.commit()


# ───────────── asignaciones ─────────────


def _assignment_out(db: Session, a) -> AssignmentOut:
    names = identity.full_names(db, [a.professional_user_id, a.patient_user_id])
    return AssignmentOut(
        assignment_id=a.id,
        professional_id=a.professional_user_id,
        patient_id=a.patient_user_id,
        professional_name=names.get(a.professional_user_id),
        patient_name=names.get(a.patient_user_id),
        active=a.active,
        created_at=a.created_at,
    )


def list_assignments(db: Session, page: Page, professional_id: uuid.UUID | None) -> AssignmentPage:
    rows = identity.list_assignments(db, page, professional_id=professional_id)
    visible = rows[: page.limit]
    names = identity.full_names(db, list({x for a in visible for x in (a.professional_user_id, a.patient_user_id)}))
    items = [
        AssignmentOut(
            assignment_id=a.id,
            professional_id=a.professional_user_id,
            patient_id=a.patient_user_id,
            professional_name=names.get(a.professional_user_id),
            patient_name=names.get(a.patient_user_id),
            active=a.active,
            created_at=a.created_at,
        )
        for a in visible
    ]
    return AssignmentPage(items=items, next_cursor=next_cursor(rows, page, lambda a: (a.created_at, a.id)))


def create_assignment(db: Session, professional_id: uuid.UUID, patient_id: uuid.UUID) -> tuple[AssignmentOut, bool]:
    """Devuelve la asignación y si es nueva. Si ya existía activa, se devuelve la misma."""
    errors = []
    professional = identity.get_user(db, professional_id)
    if professional is None or professional.role != "professional" or not professional.active:
        errors.append({"field": "professionalId", "code": "not_professional"})
    patient = identity.get_user(db, patient_id)
    if patient is None or patient.role != "patient" or not patient.active:
        errors.append({"field": "patientId", "code": "not_patient"})
    if errors:
        raise ApiError(422, "VALIDATION_ERROR", "Revisa los campos marcados.", errors)
    existing = identity.find_active_assignment(db, professional_id, patient_id)
    if existing is not None:
        return _assignment_out(db, existing), False
    assignment = identity.add_assignment(db, professional_id, patient_id)
    db.commit()
    return _assignment_out(db, assignment), True


def delete_assignment(db: Session, assignment_id: uuid.UUID) -> None:
    assignment = identity.get_assignment(db, assignment_id)
    if assignment is None:
        raise ApiError(404, "NOT_FOUND")
    assignment.active = False
    assignment.ended_at = utcnow()
    db.commit()


# ───────────── exportación anónima ─────────────

EXPORT_COLUMNS = [
    "subjectKey",
    "sessionKey",
    "sessionIndex",
    "phobiaGrade",
    "deviceModel",
    "endReason",
    "sessionLevelReached",
    "totalDurationSeconds",
    "level",
    "attempt",
    "outcome",
    "criterionMet",
    "levelDurationSeconds",
    "permanenceSeconds",
    "minDistanceM",
    "gazeConeDeg",
    "gazeOnStimulusSeconds",
    "gazeMeanAngleDeg",
    "avoidanceCount",
    "sudsBefore",
    "sudsDuringMax",
    "sudsAfter",
    "toleranceIndex",
    "recommendation",
    "analysisMethod",
    "analysisMethodVersion",
]


def analysis_dataset(db: Session) -> dict[str, Any]:
    """Una fila por registro de nivel (o por sesión, si no tiene registros).

    - Sin ``pseudonym_id`` ni ids de sesión o dispositivo: claves aleatorias nuevas en cada exportación.
    - Sin fechas absolutas, notas ni texto libre.
    - Sin sesiones de prueba (``testSession = true``) ni sesiones cuyo inicio no ha llegado.
    """
    method = get_settings().ai_method
    subject_keys: dict[uuid.UUID, str] = {}
    session_keys: dict[uuid.UUID, tuple[str, int]] = {}
    per_subject_count: dict[uuid.UUID, int] = {}
    rows: list[dict[str, Any]] = []
    for session, record, analysis in clinical.export_rows(db, method):
        subject = subject_keys.setdefault(session.pseudonym_id, str(uuid.uuid4()))
        if session.id not in session_keys:
            per_subject_count[session.pseudonym_id] = per_subject_count.get(session.pseudonym_id, 0) + 1
            session_keys[session.id] = (str(uuid.uuid4()), per_subject_count[session.pseudonym_id])
        session_key, session_index = session_keys[session.id]
        row: dict[str, Any] = dict.fromkeys(EXPORT_COLUMNS)
        row.update(
            subjectKey=subject,
            sessionKey=session_key,
            sessionIndex=session_index,
            phobiaGrade=session.phobia_grade,
            deviceModel=session.device_model,
            endReason=session.end_reason,
            sessionLevelReached=session.level_reached,
            totalDurationSeconds=session.total_duration_seconds,
        )
        if analysis is not None:
            row.update(
                toleranceIndex=analysis.tolerance_index,
                recommendation=analysis.recommendation,
                analysisMethod=analysis.method,
                analysisMethodVersion=analysis.method_version,
            )
        if record is not None:
            payload = record.payload
            gaze = payload.get("gaze") or {}
            suds = payload.get("suds") or []
            before = [s["value"] for s in suds if s.get("phase") == "before"]
            during = [s["value"] for s in suds if s.get("phase") == "during"]
            after = [s["value"] for s in suds if s.get("phase") == "after"]
            row.update(
                level=record.level,
                attempt=record.attempt,
                outcome=record.outcome,
                criterionMet=record.criterion_met,
                levelDurationSeconds=round((record.ended_at - record.started_at).total_seconds(), 3),
                permanenceSeconds=record.permanence_seconds,
                minDistanceM=record.min_distance_m,
                gazeConeDeg=gaze.get("coneDeg"),
                gazeOnStimulusSeconds=gaze.get("onStimulusSeconds"),
                gazeMeanAngleDeg=gaze.get("meanAngleDeg"),
                avoidanceCount=record.avoidance_count,
                sudsBefore=before[0] if before else None,
                sudsDuringMax=max(during) if during else None,
                sudsAfter=after[-1] if after else None,
            )
        rows.append(row)
    return {
        "exportId": str(uuid.uuid4()),
        "generatedAt": utcnow().isoformat(timespec="seconds").replace("+00:00", "Z"),
        "columns": EXPORT_COLUMNS,
        "rows": rows,
    }


def dataset_to_csv(dataset: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in dataset["rows"]:
        writer.writerow({k: "" if v is None else v for k, v in row.items()})
    return buffer.getvalue()

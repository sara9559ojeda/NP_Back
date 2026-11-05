"""Acceso a datos del esquema ``clinical``. Aquí solo existen seudónimos, nunca identidades."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.pagination import Page
from app.db.models import (
    Analysis,
    Device,
    InboundRecord,
    LevelRecord,
    Note,
    PairingCode,
    Patient,
    TherapySession,
)

# ───────────── pacientes ─────────────


def add_patient(db: Session) -> uuid.UUID:
    patient = Patient(pseudonym_id=uuid.uuid4(), allowed_start_level=1)
    db.add(patient)
    db.flush()
    return patient.pseudonym_id


def get_patient(db: Session, pseudonym_id: uuid.UUID) -> Patient | None:
    return db.get(Patient, pseudonym_id)


# ───────────── códigos de emparejamiento ─────────────


def invalidate_pairing_codes(db: Session, pseudonym_id: uuid.UUID) -> None:
    db.execute(delete(PairingCode).where(PairingCode.pseudonym_id == pseudonym_id, PairingCode.used_at.is_(None)))


def add_pairing_code(db: Session, pseudonym_id: uuid.UUID, code_hash: str, expires_at: datetime) -> None:
    db.add(PairingCode(id=uuid.uuid4(), pseudonym_id=pseudonym_id, code_hash=code_hash, expires_at=expires_at))


def get_pairing_code(db: Session, code_hash: str) -> PairingCode | None:
    return db.scalars(select(PairingCode).where(PairingCode.code_hash == code_hash).with_for_update()).first()


# ───────────── dispositivos ─────────────


def add_device(db: Session, *, pseudonym_id: uuid.UUID, model: str, app_version: str, token_hash: str) -> Device:
    device = Device(id=uuid.uuid4(), pseudonym_id=pseudonym_id, model=model, app_version=app_version, token_hash=token_hash)
    db.add(device)
    db.flush()
    db.refresh(device)
    return device


def get_device_by_token_hash(db: Session, token_hash: str) -> Device | None:
    return db.scalars(select(Device).where(Device.token_hash == token_hash)).first()


def list_devices(db: Session, pseudonym_id: uuid.UUID) -> list[Device]:
    return list(db.scalars(select(Device).where(Device.pseudonym_id == pseudonym_id).order_by(Device.paired_at.desc())))


def get_device(db: Session, device_id: uuid.UUID, pseudonym_id: uuid.UUID) -> Device | None:
    return db.scalars(select(Device).where(Device.id == device_id, Device.pseudonym_id == pseudonym_id)).first()


def revoke_devices(db: Session, pseudonym_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(Device).where(Device.pseudonym_id == pseudonym_id, Device.revoked_at.is_(None)).values(revoked_at=now)
    )


# ───────────── sesiones y registros ─────────────


def get_inbound(db: Session, record_id: uuid.UUID) -> InboundRecord | None:
    return db.get(InboundRecord, record_id)


def try_add_inbound(db: Session, **values: Any) -> bool:
    """Inserta en el libro de entrada; ``False`` si el ``recordId`` ya existía (carrera entre envíos)."""
    stmt = (
        insert(InboundRecord)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["record_id"])
        .returning(InboundRecord.record_id)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def lock_or_create_session(db: Session, session_id: uuid.UUID, pseudonym_id: uuid.UUID, device_id: uuid.UUID) -> TherapySession:
    db.execute(
        insert(TherapySession)
        .values(id=session_id, pseudonym_id=pseudonym_id, device_id=device_id, raw={}, has_start=False, has_end=False)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    return db.scalars(select(TherapySession).where(TherapySession.id == session_id).with_for_update()).one()


def get_session(db: Session, pseudonym_id: uuid.UUID, session_id: uuid.UUID) -> TherapySession | None:
    return db.scalars(
        select(TherapySession).where(TherapySession.id == session_id, TherapySession.pseudonym_id == pseudonym_id)
    ).first()


def _session_sort_key():
    return func.coalesce(TherapySession.started_at, TherapySession.created_at)


def list_sessions(db: Session, pseudonym_id: uuid.UUID, page: Page) -> list[TherapySession]:
    sort = _session_sort_key()
    stmt = select(TherapySession).where(TherapySession.pseudonym_id == pseudonym_id)
    if page.after:
        at, last_id = page.after
        stmt = stmt.where(or_(sort < at, and_(sort == at, TherapySession.id < last_id)))
    stmt = stmt.order_by(sort.desc(), TherapySession.id.desc()).limit(page.limit + 1)
    return list(db.scalars(stmt))


def session_sort_value(session: TherapySession) -> datetime:
    return session.started_at or session.created_at


def progress_sessions(db: Session, pseudonym_id: uuid.UUID) -> list[TherapySession]:
    """Sesiones que cuentan para el progreso: con inicio conocido y sin ``testSession`` (D17)."""
    stmt = (
        select(TherapySession)
        .where(
            TherapySession.pseudonym_id == pseudonym_id,
            TherapySession.has_start.is_(True),
            TherapySession.test_session.is_(False),
        )
        .order_by(TherapySession.started_at.desc(), TherapySession.id.desc())
    )
    return list(db.scalars(stmt))


def add_level_record(db: Session, record: LevelRecord) -> None:
    db.add(record)


def level_records(db: Session, session_id: uuid.UUID) -> list[LevelRecord]:
    stmt = select(LevelRecord).where(LevelRecord.session_id == session_id).order_by(
        LevelRecord.started_at, LevelRecord.level, LevelRecord.attempt
    )
    return list(db.scalars(stmt))


def analyses_for(db: Session, session_ids: list[uuid.UUID], method: str) -> dict[uuid.UUID, Analysis]:
    if not session_ids:
        return {}
    stmt = select(Analysis).where(Analysis.session_id.in_(session_ids), Analysis.method == method)
    return {a.session_id: a for a in db.scalars(stmt)}


def upsert_analysis(db: Session, values: dict[str, Any]) -> None:
    stmt = insert(Analysis).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["session_id", "method"],
        set_={k: stmt.excluded[k] for k in ("method_version", "tolerance_index", "recommendation", "basis", "clinical_status", "created_at")},
    )
    db.execute(stmt)


def delete_analysis(db: Session, session_id: uuid.UUID, method: str) -> None:
    db.execute(delete(Analysis).where(Analysis.session_id == session_id, Analysis.method == method))


# ───────────── notas ─────────────


def add_note(db: Session, *, pseudonym_id: uuid.UUID, session_id: uuid.UUID | None, author_id: uuid.UUID, text: str) -> Note:
    note = Note(id=uuid.uuid4(), pseudonym_id=pseudonym_id, session_id=session_id, author_user_id=author_id, text=text)
    db.add(note)
    db.flush()
    db.refresh(note)
    return note


def get_note(db: Session, pseudonym_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
    return db.scalars(select(Note).where(Note.id == note_id, Note.pseudonym_id == pseudonym_id).with_for_update()).first()


def list_notes(db: Session, pseudonym_id: uuid.UUID, page: Page, session_id: uuid.UUID | None = None) -> list[Note]:
    stmt = select(Note).where(Note.pseudonym_id == pseudonym_id)
    if session_id is not None:
        stmt = stmt.where(Note.session_id == session_id)
    if page.after:
        at, last_id = page.after
        stmt = stmt.where(or_(Note.created_at < at, and_(Note.created_at == at, Note.id < last_id)))
    stmt = stmt.order_by(Note.created_at.desc(), Note.id.desc()).limit(page.limit + 1)
    return list(db.scalars(stmt))


def notes_for_session(db: Session, pseudonym_id: uuid.UUID, session_id: uuid.UUID) -> list[Note]:
    stmt = (
        select(Note)
        .where(Note.pseudonym_id == pseudonym_id, Note.session_id == session_id)
        .order_by(Note.created_at.desc(), Note.id.desc())
    )
    return list(db.scalars(stmt))


def notes_count_by_session(db: Session, pseudonym_id: uuid.UUID, session_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not session_ids:
        return {}
    stmt = (
        select(Note.session_id, func.count())
        .where(Note.pseudonym_id == pseudonym_id, Note.session_id.in_(session_ids))
        .group_by(Note.session_id)
    )
    return {sid: n for sid, n in db.execute(stmt)}


# ───────────── therapy state and feedback (v1.1.0) ─────────────


def count_level_records(db: Session, session_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(LevelRecord).where(LevelRecord.session_id == session_id)) or 0


def count_active_devices(db: Session, pseudonym_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Device).where(Device.pseudonym_id == pseudonym_id, Device.revoked_at.is_(None))
    return db.scalar(stmt) or 0


def open_session(db: Session, pseudonym_id: uuid.UUID) -> TherapySession | None:
    """Latest started session that has not ended yet (the therapy in progress, if any)."""
    stmt = (
        select(TherapySession)
        .where(
            TherapySession.pseudonym_id == pseudonym_id,
            TherapySession.has_start.is_(True),
            TherapySession.has_end.is_(False),
        )
        .order_by(TherapySession.started_at.desc(), TherapySession.id.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def feedback_sessions(db: Session, pseudonym_id: uuid.UUID, method: str, page: Page) -> list[tuple[TherapySession, Analysis]]:
    """Sessions with stored feedback, newest first (returns at most ``limit + 1`` rows)."""
    stmt = (
        select(TherapySession, Analysis)
        .join(Analysis, and_(Analysis.session_id == TherapySession.id, Analysis.method == method))
        .where(TherapySession.pseudonym_id == pseudonym_id, TherapySession.started_at.is_not(None))
    )
    if page.after:
        at, last_id = page.after
        stmt = stmt.where(
            or_(TherapySession.started_at < at, and_(TherapySession.started_at == at, TherapySession.id < last_id))
        )
    stmt = stmt.order_by(TherapySession.started_at.desc(), TherapySession.id.desc()).limit(page.limit + 1)
    return [(row[0], row[1]) for row in db.execute(stmt)]


# ───────────── exportación anónima ─────────────


def export_rows(db: Session, method: str) -> list[tuple[TherapySession, LevelRecord | None, Analysis | None]]:
    """Sesiones con inicio conocido y sin ``testSession``, con sus registros de nivel y su análisis."""
    stmt = (
        select(TherapySession, LevelRecord, Analysis)
        .outerjoin(LevelRecord, LevelRecord.session_id == TherapySession.id)
        .outerjoin(Analysis, and_(Analysis.session_id == TherapySession.id, Analysis.method == method))
        .where(TherapySession.has_start.is_(True), TherapySession.test_session.is_(False))
        .order_by(TherapySession.pseudonym_id, TherapySession.started_at, LevelRecord.started_at, LevelRecord.level)
    )
    return [(row[0], row[1], row[2]) for row in db.execute(stmt)]

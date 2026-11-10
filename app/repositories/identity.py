"""Acceso a datos del esquema ``identity``."""

import uuid
from datetime import datetime

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.orm import Session

from app.core.pagination import Page
from app.db.models import Assignment, Consent, IdentityLink, PersonalData, RefreshToken, User


def get_user(db: Session, user_id: uuid.UUID, *, for_update: bool = False) -> User | None:
    stmt = select(User).where(User.id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalars(stmt).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email)).first()


def email_exists(db: Session, email: str, *, exclude_user: uuid.UUID | None = None) -> bool:
    stmt = select(User.id).where(User.email == email)
    if exclude_user is not None:
        stmt = stmt.where(User.id != exclude_user)
    return db.scalars(stmt).first() is not None


def add_user(db: Session, *, email: str, password_hash: str, role: str, full_name: str) -> User:
    user = User(id=uuid.uuid4(), email=email, password_hash=password_hash, role=role, active=True)
    db.add(user)
    db.flush()
    db.add(PersonalData(user_id=user.id, full_name=full_name))
    return user


def get_full_name(db: Session, user_id: uuid.UUID) -> str | None:
    return db.scalars(select(PersonalData.full_name).where(PersonalData.user_id == user_id)).first()


def full_names(db: Session, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    rows = db.execute(select(PersonalData.user_id, PersonalData.full_name).where(PersonalData.user_id.in_(user_ids)))
    return {row.user_id: row.full_name for row in rows}


def set_full_name(db: Session, user_id: uuid.UUID, full_name: str, now: datetime) -> None:
    data = db.get(PersonalData, user_id)
    if data is None:
        db.add(PersonalData(user_id=user_id, full_name=full_name, updated_at=now))
    else:
        data.full_name = full_name
        data.updated_at = now


def delete_personal_data(db: Session, user_id: uuid.UUID) -> None:
    db.execute(delete(PersonalData).where(PersonalData.user_id == user_id))


# ───────────── consentimientos ─────────────


def add_consent(db: Session, user_id: uuid.UUID, version: str, granted_at: datetime) -> None:
    db.add(Consent(id=uuid.uuid4(), user_id=user_id, consent_version=version, granted_at=granted_at))


def list_consents(db: Session, user_id: uuid.UUID) -> list[Consent]:
    return list(db.scalars(select(Consent).where(Consent.user_id == user_id).order_by(Consent.granted_at)))


def withdraw_consents(db: Session, user_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(Consent).where(Consent.user_id == user_id, Consent.withdrawn_at.is_(None)).values(withdrawn_at=now)
    )


# ───────────── vínculo identidad ↔ seudónimo ─────────────


def get_pseudonym(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalars(select(IdentityLink.pseudonym_id).where(IdentityLink.user_id == user_id)).first()


def get_user_id_for_pseudonym(db: Session, pseudonym_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalars(select(IdentityLink.user_id).where(IdentityLink.pseudonym_id == pseudonym_id)).first()


def add_link(db: Session, user_id: uuid.UUID, pseudonym_id: uuid.UUID) -> None:
    db.add(IdentityLink(user_id=user_id, pseudonym_id=pseudonym_id))


def delete_link(db: Session, user_id: uuid.UUID) -> None:
    db.execute(delete(IdentityLink).where(IdentityLink.user_id == user_id))


# ───────────── usuarios (administración) ─────────────


def list_users(
    db: Session, page: Page, *, role: str | None, active: bool | None, q: str | None
) -> list[tuple[User, str | None]]:
    stmt = select(User, PersonalData.full_name).outerjoin(PersonalData, PersonalData.user_id == User.id)
    if role:
        stmt = stmt.where(User.role == role)
    if active is not None:
        stmt = stmt.where(User.active == active)
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(User.email.ilike(pattern, escape="\\"), PersonalData.full_name.ilike(pattern, escape="\\")))
    if page.after:
        at, last_id = page.after
        stmt = stmt.where(or_(User.created_at < at, and_(User.created_at == at, User.id < last_id)))
    stmt = stmt.order_by(User.created_at.desc(), User.id.desc()).limit(page.limit + 1)
    return [(row[0], row[1]) for row in db.execute(stmt)]


# Clave fija del bloqueo consultivo que serializa los cambios sobre administradores (64 bits con signo).
_ADMIN_CHANGES_LOCK = 0x4E50_4144_4D49_4E53  # "NPADMINS"


def lock_admin_changes(db: Session) -> None:
    """Bloqueo de transacción: dos cambios simultáneos no pueden ver ambos «quedan 2 administradores».

    Se toma antes de bloquear filas de usuario, siempre en el mismo orden, para no crear interbloqueos.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADMIN_CHANGES_LOCK})


def count_active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.active.is_(True))) or 0


# ───────────── asignaciones ─────────────


def get_assignment(db: Session, assignment_id: uuid.UUID) -> Assignment | None:
    return db.scalars(select(Assignment).where(Assignment.id == assignment_id, Assignment.active.is_(True))).first()


def find_active_assignment(db: Session, professional_id: uuid.UUID, patient_id: uuid.UUID) -> Assignment | None:
    return db.scalars(
        select(Assignment).where(
            Assignment.professional_user_id == professional_id,
            Assignment.patient_user_id == patient_id,
            Assignment.active.is_(True),
        )
    ).first()


def add_assignment(db: Session, professional_id: uuid.UUID, patient_id: uuid.UUID) -> Assignment:
    assignment = Assignment(id=uuid.uuid4(), professional_user_id=professional_id, patient_user_id=patient_id, active=True)
    db.add(assignment)
    db.flush()
    db.refresh(assignment)
    return assignment


def list_assignments(db: Session, page: Page, *, professional_id: uuid.UUID | None) -> list[Assignment]:
    stmt = select(Assignment).where(Assignment.active.is_(True))
    if professional_id:
        stmt = stmt.where(Assignment.professional_user_id == professional_id)
    if page.after:
        at, last_id = page.after
        stmt = stmt.where(or_(Assignment.created_at < at, and_(Assignment.created_at == at, Assignment.id < last_id)))
    stmt = stmt.order_by(Assignment.created_at.desc(), Assignment.id.desc()).limit(page.limit + 1)
    return list(db.scalars(stmt))


def end_assignments_of(db: Session, user_id: uuid.UUID, now: datetime, *, as_role: str) -> None:
    column = Assignment.patient_user_id if as_role == "patient" else Assignment.professional_user_id
    db.execute(update(Assignment).where(column == user_id, Assignment.active.is_(True)).values(active=False, ended_at=now))


def assigned_patient_ids(db: Session, professional_id: uuid.UUID) -> list[uuid.UUID]:
    stmt = select(Assignment.patient_user_id).where(
        Assignment.professional_user_id == professional_id, Assignment.active.is_(True)
    )
    return list(db.scalars(stmt))


def is_assigned(db: Session, professional_id: uuid.UUID, patient_id: uuid.UUID) -> bool:
    return find_active_assignment(db, professional_id, patient_id) is not None


# ───────────── tokens de refresco ─────────────


def add_refresh_token(
    db: Session, *, user_id: uuid.UUID, family_id: uuid.UUID, token_hash: str, expires_at: datetime
) -> None:
    db.add(RefreshToken(id=uuid.uuid4(), user_id=user_id, family_id=family_id, token_hash=token_hash, expires_at=expires_at))


def get_refresh_token(db: Session, token_hash: str) -> RefreshToken | None:
    return db.scalars(select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()).first()


def revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now)
    )


def revoke_user_tokens(db: Session, user_id: uuid.UUID, now: datetime, *, keep_family: uuid.UUID | None = None) -> None:
    stmt = update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    if keep_family is not None:
        stmt = stmt.where(RefreshToken.family_id != keep_family)
    db.execute(stmt.values(revoked_at=now))

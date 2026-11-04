"""Datos propios y retirada del consentimiento (contrato, secciones 3 y 4.3)."""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, field_error
from app.core.security import hash_password, utcnow, verify_password
from app.repositories import clinical, identity
from app.schemas.accounts import ConsentOut, MeOut, MePatch
from app.services.actor import Actor


def get_me(db: Session, actor: Actor) -> MeOut:
    user = identity.get_user(db, actor.user_id)
    if user is None:
        raise ApiError(401, "UNAUTHENTICATED")
    consents = [
        ConsentOut(consent_id=c.id, consent_version=c.consent_version, granted_at=c.granted_at, withdrawn_at=c.withdrawn_at)
        for c in identity.list_consents(db, user.id)
    ]
    return MeOut(id=user.id, role=user.role, full_name=identity.get_full_name(db, user.id), email=user.email, consents=consents)


def patch_me(db: Session, actor: Actor, data: MePatch) -> MeOut:
    user = identity.get_user(db, actor.user_id, for_update=True)
    if user is None:
        raise ApiError(401, "UNAUTHENTICATED")
    now = utcnow()
    if data.email is not None and data.email != user.email:
        if identity.email_exists(db, data.email, exclude_user=user.id):
            raise ApiError(409, "EMAIL_TAKEN", "Ese correo ya tiene una cuenta.")
        user.email = data.email
        user.updated_at = now
    if data.full_name is not None:
        identity.set_full_name(db, user.id, data.full_name, now)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "EMAIL_TAKEN", "Ese correo ya tiene una cuenta.") from exc
    return get_me(db, actor)


def change_password(
    db: Session, actor: Actor, current: str, new: str, *, keep_family: uuid.UUID | None
) -> None:
    user = identity.get_user(db, actor.user_id, for_update=True)
    if user is None:
        raise ApiError(401, "UNAUTHENTICATED")
    if not verify_password(user.password_hash, current):
        raise field_error("currentPassword", "incorrect", "La contraseña actual no es correcta.")
    now = utcnow()
    user.password_hash = hash_password(new)
    user.updated_at = now
    # Las demás sesiones web se cierran; la actual se conserva.
    identity.revoke_user_tokens(db, user.id, now, keep_family=keep_family)
    db.commit()


def withdraw_consent(db: Session, actor: Actor) -> None:
    """Borra la identidad personal y rompe el vínculo con el seudónimo.

    Los datos clínicos se conservan sin vínculo (anónimos); su plazo depende de D23.
    """
    user = identity.get_user(db, actor.user_id, for_update=True)
    if user is None:
        raise ApiError(401, "UNAUTHENTICATED")
    if user.role == "admin" and user.active and identity.count_active_admins(db) <= 1:
        raise ApiError(409, "LAST_ADMIN", "No se puede dejar el sistema sin administradores.")
    now = utcnow()
    pseudonym = identity.get_pseudonym(db, user.id)
    if pseudonym is not None:
        clinical.revoke_devices(db, pseudonym, now)
        clinical.invalidate_pairing_codes(db, pseudonym)
    identity.withdraw_consents(db, user.id, now)
    identity.delete_personal_data(db, user.id)
    identity.delete_link(db, user.id)
    identity.end_assignments_of(db, user.id, now, as_role=user.role)
    identity.revoke_user_tokens(db, user.id, now)
    # El correo también es un dato personal: se sustituye por un marcador sin significado.
    user.email = f"retirado-{uuid.uuid4()}@invalid"
    user.password_hash = None
    user.active = False
    user.withdrawn_at = now
    user.updated_at = now
    db.commit()

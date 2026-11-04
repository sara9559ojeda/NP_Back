"""Registro, inicio y cierre de sesión, refresco rotativo (contrato, secciones 2.2, 4.1 y 4.2)."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.ratelimit import limiter
from app.core.security import (
    create_access_token,
    hash_password,
    new_opaque_token,
    sha256_hex,
    utcnow,
    verify_password,
)
from app.repositories import clinical, identity
from app.schemas.accounts import RegisterIn


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    user_id: uuid.UUID
    role: str


def create_account(db: Session, *, email: str, password: str, role: str, full_name: str) -> uuid.UUID:
    """Crea la identidad y, si es paciente, su seudónimo clínico. No hace commit."""
    if identity.email_exists(db, email):
        raise ApiError(409, "EMAIL_TAKEN", "Ese correo ya tiene una cuenta.")
    user = identity.add_user(db, email=email, password_hash=hash_password(password), role=role, full_name=full_name)
    if role == "patient":
        ensure_patient_link(db, user.id)
    return user.id


def ensure_patient_link(db: Session, user_id: uuid.UUID) -> uuid.UUID:
    pseudonym = identity.get_pseudonym(db, user_id)
    if pseudonym is None:
        pseudonym = clinical.add_patient(db)
        identity.add_link(db, user_id, pseudonym)
    return pseudonym


def register(db: Session, data: RegisterIn, client_ip: str) -> uuid.UUID:
    settings = get_settings()
    limiter.check_and_hit(limiter.key("register", client_ip), settings.register_max_per_window, settings.register_window_seconds)
    if data.consent is None or data.consent.accepted is not True:
        raise ApiError(422, "CONSENT_REQUIRED", "Hay que aceptar el tratamiento de datos.", [{"field": "consent.accepted", "code": "required"}])
    # D18 (opción A): el autorregistro queda como paciente sin profesional asignado.
    user_id = create_account(db, email=data.email, password=data.password, role="patient", full_name=data.full_name)
    identity.add_consent(db, user_id, data.consent.consent_version, utcnow())
    try:
        db.commit()
    except IntegrityError as exc:  # dos registros simultáneos con el mismo correo
        db.rollback()
        raise ApiError(409, "EMAIL_TAKEN", "Ese correo ya tiene una cuenta.") from exc
    return user_id


def _issue(db: Session, user_id: uuid.UUID, role: str, family_id: uuid.UUID | None = None) -> IssuedTokens:
    settings = get_settings()
    access_token, expires_in = create_access_token(user_id, role)
    refresh_token = new_opaque_token("npr")
    identity.add_refresh_token(
        db,
        user_id=user_id,
        family_id=family_id or uuid.uuid4(),
        token_hash=sha256_hex(refresh_token),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
    )
    return IssuedTokens(access_token, expires_in, refresh_token, user_id, role)


def login(db: Session, email: str, password: str, client_ip: str) -> IssuedTokens:
    settings = get_settings()
    limiter.check_and_hit(limiter.key("login", client_ip), settings.login_max_per_window, settings.login_window_seconds)
    user = identity.get_user_by_email(db, email.strip().lower())
    # verify_password usa un hash ficticio si el usuario no existe: mismo tiempo de respuesta.
    if not verify_password(user.password_hash if user else None, password) or user is None:
        raise ApiError(401, "INVALID_CREDENTIALS", "Correo o contraseña incorrectos.")
    if not user.active:
        raise ApiError(423, "ACCOUNT_DISABLED", "La cuenta está desactivada.")
    tokens = _issue(db, user.id, user.role)
    db.commit()
    return tokens


def refresh(db: Session, refresh_token: str | None) -> IssuedTokens:
    if not refresh_token:
        raise ApiError(401, "UNAUTHENTICATED", "Falta la sesión.")
    now = utcnow()
    stored = identity.get_refresh_token(db, sha256_hex(refresh_token))
    if stored is None:
        raise ApiError(401, "UNAUTHENTICATED", "La sesión no es válida.")
    if stored.revoked_at is not None:
        # Reutilización de un token ya rotado: se revoca toda la familia (posible robo).
        identity.revoke_family(db, stored.family_id, now)
        db.commit()
        raise ApiError(401, "UNAUTHENTICATED", "La sesión no es válida.")
    if stored.expires_at <= now:
        raise ApiError(401, "TOKEN_EXPIRED", "La sesión ha caducado.")
    user = identity.get_user(db, stored.user_id)
    if user is None or not user.active:
        identity.revoke_family(db, stored.family_id, now)
        db.commit()
        raise ApiError(423, "ACCOUNT_DISABLED", "La cuenta está desactivada.")
    stored.revoked_at = now
    tokens = _issue(db, user.id, user.role, family_id=stored.family_id)
    db.commit()
    return tokens


def logout(db: Session, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    stored = identity.get_refresh_token(db, sha256_hex(refresh_token))
    if stored is not None:
        identity.revoke_family(db, stored.family_id, utcnow())
        db.commit()

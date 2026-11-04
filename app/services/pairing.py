"""Emparejamiento y revocación del visor (contrato, sección 6.1; D15 y D20)."""

import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.ratelimit import limiter
from app.core.security import keyed_hash, new_opaque_token, new_pairing_code, normalize_pairing_code, sha256_hex, utcnow
from app.repositories import clinical, identity
from app.schemas.device import DeviceOut, DevicePage, PairingCodeOut, PairIn, PairOut
from app.services.actor import DeviceActor

_CODE_LABEL = "pairing-code"


def create_code(db: Session, pseudonym: uuid.UUID) -> PairingCodeOut:
    """Código de 6 caracteres, válido 10 minutos y de un solo uso. Anula los anteriores sin usar."""
    expires_at = utcnow() + timedelta(minutes=get_settings().pairing_code_minutes)
    clinical.invalidate_pairing_codes(db, pseudonym)
    for _ in range(5):
        code = new_pairing_code()
        try:
            with db.begin_nested():
                clinical.add_pairing_code(db, pseudonym, keyed_hash(normalize_pairing_code(code), _CODE_LABEL), expires_at)
            break
        except IntegrityError:  # colisión improbable con otro código vigente
            continue
    else:
        raise ApiError(500, "SERVER_ERROR")
    db.commit()
    return PairingCodeOut(code=code, expires_at=expires_at)


def pair(db: Session, data: PairIn, client_ip: str) -> PairOut:
    settings = get_settings()
    key = limiter.key("pair-fail", client_ip)
    window = settings.pairing_failure_window_seconds
    limiter.ensure_below(key, settings.pairing_max_failures, window)

    stored = clinical.get_pairing_code(db, keyed_hash(normalize_pairing_code(data.code), _CODE_LABEL))
    now = utcnow()
    if stored is None:
        limiter.hit(key, window)
        raise ApiError(404, "PAIRING_CODE_INVALID", "El código no existe.")
    if stored.used_at is not None or stored.expires_at <= now:
        limiter.hit(key, window)
        raise ApiError(410, "PAIRING_CODE_EXPIRED", "El código ha caducado o ya se usó.")
    user_id = identity.get_user_id_for_pseudonym(db, stored.pseudonym_id)
    user = identity.get_user(db, user_id) if user_id else None
    if user is None or not user.active:
        limiter.hit(key, window)
        raise ApiError(410, "PAIRING_CODE_EXPIRED", "El código ha caducado o ya se usó.")

    stored.used_at = now
    token = new_opaque_token("npd")
    device = clinical.add_device(
        db, pseudonym_id=stored.pseudonym_id, model=data.device_model, app_version=data.app_version, token_hash=sha256_hex(token)
    )
    db.commit()
    return PairOut(device_id=device.id, device_token=token)


def authenticate_device(db: Session, token: str) -> DeviceActor:
    device = clinical.get_device_by_token_hash(db, sha256_hex(token))
    if device is None:
        raise ApiError(401, "UNAUTHENTICATED", "Token de dispositivo no válido.")
    if device.revoked_at is not None:
        raise ApiError(401, "DEVICE_REVOKED", "Este visor fue desvinculado. Hay que emparejarlo de nuevo.")
    user_id = identity.get_user_id_for_pseudonym(db, device.pseudonym_id)
    user = identity.get_user(db, user_id) if user_id else None
    if user is None or not user.active:
        # Cuenta desactivada o consentimiento retirado: el visor deja de poder enviar y conserva sus datos.
        raise ApiError(401, "DEVICE_REVOKED", "Este visor ya no está vinculado a una cuenta activa.")
    device.last_seen_at = utcnow()
    return DeviceActor(device_id=device.id, pseudonym_id=device.pseudonym_id)


def _device_out(d) -> DeviceOut:
    return DeviceOut(
        device_id=d.id,
        device_model=d.model,
        app_version=d.app_version,
        paired_at=d.paired_at,
        last_seen_at=d.last_seen_at,
        revoked_at=d.revoked_at,
    )


def list_devices(db: Session, pseudonym: uuid.UUID) -> DevicePage:
    return DevicePage(items=[_device_out(d) for d in clinical.list_devices(db, pseudonym)], next_cursor=None)


def revoke_device(db: Session, pseudonym: uuid.UUID, device_id: uuid.UUID) -> None:
    device = clinical.get_device(db, device_id, pseudonym)
    if device is None:
        raise ApiError(404, "NOT_FOUND")
    if device.revoked_at is None:
        device.revoked_at = utcnow()
    db.commit()

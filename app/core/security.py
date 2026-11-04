"""Contraseñas (Argon2id), JWT de acceso y tokens opacos."""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

# argon2-cffi usa Argon2id por defecto (RFC 9106, perfil recomendado de baja memoria).
_hasher = PasswordHasher()
# Hash ficticio para igualar el tiempo de respuesta cuando el correo no existe.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

JWT_ALGORITHM = "HS256"

# Alfabeto del código de emparejamiento: sin 0/O ni 1/I (contrato, sección 6.1).
PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


class TokenExpired(Exception):
    pass


class TokenInvalid(Exception):
    pass


def create_access_token(user_id: uuid.UUID, role: str) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.access_token_minutes * 60
    claims = {"sub": str(user_id), "role": role, "exp": utcnow() + timedelta(seconds=expires_in)}
    token = jwt.encode(claims, settings.secret_key.get_secret_value(), algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> tuple[uuid.UUID, str]:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "role", "exp"]},
        )
        return uuid.UUID(claims["sub"]), str(claims["role"])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired from exc
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise TokenInvalid from exc


def new_opaque_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def sha256_hex(value: str) -> str:
    """Hash de tokens opacos de alta entropía (refresco y dispositivo)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def keyed_hash(value: str, label: str) -> str:
    """HMAC con la clave del servidor, para valores de poca entropía (códigos de emparejamiento)."""
    key = hmac.new(get_settings().secret_key.get_secret_value().encode("utf-8"), label.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def new_pairing_code() -> str:
    raw = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(6))
    return f"{raw[:3]}-{raw[3:]}"


def normalize_pairing_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").upper()

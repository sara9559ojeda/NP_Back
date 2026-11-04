"""Dependencias de autenticación y permisos por rol (contrato, sección 2)."""

from collections.abc import Callable
import hmac
import ipaddress
import os
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.config import get_settings
from app.core.security import TokenExpired, TokenInvalid, decode_access_token
from app.db.session import get_db
from app.repositories import identity
from app.services import pairing
from app.services.actor import Actor, DeviceActor

web_bearer = HTTPBearer(scheme_name="webAccessToken", description="JWT de acceso de la web (15 min).", auto_error=False)
device_bearer = HTTPBearer(scheme_name="deviceToken", description="Token opaco del visor emparejado.", auto_error=False)

Db = Annotated[Session, Depends(get_db)]


def client_ip(request: Request) -> str:
    secret = get_settings().proxy_secret
    supplied = request.headers.get("x-np-proxy-secret", "")
    if secret and hmac.compare_digest(supplied.encode(), secret.get_secret_value().encode()):
        try:
            return str(ipaddress.ip_address(request.headers.get("x-np-client-ip", "")))
        except ValueError:
            raise ApiError(400, "BAD_REQUEST", "IP del proxy no válida.") from None
    # Vercel establece esta cabecera. Fuera de esa plataforma se ignora.
    if os.environ.get("VERCEL") == "1":
        try:
            return str(ipaddress.ip_address(request.headers.get("x-vercel-forwarded-for", "")))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


def current_actor(
    db: Db, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(web_bearer)]
) -> Actor:
    if credentials is None:
        raise ApiError(401, "UNAUTHENTICATED", "Falta el token de acceso.")
    try:
        user_id, _ = decode_access_token(credentials.credentials)
    except TokenExpired as exc:
        raise ApiError(401, "TOKEN_EXPIRED", "El token de acceso ha caducado.") from exc
    except TokenInvalid as exc:
        raise ApiError(401, "UNAUTHENTICATED", "El token de acceso no es válido.") from exc
    user = identity.get_user(db, user_id)
    if user is None:
        raise ApiError(401, "UNAUTHENTICATED", "El token de acceso no es válido.")
    if not user.active:
        raise ApiError(423, "ACCOUNT_DISABLED", "La cuenta está desactivada.")
    # El rol se toma de la base: un cambio de rol se aplica sin esperar a que caduque el token.
    return Actor(user_id=user.id, role=user.role)


def require_roles(*roles: str) -> Callable[..., Actor]:
    def _dependency(actor: Annotated[Actor, Depends(current_actor)]) -> Actor:
        if actor.role not in roles:
            raise ApiError(403, "FORBIDDEN", "Tu rol no tiene acceso a este recurso.")
        return actor

    return _dependency


def current_device(
    db: Db, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(device_bearer)]
) -> DeviceActor:
    if credentials is None:
        raise ApiError(401, "UNAUTHENTICATED", "Falta el token de dispositivo.")
    token = credentials.credentials
    if token.count(".") == 2:
        try:
            decode_access_token(token)
        except (TokenExpired, TokenInvalid):
            pass
        else:
            # Un token de la web es válido, pero /device/* solo admite el token del visor.
            raise ApiError(403, "FORBIDDEN", "Esta ruta solo admite el token del visor.")
    return pairing.authenticate_device(db, token)


AnyUser = Annotated[Actor, Depends(current_actor)]
PatientUser = Annotated[Actor, Depends(require_roles("patient"))]
ProfessionalUser = Annotated[Actor, Depends(require_roles("professional"))]
AdminUser = Annotated[Actor, Depends(require_roles("admin"))]
PatientOrProfessional = Annotated[Actor, Depends(require_roles("patient", "professional"))]
Device = Annotated[DeviceActor, Depends(current_device)]

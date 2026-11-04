"""Rutas de datos propios (contrato, secciones 4.3, 5.2 y 6.1)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import AnyUser, Db, PatientUser
from app.api.docs import problems
from app.api.routes.auth import RefreshCookie, clear_refresh_cookie
from app.core.pagination import Page, page_params
from app.schemas.accounts import MeOut, MePatch, PasswordChangeIn
from app.schemas.common import StatusOut
from app.schemas.device import DevicePage, PairingCodeOut
from app.schemas.tracking import ProgressOut, SessionDetail, SessionPage
from app.services import accounts, auth, pairing, tracking

router = APIRouter(tags=["me"])

Pagination = Annotated[Page, Depends(page_params)]


@router.get("/me", response_model=MeOut, responses=problems(401, 423), summary="Datos propios")
def get_me(actor: AnyUser, db: Db) -> MeOut:
    return accounts.get_me(db, actor)


@router.patch("/me", response_model=MeOut, responses=problems(401, 409, 422, 423), summary="Editar nombre o correo")
def patch_me(data: MePatch, actor: AnyUser, db: Db) -> MeOut:
    return accounts.patch_me(db, actor, data)


@router.put(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problems(401, 422, 423),
    summary="Cambiar la contraseña (cierra las demás sesiones web)",
)
def change_password(data: PasswordChangeIn, actor: AnyUser, db: Db, np_refresh: RefreshCookie = None) -> Response:
    keep = auth.refresh_family(db, np_refresh)
    accounts.change_password(db, actor, data.current_password, data.new_password, keep_family=keep)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/me/consents/withdraw",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=StatusOut,
    responses=problems(401, 409, 423),
    summary="Retirar el consentimiento: borra la identidad y deja los datos clínicos sin vínculo",
)
def withdraw(actor: AnyUser, db: Db, response: Response) -> StatusOut:
    accounts.withdraw_consent(db, actor)
    clear_refresh_cookie(response)
    return StatusOut(status="withdrawn")


@router.get("/me/progress", response_model=ProgressOut, responses=problems(401, 403, 423), summary="Progreso del paciente")
def my_progress(actor: PatientUser, db: Db) -> ProgressOut:
    return tracking.progress(db, tracking.own_pseudonym(db, actor))


@router.get("/me/sessions", response_model=SessionPage, responses=problems(401, 403, 422, 423), summary="Sesiones propias")
def my_sessions(actor: PatientUser, db: Db, page: Pagination) -> SessionPage:
    return tracking.list_sessions(db, tracking.own_pseudonym(db, actor), page)


@router.get(
    "/me/sessions/{sessionId}",
    response_model=SessionDetail,
    responses=problems(401, 403, 404, 423),
    summary="Detalle de una sesión propia (sin notas)",
)
def my_session(sessionId: uuid.UUID, actor: PatientUser, db: Db) -> SessionDetail:  # noqa: N803
    return tracking.session_detail(db, tracking.own_pseudonym(db, actor), sessionId, with_notes=False)


@router.get("/me/devices", response_model=DevicePage, responses=problems(401, 403, 423), summary="Visores emparejados")
def my_devices(actor: PatientUser, db: Db) -> DevicePage:
    return pairing.list_devices(db, tracking.own_pseudonym(db, actor))


@router.delete(
    "/me/devices/{deviceId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problems(401, 403, 404, 423),
    summary="Revocar un visor",
)
def revoke_device(deviceId: uuid.UUID, actor: PatientUser, db: Db) -> Response:  # noqa: N803
    pairing.revoke_device(db, tracking.own_pseudonym(db, actor), deviceId)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/pairing-codes",
    status_code=status.HTTP_201_CREATED,
    response_model=PairingCodeOut,
    responses=problems(401, 403, 423),
    summary="Código para emparejar el visor (paciente)",
    tags=["device"],
)
def create_pairing_code(actor: PatientUser, db: Db) -> PairingCodeOut:
    return pairing.create_code(db, tracking.own_pseudonym(db, actor))

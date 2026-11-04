"""Rutas de registro y sesión web (contrato, secciones 4.1 y 4.2)."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response, status

from app.api.deps import Db, client_ip
from app.api.docs import problems
from app.core.config import get_settings
from app.schemas.accounts import LoginIn, LoginOut, RefreshOut, RegisterIn, RegisterOut, UserRef
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "np_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE, include_in_schema=False)]


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True, secure=settings.cookie_secure, samesite="strict"
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterOut,
    responses=problems(409, 422, 429),
    summary="Registro de un usuario externo (queda como paciente sin profesional, D18)",
)
def register(data: RegisterIn, request: Request, db: Db) -> RegisterOut:
    user_id = auth.register(db, data, client_ip(request))
    return RegisterOut(user_id=user_id, role="patient")


@router.post(
    "/login",
    response_model=LoginOut,
    responses=problems(401, 423, 429),
    summary="Inicio de sesión web; deja la cookie de refresco",
)
def login(data: LoginIn, request: Request, response: Response, db: Db) -> LoginOut:
    tokens = auth.login(db, data.email, data.password, client_ip(request))
    _set_refresh_cookie(response, tokens.refresh_token)
    return LoginOut(access_token=tokens.access_token, expires_in=tokens.expires_in, user=UserRef(id=tokens.user_id, role=tokens.role))


@router.post(
    "/refresh",
    response_model=RefreshOut,
    responses=problems(401, 423),
    summary="Nuevo token de acceso; rota la cookie de refresco",
)
def refresh(response: Response, db: Db, np_refresh: RefreshCookie = None) -> RefreshOut:
    tokens = auth.refresh(db, np_refresh)
    _set_refresh_cookie(response, tokens.refresh_token)
    return RefreshOut(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Cierra la sesión y revoca el refresco")
def logout(db: Db, np_refresh: RefreshCookie = None) -> Response:
    auth.logout(db, np_refresh)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response)
    return response

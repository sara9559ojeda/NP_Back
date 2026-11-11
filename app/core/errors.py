"""Errores ``application/problem+json`` (RFC 9457) con los códigos de la sección 8 del contrato."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("neurophobia.errors")

PROBLEM_CONTENT_TYPE = "application/problem+json"

# Títulos y detalles neutros. La web y el visor muestran sus propios textos a partir de ``code``.
_TITLES: dict[str, str] = {
    "BAD_REQUEST": "Petición mal formada",
    "UNAUTHENTICATED": "No autenticado",
    "TOKEN_EXPIRED": "Token caducado",
    "INVALID_CREDENTIALS": "Credenciales no válidas",
    "DEVICE_REVOKED": "Dispositivo revocado",
    "FORBIDDEN": "Sin permiso",
    "NOT_FOUND": "No encontrado",
    "PAIRING_CODE_INVALID": "Código de emparejamiento no válido",
    "METHOD_NOT_ALLOWED": "Método no permitido",
    "EMAIL_TAKEN": "Correo ya registrado",
    "RECORD_CONFLICT": "Registro en conflicto",
    "LAST_ADMIN": "Último administrador",
    "PAIRING_CODE_EXPIRED": "Código de emparejamiento caducado o usado",
    "PAYLOAD_TOO_LARGE": "Sobre demasiado grande",
    "VALIDATION_ERROR": "Datos no válidos",
    "CONSENT_REQUIRED": "Consentimiento obligatorio",
    "ACCOUNT_DISABLED": "Cuenta desactivada",
    "RATE_LIMITED": "Demasiados intentos",
    "SERVER_ERROR": "Error interno",
    "STORAGE_UNAVAILABLE": "Almacenamiento no disponible",
    "RELEASE_UNAVAILABLE": "Instalador no disponible",
}

# Seconds the client is asked to wait before retrying when the database does not answer.
STORAGE_RETRY_AFTER_SECONDS = 5

_DEFAULT_CODE_BY_STATUS: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "RECORD_CONFLICT",
    410: "PAIRING_CODE_EXPIRED",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    423: "ACCOUNT_DISABLED",
    429: "RATE_LIMITED",
    500: "SERVER_ERROR",
    503: "STORAGE_UNAVAILABLE",
}


class ApiError(Exception):
    """Error de negocio que se devuelve como problem+json."""

    def __init__(
        self,
        status: int,
        code: str,
        detail: str | None = None,
        errors: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.detail = detail
        self.errors = errors
        self.headers = headers


def field_error(field: str, code: str, detail: str | None = None) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", detail or "Revisa los campos marcados.", [{"field": field, "code": code}])


def problem_body(status: int, code: str, detail: str | None = None, errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"https://neurophobia/errors/{code.lower().replace('_', '-')}",
        "title": _TITLES.get(code, "Error"),
        "status": status,
        "code": code,
    }
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors
    return body


def problem_response(
    status: int,
    code: str,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        problem_body(status, code, detail, errors),
        status_code=status,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


def storage_unavailable_response() -> JSONResponse:
    return problem_response(
        503,
        "STORAGE_UNAVAILABLE",
        "No se pudieron guardar ni leer los datos. Inténtalo de nuevo.",
        headers={"Retry-After": str(STORAGE_RETRY_AFTER_SECONDS)},
    )


# Códigos de pydantic → códigos estables por campo (sin repetir nunca el valor recibido).
_PYDANTIC_CODE_MAP = {
    "missing": "required",
    "value_error": "invalid_format",
    "string_too_short": "too_short",
    "string_too_long": "too_long",
    "too_short": "too_short",
    "too_long": "too_long",
    "greater_than_equal": "out_of_range",
    "less_than_equal": "out_of_range",
    "greater_than": "out_of_range",
    "less_than": "out_of_range",
    "literal_error": "invalid_value",
    "enum": "invalid_value",
    "uuid_parsing": "invalid_format",
    "uuid_type": "invalid_format",
    "datetime_parsing": "invalid_format",
    "datetime_from_date_parsing": "invalid_format",
    "timezone_aware": "timezone_required",
    "extra_forbidden": "not_allowed",
    "int_parsing": "invalid_type",
    "int_from_float": "invalid_type",
    "int_type": "invalid_type",
    "float_parsing": "invalid_type",
    "float_type": "invalid_type",
    "bool_parsing": "invalid_type",
    "bool_type": "invalid_type",
    "string_type": "invalid_type",
    "list_type": "invalid_type",
    "dict_type": "invalid_type",
    "model_type": "invalid_type",
    "model_attributes_type": "invalid_type",
}


def _field_name(loc: tuple[Any, ...]) -> str:
    parts = [str(p) for p in loc]
    if parts and parts[0] in ("body", "query", "path", "header", "cookie"):
        parts = parts[1:]
    return ".".join(parts) or "body"


def validation_errors(raw_errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for err in raw_errors:
        err_type = str(err.get("type", "invalid"))
        ctx = err.get("ctx") or {}
        code = ctx.get("np_code") if isinstance(ctx, dict) else None
        if not code:
            code = _PYDANTIC_CODE_MAP.get(err_type, "invalid")
        out.append({"field": _field_name(tuple(err.get("loc", ()))), "code": str(code)})
    return out


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return problem_response(exc.status, exc.code, exc.detail, exc.errors, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        raw = list(exc.errors())
        if any(e.get("type") == "json_invalid" for e in raw):
            return problem_response(400, "BAD_REQUEST", "El cuerpo no es JSON válido.")
        return problem_response(422, "VALIDATION_ERROR", "Revisa los campos marcados.", validation_errors(raw))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _DEFAULT_CODE_BY_STATUS.get(exc.status_code, "SERVER_ERROR" if exc.status_code >= 500 else "BAD_REQUEST")
        return problem_response(exc.status_code, code, headers=getattr(exc, "headers", None))

    async def _storage(request: Request, exc: Exception) -> JSONResponse:
        # BPMN gateway "¿Almacena datos? -> no -> mensaje de error": the transaction is discarded, so
        # nothing is half-saved and the client can resend the same request. No technical details leak.
        logger.error("storage_unavailable type=%s request_id=%s", type(exc).__name__, getattr(request.state, "request_id", "-"))
        return storage_unavailable_response()

    for exc_class in (OperationalError, InterfaceError, PoolTimeoutError):
        app.add_exception_handler(exc_class, _storage)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Solo la clase de la excepción: el mensaje puede contener datos (p. ej. un correo en un IntegrityError).
        logger.error("unhandled_error type=%s request_id=%s", type(exc).__name__, getattr(request.state, "request_id", "-"))
        return problem_response(500, "SERVER_ERROR")

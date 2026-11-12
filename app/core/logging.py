"""Logs sin datos personales.

- El registro de acceso guarda método, plantilla de la ruta (sin valores ni query string), estado y duración.
- Nunca se registran cuerpos, cabeceras, correos, nombres ni tokens.
- Un filtro de redacción actúa como segunda barrera sobre cualquier mensaje.
- El formateador redacta también las trazas de excepción (``exc_info``), que el filtro no ve.
"""

import logging
import re
import sys
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core import timing

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_BEARER_RE = re.compile(r"(?i)bearer\s+[\w.\-~+/=]+")
_OPAQUE_RE = re.compile(r"\b(npr|npd)_[\w-]{10,}")
_JWT_RE = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")
# Hash Argon2 completo, incluidos los parámetros separados por comas (m=…,t=…,p=…).
_ARGON2_RE = re.compile(r"\$argon2(?:id|i|d)\$[^\s'\"]+")


def redact(text: str) -> str:
    text = _EMAIL_RE.sub("[correo]", text)
    text = _BEARER_RE.sub("Bearer [token]", text)
    text = _OPAQUE_RE.sub("[token]", text)
    text = _ARGON2_RE.sub("[hash]", text)
    return _JWT_RE.sub("[token]", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - un log mal formado no debe romper la petición
            message = str(record.msg)
        record.msg = redact(message)
        record.args = None
        return True


class RedactingFormatter(logging.Formatter):
    """Redacta la línea completa, incluida la traza que ``Formatter`` añade después del filtro."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # El access log de uvicorn escribe la URL completa (con query string): se desactiva.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


access_logger = logging.getLogger("neurophobia.access")


class AccessLogMiddleware:
    """Registro de acceso mínimo, con la plantilla de la ruta (``/patients/{patientId}``)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex[:12]
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.perf_counter()
        status_holder = {"status": 500}
        measured, token = timing.begin()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                # Solo duraciones (W3C Server-Timing): separa el tiempo de la API del de la red.
                elapsed = (time.perf_counter() - start) * 1000
                headers.append((b"server-timing", measured.header(elapsed).encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            timing.end(token)
            route = scope.get("route")
            template = getattr(route, "path", None) or "[sin ruta]"
            access_logger.info(
                "request_id=%s method=%s route=%s status=%s ms=%.1f db_ms=%.1f queries=%d",
                request_id,
                scope.get("method"),
                template,
                status_holder["status"],
                (time.perf_counter() - start) * 1000,
                measured.db_ms,
                measured.db_queries,
            )

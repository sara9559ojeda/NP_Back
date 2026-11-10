"""Cabeceras de seguridad comunes a todas las respuestas de la API.

- ``Cache-Control: no-store``: ninguna respuesta (datos personales o clínicos, tokens) se guarda en cachés,
  salvo que la ruta fije su propia política.
- ``X-Content-Type-Options: nosniff`` y ``Referrer-Policy: no-referrer``.

Se aplican en la propia API como defensa en profundidad, aunque el despliegue también las añada delante.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_DEFAULTS = (
    (b"cache-control", b"no-store"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                headers.extend((name, value) for name, value in _DEFAULTS if name not in present)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

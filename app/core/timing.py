"""Tiempos por petición para la cabecera ``Server-Timing`` y el registro de acceso.

Solo se guardan duraciones y el número de consultas: nunca sentencias SQL ni parámetros.
El contexto se crea en ``AccessLogMiddleware`` y viaja con la petición, incluidos los hilos
en los que FastAPI ejecuta las rutas síncronas (copian el contexto de la petición).
"""

import threading
from contextvars import ContextVar, Token
from dataclasses import dataclass, field


@dataclass
class RequestTiming:
    db_ms: float = 0.0
    db_queries: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_query(self, ms: float) -> None:
        with self._lock:
            self.db_ms += ms
            self.db_queries += 1

    def header(self, total_ms: float) -> str:
        """Valor de ``Server-Timing`` (W3C): tiempo total en la API y parte gastada en PostgreSQL."""
        return f'app;dur={total_ms:.1f}, db;dur={self.db_ms:.1f};desc="{self.db_queries} consultas"'


_current: ContextVar[RequestTiming | None] = ContextVar("np_request_timing", default=None)


def begin() -> tuple[RequestTiming, Token[RequestTiming | None]]:
    measured = RequestTiming()
    return measured, _current.set(measured)


def end(token: Token[RequestTiming | None]) -> None:
    _current.reset(token)


def add_query(ms: float) -> None:
    measured = _current.get()
    if measured is not None:  # consultas fuera de una petición (migraciones, CLI, worker)
        measured.add_query(ms)

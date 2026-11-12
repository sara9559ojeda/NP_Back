"""Motor y sesiones de SQLAlchemy."""

import os
import time
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core import timing
from app.core.config import Settings, get_settings

DEFAULT_POOL_SIZE = 5
# Puerto del Transaction pooler de Supabase: agrupa él mismo las conexiones.
TRANSACTION_POOLER_PORT = 6543


def pool_size(settings: Settings) -> int:
    """Conexiones que la API mantiene abiertas (0 = una conexión nueva por uso)."""
    if settings.db_pool_size is not None:
        return settings.db_pool_size
    if os.environ.get("VERCEL") == "1":
        return 0  # instancias serverless de corta vida
    if make_url(settings.database_url.get_secret_value()).port == TRANSACTION_POOLER_PORT:
        return 0
    return DEFAULT_POOL_SIZE


def _pool_options(size: int) -> dict[str, Any]:
    if size == 0:
        return {"poolclass": NullPool}
    return {
        "pool_size": size,
        # Picos breves (varias pestañas, el visor enviando registros) sin agotar max_connections.
        "max_overflow": size,
        "pool_timeout": 10,
        # Renueva las conexiones cada 30 min: evita conexiones colgadas tras reinicios de PostgreSQL.
        "pool_recycle": 1800,
    }


def _measure_queries(engine: Engine) -> None:
    """Suma la duración de cada consulta a la petición en curso (cabecera Server-Timing)."""

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        conn.info.setdefault("np_query_start", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        started = conn.info["np_query_start"].pop()
        timing.add_query((time.perf_counter() - started) * 1000)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    engine = create_engine(
        settings.database_url.get_secret_value(),
        # Comprueba la conexión al sacarla del pool: un PostgreSQL reiniciado no provoca errores 500.
        pool_pre_ping=True,
        # Sin valores de parámetros en los errores de SQLAlchemy (correos, hashes) que acaban en los logs.
        hide_parameters=True,
        # Sin sentencias preparadas del servidor: compatible con los poolers externos (Supabase).
        connect_args={"prepare_threshold": None},
        **_pool_options(pool_size(settings)),
    )
    _measure_queries(engine)
    return engine


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """Una sesión por petición.

    Los servicios hacen ``commit`` explícito antes de devolver la respuesta, para que un
    ``201`` nunca salga antes de que los datos estén guardados. Lo no confirmado se descarta.
    """
    db = _session_factory()()
    try:
        yield db
    finally:
        db.rollback()
        db.close()

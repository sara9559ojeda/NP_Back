"""Motor y sesiones de SQLAlchemy."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url.get_secret_value(),
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
    )


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

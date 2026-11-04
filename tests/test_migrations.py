"""Las migraciones de Alembic suben, bajan y coinciden con los modelos."""

import secrets

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.db.models import Base
from tests.conftest import ROOT


def test_upgrade_downgrade_and_no_drift(database_url):
    name = f"np_mig_{secrets.token_hex(4)}"
    admin_engine = create_engine(database_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(database_url).set(database=name).render_as_string(hide_password=False)
    try:
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.attributes["url"] = url
        cfg.attributes["configure_logger"] = False
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")

        engine = create_engine(url)
        with engine.connect() as conn:
            schemas = set(conn.execute(text("SELECT schema_name FROM information_schema.schemata")).scalars())
            assert {"identity", "clinical"} <= schemas
            context = MigrationContext.configure(conn, opts={"include_schemas": True})
            diff = [d for d in compare_metadata(context, Base.metadata) if not (isinstance(d, tuple) and d[0] == "remove_table")]
            assert diff == []
        engine.dispose()
    finally:
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin_engine.dispose()

"""Builds the SQLAlchemy database URL from the environment.

Two sources are supported, in this order:

1. ``NP_DATABASE_URL``: a full ``postgresql+psycopg://`` URL (Vercel, Supabase, Docker Compose).
2. ``NP_DATABASE_SECRET``: the JSON document that Amazon RDS stores in AWS Secrets Manager
   (``username``, ``password``, ``host``, ``port``, ``dbname``). Amazon ECS injects it as an
   environment variable, so the password never appears in the task definition.
"""

import json
from collections.abc import Mapping
from urllib.parse import quote

DRIVER = "postgresql+psycopg"
DEFAULT_PORT = 5432
DEFAULT_DBNAME = "postgres"
URL_VARIABLE = "NP_DATABASE_URL"
SECRET_VARIABLE = "NP_DATABASE_SECRET"


class DatabaseSecretError(ValueError):
    """The RDS secret is not a JSON object with the expected fields."""


def url_from_rds_secret(secret: str) -> str:
    """Return a TLS-only psycopg URL for the RDS secret JSON ``secret``."""
    try:
        fields = json.loads(secret)
        username, password, host = fields["username"], fields["password"], fields["host"]
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        raise DatabaseSecretError("NP_DATABASE_SECRET must hold username, password and host") from exc
    port = int(fields.get("port") or DEFAULT_PORT)
    dbname = fields.get("dbname") or DEFAULT_DBNAME
    credentials = f"{quote(username, safe='')}:{quote(password, safe='')}"
    return f"{DRIVER}://{credentials}@{host}:{port}/{quote(dbname, safe='')}?sslmode=require"


def database_url_from_env(environ: Mapping[str, str]) -> str | None:
    """Return the configured database URL, or ``None`` when neither variable is set."""
    if url := environ.get(URL_VARIABLE):
        return url
    if secret := environ.get(SECRET_VARIABLE):
        return url_from_rds_secret(secret)
    return None

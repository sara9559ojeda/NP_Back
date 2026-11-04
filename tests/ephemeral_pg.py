"""PostgreSQL efímero para las pruebas.

- Si existe ``NP_TEST_DATABASE_URL`` (por ejemplo, en la integración continua), se usa esa base.
- Si no, se arranca un contenedor ``postgres`` con usuario y contraseña aleatorios, generados en
  tiempo de ejecución y pasados por variable de entorno (no quedan en ningún archivo ni en la
  línea de órdenes). El contenedor se borra al terminar.
"""

import os
import secrets
import subprocess
import time
from contextlib import contextmanager

import psycopg

IMAGE = os.environ.get("NP_TEST_PG_IMAGE", "postgres:17-alpine")


def _wait(url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(url, connect_timeout=2) as conn:
                conn.execute("SELECT 1")
            return
        except psycopg.OperationalError as exc:
            last = exc
            time.sleep(0.5)
    raise RuntimeError("PostgreSQL efímero no respondió a tiempo") from last


@contextmanager
def ephemeral_postgres():
    """Devuelve una URL ``postgresql+psycopg://`` lista para usar."""
    external = os.environ.get("NP_TEST_DATABASE_URL")
    if external:
        yield external
        return

    name = f"np-test-pg-{secrets.token_hex(4)}"
    user = f"u{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(24)
    env = {**os.environ, "POSTGRES_USER": user, "POSTGRES_PASSWORD": password, "POSTGRES_DB": "np_test"}
    subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            "-e", "POSTGRES_USER", "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_DB",
            "-p", "127.0.0.1::5432", IMAGE,
        ],
        env=env, check=True, capture_output=True,
    )
    try:
        port_line = subprocess.run(
            ["docker", "port", name, "5432/tcp"], check=True, capture_output=True, text=True, encoding="utf-8"
        ).stdout.strip().splitlines()[0]
        port = port_line.rsplit(":", 1)[1]
        url = f"postgresql://{user}:{password}@127.0.0.1:{port}/np_test"
        _wait(url)
        yield url.replace("postgresql://", "postgresql+psycopg://", 1)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)

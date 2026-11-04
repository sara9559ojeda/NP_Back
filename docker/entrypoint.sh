#!/bin/sh
# Aplica las migraciones y arranca la API. El access log de uvicorn se desactiva:
# la aplicación escribe su propio registro sin datos personales.
set -e
alembic upgrade head
exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --no-access-log

"""Configuración leída de variables de entorno (prefijo ``NP_``).

Ningún secreto tiene valor por defecto: ``NP_DATABASE_URL`` y ``NP_SECRET_KEY``
son obligatorios y los escribe Sara en ``backend/.env`` (fuera de Git).
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NP_", env_file=None, extra="ignore")

    # Obligatorios (secretos).
    database_url: SecretStr
    secret_key: SecretStr = Field(min_length=32)

    # Web.
    cors_origin: str = "http://localhost:5173"
    cookie_secure: bool = True

    # Tokens (contrato, sección 2.2).
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # Emparejamiento (contrato, sección 6.1).
    pairing_code_minutes: int = 10
    pairing_max_failures: int = 5
    pairing_failure_window_seconds: int = 900

    # Límites de frecuencia (valores técnicos, no clínicos).
    register_max_per_window: int = 10
    register_window_seconds: int = 3600
    login_max_per_window: int = 10
    login_window_seconds: int = 300

    # Visor.
    max_record_bytes: int = 256 * 1024

    # Progreso: cuántas sesiones recientes se devuelven en /me/progress.
    progress_last_sessions: int = 5

    # Módulo de IA.
    ai_method: str = "rules-baseline"

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

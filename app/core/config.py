"""Configuración leída de variables de entorno (prefijo ``NP_``).

Ningún secreto tiene valor por defecto: ``NP_DATABASE_URL`` y ``NP_SECRET_KEY``
son obligatorios y los escribe Sara en ``backend/.env`` (fuera de Git).
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database_url import url_from_rds_secret

APP_VERSION = "0.2.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NP_", env_file=None, extra="ignore")

    # Obligatorios (secretos).
    database_url: SecretStr
    secret_key: SecretStr = Field(min_length=32)
    # AWS only: RDS secret JSON injected by ECS; used when NP_DATABASE_URL is absent.
    database_secret: SecretStr | None = None
    # Conexiones abiertas que la API reutiliza. Sin valor: 5, salvo en Vercel o con el Transaction
    # pooler de Supabase (puerto 6543), donde el pooler externo ya agrupa y se usa 0 (sin pool propio).
    db_pool_size: int | None = Field(default=None, ge=0, le=20)

    # Web.
    cors_origin: str = "http://localhost:5173"
    cookie_secure: bool = True
    # Se comparte solo entre los servidores front/back, nunca con el navegador.
    proxy_secret: SecretStr | None = Field(default=None, min_length=32)

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

    apk_release_directory: Path | None = None
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-20b"
    external_ai_enabled: bool = False
    groq_daily_request_limit: int = Field(default=25, ge=0, le=1000)
    groq_timeout_seconds: float = Field(default=8, ge=1, le=20)

    log_level: str = "INFO"

    @model_validator(mode="before")
    @classmethod
    def _database_url_from_rds_secret(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("database_url") and data.get("database_secret"):
            return {**data, "database_url": url_from_rds_secret(str(data["database_secret"]))}
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

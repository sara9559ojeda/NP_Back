"""Aplicación FastAPI de NEUROPHOBIA (monolito modular por capas, apartado 3.6 del documento).

Capas:
- presentación: ``app.api`` (rutas y dependencias de autenticación);
- lógica de negocio: ``app.services`` (reglas, permisos por rol);
- módulo de IA: ``app.ai`` (no depende de la base de datos);
- acceso a datos: ``app.repositories`` y ``app.db``.
"""

from typing import Any
import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.routes import admin, auth, device, health, me, patients, public, releases
from app.core.config import APP_VERSION, get_settings
from app.core.errors import install_error_handlers
from app.core.headers import SecurityHeadersMiddleware
from app.core.logging import AccessLogMiddleware, configure_logging
from app.schemas.common import Problem
from app.schemas.device import RecordEnvelope, PAYLOAD_MODELS
from app.ai.groq_summary import enabled
from app.services.narratives import summary_worker

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(summary_worker()) if enabled(get_settings()) else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def custom_openapi(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title="NEUROPHOBIA API",
        version=APP_VERSION,
        description=(
            "API v1 de NEUROPHOBIA (prototipo académico). Contrato: docs/api/CONTRATO_API_v1.md (contrato-v1.1.0). "
            "Errores en application/problem+json (RFC 9457)."
        ),
        routes=app.routes,
    )
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    extra_models = [("Problem", Problem), ("RecordEnvelope", RecordEnvelope)]
    extra_models += [(f"{name.title().replace('_', '')}Payload", model) for name, model in PAYLOAD_MODELS.items()]
    for name, model in extra_models:
        model_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        for def_name, definition in model_schema.pop("$defs", {}).items():
            components.setdefault(def_name, definition)
        components[name] = model_schema
    # FastAPI documenta su 422 propio; el contrato usa problem+json.
    components.pop("HTTPValidationError", None)
    components.pop("ValidationError", None)
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            responses = operation.get("responses", {})
            if "422" in responses and "application/json" in responses["422"].get("content", {}):
                responses["422"] = {
                    "description": "VALIDATION_ERROR",
                    "content": {"application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}},
                }
    app.openapi_schema = schema
    return schema


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="NEUROPHOBIA API",
        version=APP_VERSION,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    install_error_handlers(app)
    for module in (health, public, auth, me, admin, patients, device, releases):
        app.include_router(module.router, prefix=API_PREFIX)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        expose_headers=["X-Request-Id", "Retry-After", "Server-Timing"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.openapi = lambda: custom_openapi(app)  # type: ignore[method-assign]
    return app

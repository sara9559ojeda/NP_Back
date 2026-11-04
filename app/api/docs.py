"""Respuestas de error para la documentación OpenAPI.

El esquema ``Problem`` se añade a ``components`` en ``app.main.custom_openapi``.
"""

from typing import Any

from app.core.errors import PROBLEM_CONTENT_TYPE

_DESCRIPTIONS = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED, TOKEN_EXPIRED, INVALID_CREDENTIALS o DEVICE_REVOKED",
    403: "FORBIDDEN",
    404: "NOT_FOUND o PAIRING_CODE_INVALID",
    409: "EMAIL_TAKEN, RECORD_CONFLICT o LAST_ADMIN",
    410: "PAIRING_CODE_EXPIRED",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR o CONSENT_REQUIRED",
    423: "ACCOUNT_DISABLED",
    429: "RATE_LIMITED",
}


def problems(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {
        status: {
            "description": _DESCRIPTIONS.get(status, "Error"),
            "content": {PROBLEM_CONTENT_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
        }
        for status in statuses
    }

"""Rutas del visor (contrato, sección 6)."""

import json
import math
import uuid

from fastapi import APIRouter, Request, Response, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import Db, Device, client_ip
from app.api.docs import problems
from app.core.config import get_settings
from app.core.errors import ApiError
from app.schemas.device import DeviceContext, DeviceSessionOut, PairIn, PairOut, PhobiaGradeIn, PhobiaGradeOut, RecordResult
from app.services import pairing, records, therapy

router = APIRouter(prefix="/device", tags=["device"])


def _reject_constant(name: str) -> float:
    raise ValueError(f"constante JSON no admitida: {name}")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("número fuera de rango")
    return value


@router.post(
    "/pair",
    status_code=status.HTTP_201_CREATED,
    response_model=PairOut,
    responses=problems(404, 410, 422, 429),
    summary="Emparejar el visor con el código de la web",
)
def pair(data: PairIn, request: Request, db: Db) -> PairOut:
    return pairing.pair(db, data, client_ip(request))


@router.get(
    "/context",
    response_model=DeviceContext,
    responses=problems(401, 403),
    summary="Contexto al empezar, en el Refugio (sin nombre ni correo). v1.1.0: incluye phobiaGrade",
)
def context(device: Device, db: Db) -> DeviceContext:
    return records.device_context(db, device)


@router.post(
    "/records",
    status_code=status.HTTP_201_CREATED,
    response_model=RecordResult,
    responses={
        200: {"model": RecordResult, "description": "duplicate: ya existía con el mismo contenido"},
        **problems(400, 401, 403, 409, 413, 422, 503),
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/RecordEnvelope"}}},
        }
    },
    summary="Entrada única de la bandeja de salida del visor (idempotente por recordId); v1.1.0: session y feedback",
)
async def post_record(request: Request, device: Device, db: Db, response: Response) -> RecordResult:
    limit = get_settings().max_record_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "El sobre supera los 256 KB.")
    body = await request.body()
    if len(body) > limit:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "El sobre supera los 256 KB.")
    try:
        parsed = json.loads(body.decode("utf-8"), parse_constant=_reject_constant, parse_float=_finite_float)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ApiError(400, "BAD_REQUEST", "El cuerpo no es JSON válido.") from exc
    result = await run_in_threadpool(records.ingest, db, device, parsed)
    if result.status == "duplicate":
        response.status_code = status.HTTP_200_OK
    return result


# ───────────── v1.1.0: phobia grade, session status and headset logout ─────────────


@router.put(
    "/phobia-grade",
    response_model=PhobiaGradeOut,
    responses=problems(401, 403, 404, 422, 503),
    summary="Ajustar grado de fobia (1–5) en el Refugio, antes de «Comenzar»",
)
def put_phobia_grade(data: PhobiaGradeIn, device: Device, db: Db) -> PhobiaGradeOut:
    return therapy.set_phobia_grade(db, device.pseudonym_id, data.phobia_grade)


@router.get(
    "/sessions/{sessionId}",
    response_model=DeviceSessionOut,
    responses=problems(401, 403, 404, 503),
    summary="Estado de una sesión del visor y de su retroalimentación",
)
def get_session(sessionId: uuid.UUID, device: Device, db: Db) -> DeviceSessionOut:  # noqa: N803
    return therapy.device_session(db, device, sessionId)


@router.post(
    "/unpair",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problems(401, 403),
    summary="Cerrar sesión en el visor: revoca su propio token",
)
def unpair(device: Device, db: Db) -> Response:
    therapy.unpair(db, device)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

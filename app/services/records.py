"""Entrada de registros del visor y contexto al empezar (contrato, secciones 6.2 y 6.3; D12).

- Idempotente por ``recordId``: mismo sobre → ``duplicate``; mismo ``recordId`` con otro contenido → 409.
- Acepta registros desordenados: un ``level_record`` o un ``session_end`` sin ``session_start``
  crea la sesión en estado ``pending_start`` y se enlaza cuando llega el inicio.
"""

import hashlib
import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, validation_errors
from app.db.models import LevelRecord
from app.repositories import clinical
from app.schemas.device import (
    PAYLOAD_MODELS,
    ContextLastSession,
    ContextRecommendation,
    DeviceContext,
    LevelRecordPayload,
    RecordEnvelope,
    RecordResult,
    SessionEndPayload,
    SessionStartPayload,
)
from app.services.actor import DeviceActor
from app.services.therapy import session_ref, sync_phobia_grade_from_session
from app.services.analysis import feedback_for, refresh_analysis


def _conflict() -> ApiError:
    return ApiError(409, "RECORD_CONFLICT", "Ya existe un registro con ese recordId y otro contenido.")


def _validation(exc: ValidationError, prefix: tuple[str, ...] = ()) -> ApiError:
    raw = [dict(e, loc=prefix + tuple(e["loc"])) for e in exc.errors()]
    return ApiError(422, "VALIDATION_ERROR", "El sobre no cumple el esquema.", validation_errors(raw))


def content_hash(body: dict[str, Any]) -> str:
    content = {k: body.get(k) for k in ("type", "schemaVersion", "sessionId", "payload")}
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_envelope(body: Any) -> tuple[RecordEnvelope, Any]:
    if not isinstance(body, dict):
        raise ApiError(422, "VALIDATION_ERROR", "El sobre no cumple el esquema.", [{"field": "body", "code": "invalid_type"}])
    try:
        envelope = RecordEnvelope.model_validate(body)
    except ValidationError as exc:
        raise _validation(exc) from exc
    try:
        payload = PAYLOAD_MODELS[envelope.type].model_validate(envelope.payload)
    except ValidationError as exc:
        raise _validation(exc, ("payload",)) from exc
    return envelope, payload


def ingest(db: Session, device: DeviceActor, body: dict[str, Any]) -> RecordResult:
    """Store one outbox envelope and report the resulting session and feedback state (contract v1.1.0).

    Metrics, AI analysis and feedback are committed in a single transaction ("therapy" sequence
    diagram): if anything fails nothing is half-saved and the headset can resend the same envelope.
    """
    envelope, payload = parse_envelope(body)
    status = _store(db, device, envelope, payload, body)
    session = clinical.get_session(db, device.pseudonym_id, envelope.sessionId)
    if session is None:  # unreachable: the envelope was just stored or already existed
        return RecordResult(status=status)
    result = RecordResult(status=status, session=session_ref(session), feedback=feedback_for(db, session))
    db.commit()  # persists the device's last_seen_at on duplicates
    return result


def _store(db: Session, device: DeviceActor, envelope: RecordEnvelope, payload: Any, body: dict[str, Any]) -> str:
    """Return ``"stored"`` or ``"duplicate"``."""
    digest = content_hash(body)

    existing = clinical.get_inbound(db, envelope.recordId)
    if existing is not None:
        return _duplicate_or_conflict(existing, device, digest)

    session = clinical.lock_or_create_session(db, envelope.sessionId, device.pseudonym_id, device.device_id)
    if session.pseudonym_id != device.pseudonym_id:
        db.rollback()
        raise _conflict()

    inserted = clinical.try_add_inbound(
        db,
        record_id=envelope.recordId,
        pseudonym_id=device.pseudonym_id,
        device_id=device.device_id,
        session_id=envelope.sessionId,
        type=envelope.type,
        schema_version=envelope.schemaVersion,
        content_hash=digest,
    )
    if not inserted:  # otro envío del mismo recordId ganó la carrera
        db.rollback()
        existing = clinical.get_inbound(db, envelope.recordId)
        if existing is None:
            raise ApiError(500, "SERVER_ERROR")
        return _duplicate_or_conflict(existing, device, digest)

    raw_payload = body["payload"]
    if isinstance(payload, SessionStartPayload):
        if session.has_start:
            db.rollback()
            raise _conflict()
        session.has_start = True
        session.started_at = payload.startedAt
        session.phobia_grade = payload.phobiaGrade
        sync_phobia_grade_from_session(db, device.pseudonym_id, payload.phobiaGrade, payload.startedAt)
        session.app_version = payload.appVersion
        session.device_model = payload.deviceModel
        session.test_session = payload.testSession
        session.raw = {**session.raw, "session_start": raw_payload}
    elif isinstance(payload, SessionEndPayload):
        if session.has_end:
            db.rollback()
            raise _conflict()
        session.has_end = True
        session.ended_at = payload.endedAt
        session.end_reason = payload.endReason
        session.level_reached = payload.levelReached
        session.total_duration_seconds = payload.totalDurationSeconds
        session.raw = {**session.raw, "session_end": raw_payload}
    elif isinstance(payload, LevelRecordPayload):
        clinical.add_level_record(
            db,
            LevelRecord(
                id=envelope.recordId,
                session_id=session.id,
                level=payload.level,
                attempt=payload.attempt,
                outcome=payload.outcome,
                criterion_met=payload.criterionMet,
                started_at=payload.startedAt,
                ended_at=payload.endedAt,
                permanence_seconds=payload.permanenceSeconds,
                min_distance_m=payload.minDistanceM,
                avoidance_count=payload.avoidanceCount,
                payload=raw_payload,
            ),
        )
    db.flush()
    refresh_analysis(db, session)
    db.commit()
    return "stored"


def _duplicate_or_conflict(existing, device: DeviceActor, digest: str) -> str:
    if existing.pseudonym_id == device.pseudonym_id and existing.content_hash == digest:
        return "duplicate"
    raise _conflict()


def device_context(db: Session, device: DeviceActor) -> DeviceContext:
    patient = clinical.get_patient(db, device.pseudonym_id)
    allowed = patient.allowed_start_level if patient else 1
    closed = [s for s in clinical.progress_sessions(db, device.pseudonym_id) if s.has_end]
    closed.sort(key=lambda s: s.ended_at, reverse=True)
    last = closed[0] if closed else None
    method = get_settings().ai_method
    analyses = clinical.analyses_for(db, [s.id for s in closed], method)
    from_session = next((s for s in closed if s.id in analyses), None)
    recommendation = None
    if from_session is not None:
        a = analyses[from_session.id]
        recommendation = ContextRecommendation(
            value=a.recommendation, from_session_id=from_session.id, method=a.method, clinical_status=a.clinical_status
        )
    db.commit()  # guarda last_seen_at del dispositivo
    return DeviceContext(
        allowed_start_level=allowed,
        last_session=ContextLastSession(
            ended_at=last.ended_at, level_reached=last.level_reached, total_duration_seconds=last.total_duration_seconds
        )
        if last
        else None,
        recommendation=recommendation,
        phobia_grade=patient.phobia_grade if patient else None,
        phobia_grade_updated_at=patient.phobia_grade_updated_at if patient else None,
    )

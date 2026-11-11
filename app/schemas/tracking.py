"""Esquemas de seguimiento: progreso, sesiones, análisis, plan y notas (contrato, secciones 5 y 7)."""

import uuid
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import CamelModel, Paginated, UtcDateTime

Recommendation = Literal["advance", "repeat", "step_back"]


class BasisItem(CamelModel):
    feature: str
    value: float | int | bool | None
    effect: Literal["favorable", "unfavorable", "neutral"]


class AnalysisOut(CamelModel):
    tolerance_index: float
    recommendation: Recommendation
    method: str
    method_version: str
    basis: list[BasisItem]
    clinical_status: str
    created_at: UtcDateTime
    explanation: str | None = None
    evaluated_level: int | None = None
    evaluated_attempt: int | None = None
    narrative: str | None = None
    narrative_status: Literal["disabled", "pending", "generating", "generated", "fallback", "quota_exceeded"] = "disabled"
    narrative_model: str | None = None
    narrative_created_at: UtcDateTime | None = None


class SessionComparison(CamelModel):
    previous_session_id: uuid.UUID
    previous_ended_at: UtcDateTime
    level_delta: int | None
    duration_delta_seconds: float | None
    tolerance_delta: float | None
    tolerance_comparable: bool


class LastSessionItem(CamelModel):
    session_id: uuid.UUID
    started_at: UtcDateTime | None
    level_reached: int | None
    total_duration_seconds: float | None
    recommendation: Recommendation | None


class ProgressOut(CamelModel):
    sessions_count: int
    level_reached: int | None
    last_sessions: list[LastSessionItem]


class PatientSummary(CamelModel):
    patient_id: uuid.UUID
    full_name: str | None
    last_session_at: UtcDateTime | None
    level_reached: int | None
    last_recommendation: Recommendation | None
    phobia_grade: int | None = None


class PatientPage(Paginated[PatientSummary]):
    pass


SessionStatus = Literal["open", "closed", "pending_start"]


class SessionSummary(CamelModel):
    session_id: uuid.UUID
    status: SessionStatus
    started_at: UtcDateTime | None
    ended_at: UtcDateTime | None
    phobia_grade: int | None
    test_session: bool | None
    end_reason: str | None
    level_reached: int | None
    total_duration_seconds: float | None
    recommendation: Recommendation | None
    tolerance_index: float | None


class SessionPage(Paginated[SessionSummary]):
    pass


class LevelRecordOut(CamelModel):
    record_id: uuid.UUID
    level: int
    attempt: int
    outcome: str
    criterion_met: bool
    started_at: UtcDateTime
    ended_at: UtcDateTime
    permanence_seconds: float
    min_distance_m: float | None
    avoidance_count: int
    suds: list[dict[str, Any]]
    payload: dict[str, Any]


class NoteOut(CamelModel):
    note_id: uuid.UUID
    session_id: uuid.UUID | None
    author_id: uuid.UUID
    author_name: str | None
    text: str
    created_at: UtcDateTime
    edited_at: UtcDateTime | None


class NotePage(Paginated[NoteOut]):
    pass


class SessionDetail(SessionSummary):
    app_version: str | None
    device_model: str | None
    levels: list[LevelRecordOut]
    analysis: AnalysisOut | None


class ProfessionalSessionDetail(SessionDetail):
    notes: list[NoteOut]


class PlanIn(CamelModel):
    allowed_start_level: Annotated[int, Field(ge=1, le=5, strict=True)]


class PlanOut(CamelModel):
    patient_id: uuid.UUID
    allowed_start_level: int
    updated_at: UtcDateTime | None


NoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class NoteIn(CamelModel):
    text: NoteText
    session_id: uuid.UUID | None = None


class NoteCreated(NoteOut):
    """``201`` body of a new note. Since v1.1.0 it is the whole stored note ("comentario anotado")."""


class NotePatch(CamelModel):
    text: NoteText


# ───────────── feedback and therapy state (v1.1.0) ─────────────


class SessionFeedbackItem(CamelModel):
    session_id: uuid.UUID
    started_at: UtcDateTime | None
    ended_at: UtcDateTime | None
    phobia_grade: int | None
    level_reached: int | None
    end_reason: str | None
    analysis: AnalysisOut
    total_duration_seconds: float | None = None
    comparison: SessionComparison | None = None


class ProfessionalFeedbackItem(SessionFeedbackItem):
    notes_count: int


class FeedbackPage(Paginated[ProfessionalFeedbackItem]):
    pass


class OpenSessionOut(CamelModel):
    session_id: uuid.UUID
    started_at: UtcDateTime | None


class TherapyStateOut(CamelModel):
    phobia_grade: int | None
    phobia_grade_updated_at: UtcDateTime | None
    allowed_start_level: int
    paired_devices: int
    open_session: OpenSessionOut | None
    last_session: LastSessionItem | None
    last_feedback: SessionFeedbackItem | None

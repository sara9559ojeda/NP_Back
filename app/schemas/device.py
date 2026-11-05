"""Esquemas del visor: emparejamiento, contexto y sobres de ``/device/records`` (contrato, sección 6)."""

import uuid
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.common import CamelModel, Paginated, UtcDateTime

# ───────────── emparejamiento ─────────────


class PairingCodeOut(CamelModel):
    code: str
    expires_at: UtcDateTime


class PairIn(CamelModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=8)]
    device_model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")]
    app_version: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_.+-]+$")]


class PairOut(CamelModel):
    device_id: uuid.UUID
    device_token: str


class DeviceOut(CamelModel):
    device_id: uuid.UUID
    device_model: str
    app_version: str
    paired_at: UtcDateTime
    last_seen_at: UtcDateTime | None
    revoked_at: UtcDateTime | None


class DevicePage(Paginated[DeviceOut]):
    pass


# ───────────── contexto ─────────────


class ContextLastSession(CamelModel):
    ended_at: UtcDateTime | None
    level_reached: int | None
    total_duration_seconds: float | None


class ContextRecommendation(CamelModel):
    value: Literal["advance", "repeat", "step_back"]
    from_session_id: uuid.UUID
    method: str
    clinical_status: str


class DeviceContext(CamelModel):
    allowed_start_level: int
    last_session: ContextLastSession | None
    recommendation: ContextRecommendation | None
    # v1.1.0: latest self-reported phobia grade, to prefill the "Ajustar grado de fobia" step.
    phobia_grade: int | None = None
    phobia_grade_updated_at: UtcDateTime | None = None


# ───────────── phobia grade and therapy state (v1.1.0) ─────────────

PhobiaGrade = Annotated[int, Field(ge=1, le=5, strict=True)]


class PhobiaGradeIn(CamelModel):
    phobia_grade: PhobiaGrade


class PhobiaGradeOut(CamelModel):
    phobia_grade: int | None
    updated_at: UtcDateTime | None


FeedbackStatus = Literal["saved", "not_applicable", "insufficient_data", "pending"]
SessionStatus = Literal["open", "closed", "pending_start"]


class FeedbackOut(CamelModel):
    """Feedback (AI analysis) state of a session.

    - ``saved``: the analysis is stored (same data as ``analysis`` in the session detail).
    - ``pending``: the session is still missing its start or its end.
    - ``not_applicable``: test session (``testSession = true``); it is never analysed.
    - ``insufficient_data``: closed session without enough data for the current method.
    """

    status: FeedbackStatus
    recommendation: Literal["advance", "repeat", "step_back"] | None = None
    tolerance_index: float | None = None
    method: str | None = None
    clinical_status: str | None = None
    created_at: UtcDateTime | None = None


class SessionRef(CamelModel):
    session_id: uuid.UUID
    status: SessionStatus


class DeviceSessionOut(CamelModel):
    session_id: uuid.UUID
    status: SessionStatus
    started_at: UtcDateTime | None
    ended_at: UtcDateTime | None
    phobia_grade: int | None
    level_reached: int | None
    levels_stored: int
    feedback: FeedbackOut


# ───────────── sobres ─────────────


class _Payload(BaseModel):
    # Los payloads se guardan completos en JSONB; se admiten campos adicionales para no perder datos.
    model_config = ConfigDict(extra="allow")


DeviceModel = Literal["quest2", "quest3", "quest3s", "editor"]


class SessionStartPayload(_Payload):
    startedAt: AwareDatetime
    phobiaGrade: Annotated[int, Field(ge=1, le=5, strict=True)]
    appVersion: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    deviceModel: DeviceModel
    testSession: bool


class Gaze(_Payload):
    coneDeg: Annotated[float, Field(gt=0, le=180)]
    onStimulusSeconds: Annotated[float, Field(ge=0)]
    meanAngleDeg: Annotated[float | None, Field(ge=0, le=180)] = None


class Suds(_Payload):
    phase: Literal["before", "during", "after"]
    value: Annotated[int, Field(ge=0, le=100, strict=True)]
    at: Annotated[float, Field(ge=0)]


EventType = Literal[
    "level_start",
    "level_end",
    "pause",
    "resume",
    "avoidance",
    "suds",
    "safe_exit",
    "repeat_offered",
    "repeat_accepted",
    "tutorial_skipped",
]


class Event(_Payload):
    t: Annotated[float, Field(ge=0)]
    type: EventType
    data: dict[str, Any] | None = None


class Samples(_Payload):
    hz: Annotated[float, Field(gt=0)]
    distanceM: list[float | None] = []
    angleDeg: list[float | None] = []


class LevelRecordPayload(_Payload):
    level: Annotated[int, Field(ge=1, le=5, strict=True)]
    attempt: Annotated[int, Field(ge=1, le=1000, strict=True)]
    levelDefinitionVersion: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    startedAt: AwareDatetime
    endedAt: AwareDatetime
    outcome: Literal["completed", "criterion_not_met", "safe_exit", "abandoned"]
    criterionMet: bool
    permanenceSeconds: Annotated[float, Field(ge=0)]
    minDistanceM: Annotated[float | None, Field(ge=0)]
    gaze: Gaze
    avoidanceCount: Annotated[int, Field(ge=0, strict=True)]
    suds: list[Suds] = []
    events: list[Event] = []
    samples: Samples | None = None
    extra: dict[str, Any] = {}

    @model_validator(mode="after")
    def _times(self) -> "LevelRecordPayload":
        if self.endedAt < self.startedAt:
            raise ValueError("endedAt_before_startedAt")
        return self


class SessionEndPayload(_Payload):
    endedAt: AwareDatetime
    endReason: Literal["completed", "user_finished", "safe_exit", "app_closed"]
    levelReached: Annotated[int, Field(ge=0, le=5, strict=True)]
    totalDurationSeconds: Annotated[float, Field(ge=0)]


PAYLOAD_MODELS: dict[str, type[_Payload]] = {
    "session_start": SessionStartPayload,
    "level_record": LevelRecordPayload,
    "session_end": SessionEndPayload,
}


class RecordEnvelope(BaseModel):
    """Sobre de la bandeja de salida del visor (D12)."""

    model_config = ConfigDict(extra="forbid")

    recordId: uuid.UUID
    type: Literal["session_start", "level_record", "session_end"]
    schemaVersion: Literal[1]
    sessionId: uuid.UUID
    payload: dict[str, Any]


class RecordResult(CamelModel):
    status: Literal["stored", "duplicate"]
    # v1.1.0 (optional): session and feedback state after storing the envelope.
    session: SessionRef | None = None
    feedback: FeedbackOut | None = None

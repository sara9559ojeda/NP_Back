"""Modelo de datos (contrato, sección 3).

Dos esquemas separados:

- ``identity``: quién es cada persona (correo, nombre, contraseña, rol, consentimientos, asignaciones).
- ``clinical``: datos de las sesiones, asociados solo a un ``pseudonym_id`` aleatorio.

No hay claves foráneas entre esquemas: solo la capa de servicio une los dos lados a través de
``identity.identity_links``. Así el esquema clínico podría moverse a otra base sin cambios.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    BigInteger,
    Identity,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class RateLimitEvent(Base):
    __tablename__ = "rate_limit_events"
    __table_args__ = (
        Index("ix_rate_limit_key_time", "key_hash", "occurred_at"),
        Index("ix_rate_limit_time", "occurred_at"),
        {"schema": "identity"},
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()"))


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ───────────────────────────── esquema identity ─────────────────────────────


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('patient', 'professional', 'admin')", name="role"),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PersonalData(Base):
    __tablename__ = "personal_data"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), primary_key=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_at: Mapped[datetime] = _created_at()


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = {"schema": "identity"}

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdentityLink(Base):
    __tablename__ = "identity_links"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), primary_key=True
    )
    pseudonym_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        Index(
            "uq_assignments_active_pair",
            "professional_user_id",
            "patient_user_id",
            unique=True,
            postgresql_where=text("active"),
        ),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    professional_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _created_at()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "identity"}

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ───────────────────────────── esquema clinical ─────────────────────────────


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint("allowed_start_level BETWEEN 1 AND 5", name="allowed_start_level"),
        CheckConstraint("phobia_grade IS NULL OR phobia_grade BETWEEN 1 AND 5", name="phobia_grade"),
        {"schema": "clinical"},
    )

    pseudonym_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    allowed_start_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    plan_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Self-reported phobia grade (1-5) from the BPMN step "Ajustar grado de fobia" (contract v1.1.0).
    phobia_grade: Mapped[int | None] = mapped_column(SmallInteger)
    phobia_grade_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Plazo de conservación: campo preparado, sin uso hasta que se decida D23.
    retain_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class PairingCode(Base):
    __tablename__ = "pairing_codes"
    __table_args__ = {"schema": "clinical"}

    id: Mapped[uuid.UUID] = _uuid_pk()
    pseudonym_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical.patients.pseudonym_id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = {"schema": "clinical"}

    id: Mapped[uuid.UUID] = _uuid_pk()
    pseudonym_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical.patients.pseudonym_id", ondelete="CASCADE"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(32), nullable=False)
    app_version: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    paired_at: Mapped[datetime] = _created_at()
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TherapySession(Base):
    """Sesión del visor. El ``id`` lo genera el visor (``sessionId``).

    Puede existir sin ``session_start`` (``has_start = false``) cuando los registros llegan desordenados.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("phobia_grade IS NULL OR phobia_grade BETWEEN 1 AND 5", name="phobia_grade"),
        Index("ix_sessions_pseudonym_started", "pseudonym_id", "started_at"),
        {"schema": "clinical"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    pseudonym_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical.patients.pseudonym_id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical.devices.id", ondelete="SET NULL")
    )
    has_start: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phobia_grade: Mapped[int | None] = mapped_column(SmallInteger)
    test_session: Mapped[bool | None] = mapped_column(Boolean)
    app_version: Mapped[str | None] = mapped_column(String(32))
    device_model: Mapped[str | None] = mapped_column(String(32))
    end_reason: Mapped[str | None] = mapped_column(String(32))
    level_reached: Mapped[int | None] = mapped_column(SmallInteger)
    total_duration_seconds: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _created_at()


class LevelRecord(Base):
    """``level_record`` del visor. El ``id`` es el ``recordId`` del sobre."""

    __tablename__ = "level_records"
    __table_args__ = {"schema": "clinical"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical.sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    criterion_met: Mapped[bool] = mapped_column(Boolean, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    permanence_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    min_distance_m: Mapped[float | None] = mapped_column(Float)
    avoidance_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = _created_at()


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint("tolerance_index BETWEEN 0 AND 1", name="tolerance_index"),
        CheckConstraint("recommendation IN ('advance', 'repeat', 'step_back')", name="recommendation"),
        {"schema": "clinical"},
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical.sessions.id", ondelete="CASCADE"), primary_key=True
    )
    method: Mapped[str] = mapped_column(String(32), primary_key=True)
    method_version: Mapped[str] = mapped_column(String(16), nullable=False)
    tolerance_index: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(16), nullable=False)
    basis: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    clinical_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_pseudonym_created", "pseudonym_id", "created_at"), {"schema": "clinical"})

    id: Mapped[uuid.UUID] = _uuid_pk()
    pseudonym_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical.patients.pseudonym_id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical.sessions.id", ondelete="SET NULL")
    )
    # Id del profesional autor. Sin clave foránea: es otro esquema.
    author_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InboundRecord(Base):
    """Libro de entrada de ``/device/records``: garantiza la idempotencia por ``recordId``."""

    __tablename__ = "inbound_records"
    __table_args__ = {"schema": "clinical"}

    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    pseudonym_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = _created_at()

"""Esquemas de cuentas, sesión web, datos propios y administración (contrato, sección 4)."""

import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, EmailStr, Field, StringConstraints

from app.schemas.common import CamelModel, Paginated, UtcDateTime

Role = Literal["patient", "professional", "admin"]

# Límites técnicos (no clínicos): el contrato no fija la política de contraseñas.
PASSWORD_MIN = 8
PASSWORD_MAX = 128

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Password = Annotated[str, Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)]
Email = Annotated[EmailStr, Field(max_length=320), AfterValidator(lambda v: v.strip().lower())]


class ConsentIn(CamelModel):
    accepted: bool
    consent_version: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class RegisterIn(CamelModel):
    full_name: FullName
    email: Email
    password: Password
    consent: ConsentIn | None = None


class RegisterOut(CamelModel):
    user_id: uuid.UUID
    role: Role


class LoginIn(CamelModel):
    email: Annotated[str, Field(min_length=1, max_length=320)]
    password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX)]


class UserRef(CamelModel):
    id: uuid.UUID
    role: Role


class LoginOut(CamelModel):
    access_token: str
    expires_in: int
    user: UserRef


class RefreshOut(CamelModel):
    access_token: str
    expires_in: int


class ConsentOut(CamelModel):
    consent_id: uuid.UUID
    consent_version: str
    granted_at: UtcDateTime
    withdrawn_at: UtcDateTime | None


class MeOut(CamelModel):
    id: uuid.UUID
    role: Role
    full_name: str | None
    email: str
    consents: list[ConsentOut]


class MePatch(CamelModel):
    full_name: FullName | None = None
    email: Email | None = None


class PasswordChangeIn(CamelModel):
    current_password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX)]
    new_password: Password


class AdminUserOut(CamelModel):
    id: uuid.UUID
    full_name: str | None
    email: str
    role: Role
    active: bool


class AdminUserPage(Paginated[AdminUserOut]):
    pass


class AdminUserCreate(CamelModel):
    full_name: FullName
    email: Email
    role: Role
    temporary_password: Password


class AdminUserPatch(CamelModel):
    role: Role | None = None
    active: bool | None = None
    # v1.1.0: full profile management.
    full_name: FullName | None = None
    email: Email | None = None


class AdminPasswordReset(CamelModel):
    temporary_password: Password


class AssignmentCreate(CamelModel):
    professional_id: uuid.UUID
    patient_id: uuid.UUID


class AssignmentOut(CamelModel):
    assignment_id: uuid.UUID
    professional_id: uuid.UUID
    patient_id: uuid.UUID
    professional_name: str | None
    patient_name: str | None
    active: bool
    created_at: UtcDateTime


class AssignmentPage(Paginated[AssignmentOut]):
    pass

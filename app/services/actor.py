"""Quién hace la petición, tal como lo ven los servicios."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    role: str


@dataclass(frozen=True)
class DeviceActor:
    device_id: uuid.UUID
    pseudonym_id: uuid.UUID

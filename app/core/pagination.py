"""Paginación por cursor opaco (``?limit=`` y ``?cursor=``), ordenada por fecha descendente e id."""

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Query

from app.core.errors import field_error

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(frozen=True)
class Page:
    limit: int
    after: tuple[datetime, uuid.UUID] | None


def encode_cursor(at: datetime, item_id: uuid.UUID) -> str:
    raw = json.dumps({"t": at.isoformat(), "id": str(item_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        at = datetime.fromisoformat(data["t"])
        if at.tzinfo is None:
            raise ValueError
        return at, uuid.UUID(data["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
        raise field_error("cursor", "invalid_format") from exc


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> Page:
    return Page(limit=limit, after=decode_cursor(cursor) if cursor else None)


def next_cursor(rows: list, page: Page, key) -> str | None:
    """``rows`` trae ``limit + 1`` elementos como mucho; si sobra uno, hay página siguiente."""
    if len(rows) <= page.limit:
        return None
    at, item_id = key(rows[page.limit - 1])
    return encode_cursor(at, item_id)

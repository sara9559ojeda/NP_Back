"""Ventana deslizante: la API usa PostgreSQL para compartir los contadores.

Solo se persisten hashes HMAC y fechas. SlidingWindowLimiter se conserva como
implementación aislada en memoria; no es el singleton usado por la API.
"""

import hashlib
import threading
import time
from collections import defaultdict, deque

from app.core.errors import ApiError


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def key(*parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def _prune(self, key: str, window: float, now: float) -> deque[float]:
        events = self._events[key]
        while events and now - events[0] >= window:
            events.popleft()
        return events

    def count(self, key: str, window: float) -> int:
        with self._lock:
            return len(self._prune(key, window, time.monotonic()))

    def hit(self, key: str, window: float) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, window, now).append(now)

    def check_and_hit(self, key: str, limit: int, window: float) -> None:
        """Cuenta un intento y lanza 429 si se supera el límite."""
        with self._lock:
            now = time.monotonic()
            events = self._prune(key, window, now)
            if len(events) >= limit:
                raise rate_limited(window - (now - events[0]))
            events.append(now)

    def ensure_below(self, key: str, limit: int, window: float) -> None:
        """Lanza 429 si ya hay ``limit`` eventos en la ventana, sin contar uno nuevo."""
        with self._lock:
            now = time.monotonic()
            events = self._prune(key, window, now)
            if len(events) >= limit:
                raise rate_limited(window - (now - events[0]))

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


def rate_limited(retry_after: float) -> ApiError:
    return ApiError(
        429,
        "RATE_LIMITED",
        "Demasiados intentos. Espera antes de volver a intentarlo.",
        headers={"Retry-After": str(max(1, int(retry_after) + 1))},
    )


class PostgresWindowLimiter:
    """Ventana compartida con transacción independiente y bloqueo por clave.

    Un fallo de login no revierte el contador junto a la transacción del usuario.
    Los advisory locks son transaccionales: funcionan con Transaction pooler.
    """

    @staticmethod
    def key(*parts: str) -> str:
        import hmac
        from app.core.config import get_settings
        return hmac.new(
            get_settings().secret_key.get_secret_value().encode(),
            "|".join(parts).encode(), hashlib.sha256,
        ).hexdigest()

    def _operate(self, key: str, window: float, *, hit: bool = False, limit: int | None = None) -> int:
        from sqlalchemy import text
        from app.db.session import get_engine
        lock_id = int.from_bytes(bytes.fromhex(key[:16]), "big", signed=True)
        with get_engine().begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
            now = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
            from datetime import timedelta
            cutoff = now - timedelta(seconds=window)
            conn.execute(text("DELETE FROM identity.rate_limit_events WHERE key_hash=:key AND occurred_at<=:cutoff"), {"key": key, "cutoff": cutoff})
            # Limpieza acotada de claves abandonadas; solo hashes y fechas.
            conn.execute(text("DELETE FROM identity.rate_limit_events WHERE id IN (SELECT id FROM identity.rate_limit_events WHERE occurred_at < :cutoff LIMIT 1000)"), {"cutoff": now - timedelta(days=1)})
            count, oldest = conn.execute(text("SELECT count(*), min(occurred_at) FROM identity.rate_limit_events WHERE key_hash=:key"), {"key": key}).one()
            if limit is not None and count >= limit:
                raise rate_limited(window - (now - oldest).total_seconds())
            if hit:
                conn.execute(text("INSERT INTO identity.rate_limit_events(key_hash, occurred_at) VALUES (:key, :now)"), {"key": key, "now": now})
            return count

    def count(self, key: str, window: float) -> int:
        return self._operate(key, window)

    def hit(self, key: str, window: float) -> None:
        self._operate(key, window, hit=True)

    def check_and_hit(self, key: str, limit: int, window: float) -> None:
        self._operate(key, window, hit=True, limit=limit)

    def ensure_below(self, key: str, limit: int, window: float) -> None:
        self._operate(key, window, limit=limit)

    def reset(self) -> None:
        """Solo usado por las pruebas, no se expone mediante la API."""
        from sqlalchemy import text
        from app.db.session import get_engine
        with get_engine().begin() as conn:
            conn.execute(text("TRUNCATE identity.rate_limit_events"))


limiter = PostgresWindowLimiter()

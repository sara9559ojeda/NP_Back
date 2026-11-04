"""Límite de frecuencia en memoria, por ventana deslizante.

Suficiente para un prototipo con una sola instancia de la API. Si se escalara a varias
instancias, habría que moverlo a un almacén compartido (por ejemplo, Redis).
Las claves son hashes: nunca se guarda un correo ni una IP en claro.
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


limiter = SlidingWindowLimiter()

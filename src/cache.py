from __future__ import annotations

import math
import time
from typing import Final, final

from opentelemetry import trace

_ABSENT: Final = (-math.inf, None)  # an absent key reads as one long expired

_tracer = trace.get_tracer(__name__)


@final
class MemoryCache[Payload]:
    """Values by key, each until its own deadline, with an internal span per call."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        """Start empty."""
        self._entries: dict[str, tuple[float, Payload]] = {}

    def get(self, key: str) -> Payload | None:
        """Return the payload under `key`, or None if it is absent or expired."""
        with _tracer.start_as_current_span("cache get", attributes={"cache.key": key}) as span:
            deadline, payload = self._entries.get(key, _ABSENT)
            hit = deadline > time.monotonic()
            span.set_attribute("cache.hit", hit)
            return payload if hit else None

    def set(self, key: str, payload: Payload, *, ttl_seconds: float) -> None:
        """Keep `payload` under `key` for `ttl_seconds`."""
        with _tracer.start_as_current_span("cache set", attributes={"cache.key": key}):
            self._entries[key] = (time.monotonic() + ttl_seconds, payload)

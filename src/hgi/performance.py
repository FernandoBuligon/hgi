"""Application-only observations; no gesture clock or effects on control."""

from collections import deque
from dataclasses import dataclass
from math import isfinite


class RateMeter:
    """Count events in a sliding one-second window, with bounded time history."""

    def __init__(self) -> None:
        self._events: deque[float] = deque()
        self._start: float | None = None
        self._last: float | None = None

    def _advance(self, now: float) -> None:
        if not isfinite(now) or (self._last is not None and now < self._last):
            raise ValueError("Observability time must be finite and monotonic")
        self._last = now
        if self._start is None:
            self._start = now
        while self._events and self._events[0] <= now - 1:
            self._events.popleft()

    def tick(self, now: float) -> None:
        """Record one actual completion, never one redraw of a cached result."""
        self._advance(now)
        self._events.append(now)

    def rate(self, now: float) -> float:
        """Report recent events/seconds; zero until a positive interval exists."""
        self._advance(now)
        assert self._start is not None
        elapsed = min(1.0, now - self._start)
        return len(self._events) / elapsed if elapsed > 0 else 0.0


@dataclass(frozen=True, slots=True)
class PipelineMetrics:
    """Milliseconds and delivered-sample throughput, never GPU-specific logic."""

    mode: str
    delegate: str
    inference_fps: float
    inference_ms: float
    capture_ms: float
    conversion_ms: float
    controller_ms: float
    overlay_ms: float

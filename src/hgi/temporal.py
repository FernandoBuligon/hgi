"""Synchronous gesture protection; one injected clock, no devices or timers."""

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from time import monotonic

from hgi.gesture_detector import Gesture, GestureObservation


@dataclass(frozen=True, slots=True)
class TemporalConfig:
    """Initial uncalibrated durations in seconds and dimensionless pinch ratios."""

    stabilization_seconds: float = 0.08
    enter_pinch_threshold: float = 0.25
    exit_pinch_threshold: float = 0.32
    click_cooldown_seconds: float = 0.3
    tracking_grace_seconds: float = 0.15

    def __post_init__(self) -> None:
        values = (
            self.stabilization_seconds,
            self.enter_pinch_threshold,
            self.exit_pinch_threshold,
            self.click_cooldown_seconds,
            self.tracking_grace_seconds,
        )
        if any(isinstance(v, bool) or not isfinite(v) or v < 0 for v in values):
            raise ValueError("Temporal parameters must be finite nonnegative numbers")
        if self.enter_pinch_threshold >= self.exit_pinch_threshold:
            raise ValueError("Pinch enter threshold must be less than exit threshold")


@dataclass(frozen=True, slots=True)
class TemporalDecision:
    """Stable label, permitted intentions and a request to discard motion state."""

    gesture: Gesture
    move: bool = False
    click: bool = False
    reset_motion: bool = False


class TemporalGestureFilter:
    """Duration-based confirmation, pinch hysteresis, cooldown and tracking grace.

    Start unarmed: a confirmed ratio at/above exit is required before clicking.
    Missing samples freeze stable state but cancel pending confirmation. Timeout
    clears interaction and requires release, preserving the last click deadline.
    A click blocked by cooldown is consumed, never queued. Use sequentially.
    """

    def __init__(
        self,
        config: TemporalConfig | None = None,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._config = config if config is not None else TemporalConfig()
        self._clock = clock
        self.reset()

    def reset(self) -> None:
        """Clear all temporal state, including cooldown, and require open rearming."""
        self._clear_interaction()
        self._last_click: float | None = None
        self._missing_since: float | None = None
        self._last_time: float | None = None

    def _clear_interaction(self) -> None:
        self._current = Gesture.UNKNOWN
        self._candidate: Gesture | None = None
        self._candidate_since: float | None = None
        self._pinch_closed = False
        self._armed = False
        self._release_since: float | None = None

    def _read_time(self) -> float:
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not isfinite(now)
        ):
            raise ValueError("Clock must return finite seconds")
        if self._last_time is not None and now < self._last_time:
            raise ValueError("Clock must not move backwards")
        self._last_time = now
        return now

    def _tracking_expired(self, now: float) -> bool:
        return (
            self._missing_since is not None
            and now >= self._missing_since + self._config.tracking_grace_seconds
        )

    def _missing(self, now: float) -> TemporalDecision:
        if self._missing_since is None:
            self._missing_since = now
        self._candidate = None
        self._candidate_since = None
        self._release_since = None
        expired = self._tracking_expired(now)
        if expired:
            self._clear_interaction()
        return TemporalDecision(self._current, reset_motion=expired)

    def _desired(
        self, observation: GestureObservation, ratio: float, now: float
    ) -> Gesture:
        if ratio <= self._config.enter_pinch_threshold:
            self._pinch_closed = True
        elif ratio >= self._config.exit_pinch_threshold:
            self._pinch_closed = False
        if ratio >= self._config.exit_pinch_threshold:
            if self._release_since is None:
                self._release_since = now
        else:
            self._release_since = None
        return Gesture.PINCH if self._pinch_closed else observation.pose

    def _confirm(self, desired: Gesture, now: float) -> bool:
        if desired is not self._candidate:
            self._candidate = desired
            self._candidate_since = now
        assert self._candidate_since is not None
        if now < self._candidate_since + self._config.stabilization_seconds:
            return False
        entered_pinch = desired is Gesture.PINCH and self._current is not Gesture.PINCH
        self._current = desired
        return entered_pinch

    def _click(self, entered_pinch: bool, now: float) -> bool:
        if not entered_pinch:
            return False
        cooldown_done = (
            self._last_click is None
            or now >= self._last_click + self._config.click_cooldown_seconds
        )
        click = self._armed and cooldown_done
        self._armed = False
        if click:
            self._last_click = now
        return click

    def _advance(self, observation: GestureObservation, now: float) -> TemporalDecision:
        ratio = observation.pinch_ratio
        if ratio is None:
            return self._missing(now)
        if isinstance(ratio, bool) or not isfinite(ratio) or ratio < 0:
            raise ValueError("Pinch ratio must be finite and nonnegative")
        if (
            not isinstance(observation.pose, Gesture)
            or observation.pose is Gesture.PINCH
        ):
            raise ValueError("Observation pose must be a non-pinch Gesture")
        expired = self._tracking_expired(now)
        if expired:
            self._clear_interaction()
        self._missing_since = None
        desired = self._desired(observation, ratio, now)
        entered_pinch = self._confirm(desired, now)
        click = self._click(entered_pinch, now)
        if (
            self._current is not Gesture.PINCH
            and self._release_since is not None
            and now >= self._release_since + self._config.stabilization_seconds
        ):
            self._armed = True
        inactive = self._current in (Gesture.UNKNOWN, Gesture.OPEN_HAND, Gesture.FIST)
        return TemporalDecision(
            self._current,
            move=self._current is Gesture.POINT and not self._pinch_closed,
            click=click,
            reset_motion=expired or inactive,
        )

    def update(self, observation: GestureObservation) -> TemporalDecision:
        """Read the clock once and return permissions, never cursor commands.

        On invalid input or a failed/regressing clock, clear state and re-raise
        the original exception. No callback, background reset or retry exists.
        """
        try:
            return self._advance(observation, self._read_time())
        except Exception:
            # Cleanup only: errors remain visible to the caller.
            self.reset()
            raise

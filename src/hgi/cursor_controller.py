"""Opt-in virtual cursor mapping; timing belongs to the injected temporal filter."""

from dataclasses import dataclass

from hgi.cursor import ControlState, CursorAction, CursorCommand, DryRunCursorSink
from hgi.geometry import (
    Point2D,
    Region2D,
    clamp,
    map_camera_to_screen,
    normalized_to_pixels,
)
from hgi.gesture_detector import Gesture, GestureDetector
from hgi.hand_landmarks import DetectedHand, HandLandmark
from hgi.smoothing import ExponentialSmoother
from hgi.temporal import TemporalDecision, TemporalGestureFilter


@dataclass(frozen=True, slots=True)
class CursorConfig:
    """Explicit logical screen and normalized active camera region.

    Initial margins are 10% per side; alpha is per POINT update. mirror_x=True
    expects unmirrored camera landmarks, reflecting relative to active_region.
    Disable it if the input image has already been mirrored. No device is queried.
    """

    screen_width: int
    screen_height: int
    active_region: Region2D = Region2D(0.1, 0.1, 0.9, 0.9)
    mirror_x: bool = True
    smoothing_alpha: float = 0.25

    def __post_init__(self) -> None:
        normalized_to_pixels(Point2D(0.0, 0.0), self.screen_width, self.screen_height)
        region = self.active_region
        if not (
            0 <= region.left < region.right <= 1
            and 0 <= region.top < region.bottom <= 1
        ):
            raise ValueError("Active region must be inside normalized bounds [0, 1]")
        if not isinstance(self.mirror_x, bool):
            raise ValueError("mirror_x must be a boolean")
        ExponentialSmoother(self.smoothing_alpha)


class CursorController:
    """Start DISABLED; map temporal permissions to intentions only after enable.

    Own EMA/position, not gesture timing. Missing hands never move or click.
    Short tracking gaps preserve motion; the filter requests resets on timeout
    or stable inactivity. Errors disable and propagate. Use sequentially for
    one hand; only DryRunCursorSink output is supported in this phase.
    """

    def __init__(
        self,
        config: CursorConfig,
        *,
        sink: DryRunCursorSink | None = None,
        detector: GestureDetector | None = None,
        temporal: TemporalGestureFilter | None = None,
    ) -> None:
        if sink is not None and not isinstance(sink, DryRunCursorSink):
            raise TypeError("This phase requires a DryRunCursorSink")
        self._config = config
        self._sink = sink if sink is not None else DryRunCursorSink()
        self._detector = detector if detector is not None else GestureDetector()
        self._smoother = ExponentialSmoother(config.smoothing_alpha)
        self._temporal = temporal if temporal is not None else TemporalGestureFilter()
        self._position: Point2D | None = None
        self._state = ControlState.DISABLED

    @property
    def config(self) -> CursorConfig:
        """Return the immutable configuration supplied by the caller."""
        return self._config

    @property
    def sink(self) -> DryRunCursorSink:
        """Expose the output boundary for inspection; the default is dry-run."""
        return self._sink

    @property
    def state(self) -> ControlState:
        """Return explicit opt-in state; detecting a hand never enables control."""
        return self._state

    def enable(self) -> None:
        """Opt in from neutral/unarmed state; repeated enable calls do nothing."""
        if self._state is ControlState.DISABLED:
            self.reset()
            self._state = ControlState.ENABLED

    def disable(self) -> None:
        """Disarm, cancel pending gestures and clear motion without emitting."""
        self._state = ControlState.DISABLED
        self._temporal.reset()
        self._clear_motion()

    def _map_indicator(self, hand: DetectedHand) -> Point2D:
        tip = hand.landmarks[HandLandmark.INDEX_FINGER_TIP]
        return map_camera_to_screen(
            Point2D(tip.x, tip.y),
            self._config.active_region,
            self._config.screen_width,
            self._config.screen_height,
            mirror_x=self._config.mirror_x,
        )

    def _move(self, hand: DetectedHand) -> CursorCommand:
        smoothed = self._smoother.update(self._map_indicator(hand))
        self._position = Point2D(
            clamp(smoothed.x, 0.0, self._config.screen_width - 1),
            clamp(smoothed.y, 0.0, self._config.screen_height - 1),
        )
        return CursorCommand(
            CursorAction.MOVE, self._position.x, self._position.y, Gesture.POINT
        )

    def _command(
        self, hand: DetectedHand | None, decision: TemporalDecision
    ) -> CursorCommand:
        if decision.reset_motion:
            self._clear_motion()
        if hand is not None and decision.click:
            if self._position is None:
                self._position = self._map_indicator(hand)
            return CursorCommand(
                CursorAction.CLICK, self._position.x, self._position.y, Gesture.PINCH
            )
        if hand is not None and decision.move:
            return self._move(hand)
        return CursorCommand(CursorAction.NONE, gesture=decision.gesture)

    def update(self, hand: DetectedHand | None) -> CursorCommand:
        """Observe/filter only while enabled, then return and emit one intention.

        Any processing/output exception disables the interaction and propagates
        unchanged. No retry or pending click survives. NONE records disabled or
        inactive updates without controlling anything. No clock is read here.
        """
        try:
            command = CursorCommand(CursorAction.NONE, gesture=Gesture.UNKNOWN)
            if self._state is ControlState.ENABLED:
                decision = self._temporal.update(self._detector.observe(hand))
                command = self._command(hand, decision)
            self._sink.emit(command)
            return command
        except Exception:
            # Safety boundary: clean up, never hide the original failure.
            self.disable()
            raise

    def _clear_motion(self) -> None:
        self._smoother.reset()
        self._position = None

    def reset(self) -> None:
        """Disable and clear all interaction state, preserving output history."""
        self.disable()

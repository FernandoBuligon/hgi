"""Virtual cursor pipeline over HGI data; no display, devices or clock."""

from dataclasses import dataclass

from hgi.cursor import CursorAction, CursorCommand, CursorSink, DryRunCursorSink
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
    """Recognize, map, smooth and emit intentions to a dry-run sink by default.

    POINT alone moves. PINCH clicks once on entry at the last virtual position,
    or the mapped indicator if no position exists. A held PINCH emits NONE.
    Inactivity clears motion; reset/tracking loss also rearms the logical edge.
    This edge rule is not a safety gate for a future real mouse backend.
    Use one instance sequentially for one tracked hand; identity is not inferred.
    """

    def __init__(
        self,
        config: CursorConfig,
        *,
        sink: CursorSink | None = None,
        detector: GestureDetector | None = None,
    ) -> None:
        self._config = config
        self._sink = sink if sink is not None else DryRunCursorSink()
        self._detector = detector if detector is not None else GestureDetector()
        self._smoother = ExponentialSmoother(config.smoothing_alpha)
        self._position: Point2D | None = None
        self._previous_gesture = Gesture.UNKNOWN

    @property
    def config(self) -> CursorConfig:
        """Return the immutable configuration supplied by the caller."""
        return self._config

    @property
    def sink(self) -> CursorSink:
        """Expose the output boundary for inspection; the default is dry-run."""
        return self._sink

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

    def update(self, hand: DetectedHand | None) -> CursorCommand:
        """Return and emit exactly one command; NONE is an observable idle update.

        Invalid geometry resets state and propagates ValueError, emitting nothing.
        PINCH freezes the position and EMA until POINT resumes. Other gestures
        and absence discard motion. Output errors propagate without retrying.
        """
        try:
            gesture = self._detector.detect(hand)
        except ValueError:
            self.reset()
            raise
        if hand is not None and gesture is Gesture.POINT:
            command = self._move(hand)
        elif hand is not None and gesture is Gesture.PINCH:
            command = CursorCommand(CursorAction.NONE, gesture=gesture)
            if self._previous_gesture is not Gesture.PINCH:
                if self._position is None:
                    self._position = self._map_indicator(hand)
                command = CursorCommand(
                    CursorAction.CLICK, self._position.x, self._position.y, gesture
                )
        else:
            self.reset()
            command = CursorCommand(CursorAction.NONE, gesture=gesture)
        self._previous_gesture = gesture
        self._sink.emit(command)
        return command

    def reset(self) -> None:
        """Clear EMA, position and gesture edge, preserving the sink's history."""
        self._smoother.reset()
        self._position = None
        self._previous_gesture = Gesture.UNKNOWN

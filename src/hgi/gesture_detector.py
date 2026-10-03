"""MVP semantic gesture classification, without actions or temporal state."""

from dataclasses import dataclass
from enum import Enum

from hgi.finger_state import (
    FingerState,
    GestureConfig,
    detect_fingers,
    pinch_ratio,
    thumb_vertical_direction,
)
from hgi.hand_landmarks import DetectedHand


class Gesture(Enum):
    """Semantic labels supported by HGI's geometry-based recognizer."""

    UNKNOWN = "UNKNOWN"
    POINT = "POINT"
    PINCH = "PINCH"
    THUMBS_UP = "THUMBS_UP"
    THUMBS_DOWN = "THUMBS_DOWN"
    PEACE = "PEACE"
    ROCK = "ROCK"
    OPEN_HAND = "OPEN_HAND"
    FIST = "FIST"


@dataclass(frozen=True, slots=True)
class GestureObservation:
    """Raw label, non-pinch finger pose and ratio from one validated hand.

    A missing ratio means no hand. The temporal layer owns its hysteresis
    thresholds; pose avoids recovering a non-pinch label from a collapsed raw
    PINCH. No geometry is recalculated by consumers of this observation.
    """

    raw: Gesture
    pose: Gesture
    pinch_ratio: float | None


def _finger_pose(state: FingerState, thumb_direction: int) -> Gesture:
    fingers = (state.thumb, state.index, state.middle, state.ring, state.pinky)
    if state.index and state.pinky and not any((state.thumb, state.middle, state.ring)):
        return Gesture.ROCK
    if state.index and state.middle and not any((state.thumb, state.ring, state.pinky)):
        return Gesture.PEACE
    if state.thumb and not any((state.index, state.middle, state.ring, state.pinky)):
        if thumb_direction < 0:
            return Gesture.THUMBS_UP
        if thumb_direction > 0:
            return Gesture.THUMBS_DOWN
    if state.index and not any((state.thumb, state.middle, state.ring, state.pinky)):
        return Gesture.POINT
    if all(fingers):
        return Gesture.OPEN_HAND
    if not any(fingers):
        return Gesture.FIST
    return Gesture.UNKNOWN


class GestureDetector:
    """Stateless per-hand rules; a label is not an action or click event.

    PINCH wins over every finger pose. Invalid geometry raises ValueError;
    absence or a valid unrecognized pose yields UNKNOWN. No hysteresis,
    debounce, cooldown, timestamps or hand identity is maintained.
    """

    def __init__(self, config: GestureConfig | None = None) -> None:
        self._config = config if config is not None else GestureConfig()

    @property
    def config(self) -> GestureConfig:
        """Return the immutable thresholds used by this detector."""
        return self._config

    def detect(self, hand: DetectedHand | None) -> Gesture:
        """Return one semantic label from internal hand data, without side effects."""
        return self.observe(hand).raw

    def observe(self, hand: DetectedHand | None) -> GestureObservation:
        """Measure once, preserving pose and ratio for the temporal boundary."""
        if hand is None:
            return GestureObservation(Gesture.UNKNOWN, Gesture.UNKNOWN, None)
        state = detect_fingers(hand, self._config)
        ratio = pinch_ratio(hand, self._config)
        pose = _finger_pose(state, thumb_vertical_direction(hand, self._config))
        raw = Gesture.PINCH if ratio <= self._config.pinch_threshold else pose
        return GestureObservation(raw, pose, ratio)

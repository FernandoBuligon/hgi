"""MVP semantic gesture classification, without actions or temporal state."""

from enum import Enum

from hgi.finger_state import GestureConfig, detect_fingers, pinch_ratio
from hgi.hand_landmarks import DetectedHand


class Gesture(Enum):
    """Only the five semantic labels supported by this recognition phase."""

    UNKNOWN = "UNKNOWN"
    POINT = "POINT"
    PINCH = "PINCH"
    OPEN_HAND = "OPEN_HAND"
    FIST = "FIST"


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
        if hand is None:
            return Gesture.UNKNOWN
        state = detect_fingers(hand, self._config)
        if pinch_ratio(hand, self._config) <= self._config.pinch_threshold:
            return Gesture.PINCH
        fingers = (state.thumb, state.index, state.middle, state.ring, state.pinky)
        if state.index and not any(
            (state.thumb, state.middle, state.ring, state.pinky)
        ):
            return Gesture.POINT
        if all(fingers):
            return Gesture.OPEN_HAND
        if not any(fingers):
            return Gesture.FIST
        return Gesture.UNKNOWN

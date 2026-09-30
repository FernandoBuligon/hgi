"""Immutable HGI hand data; no dependency on MediaPipe or image libraries."""

from dataclasses import dataclass
from enum import IntEnum
from math import isfinite
from typing import Literal


class HandLandmark(IntEnum):
    """The official 21 Hand Landmarker indices, in detector output order."""

    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_FINGER_MCP = 5
    INDEX_FINGER_PIP = 6
    INDEX_FINGER_DIP = 7
    INDEX_FINGER_TIP = 8
    MIDDLE_FINGER_MCP = 9
    MIDDLE_FINGER_PIP = 10
    MIDDLE_FINGER_DIP = 11
    MIDDLE_FINGER_TIP = 12
    RING_FINGER_MCP = 13
    RING_FINGER_PIP = 14
    RING_FINGER_DIP = 15
    RING_FINGER_TIP = 16
    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20


@dataclass(frozen=True, slots=True)
class NormalizedLandmark:
    """Finite image-space XYZ prediction, without clipping detector output.

    X/Y are normalized by image width/height. Z is relative depth with origin
    at the wrist and roughly X's scale; it is not a distance in meters.
    Predictions may extend outside the frame. Preserve them for later logic.
    """

    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.x, self.y, self.z)):
            raise ValueError("Landmark coordinates must be finite")


@dataclass(frozen=True, slots=True)
class DetectedHand:
    """Exactly 21 landmarks and optional handedness classification metadata.

    The score is confidence in Left/Right, not in each landmark or detection.
    A hand has no persistent identity; ordering across frames is not guaranteed.
    """

    landmarks: tuple[NormalizedLandmark, ...]
    handedness: Literal["Left", "Right"] | None = None
    handedness_score: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.landmarks, tuple):
            raise TypeError("Landmarks must be an immutable tuple")
        if len(self.landmarks) != len(HandLandmark):
            raise ValueError("A detected hand must have exactly 21 landmarks")
        if not all(isinstance(point, NormalizedLandmark) for point in self.landmarks):
            raise TypeError("Landmarks must contain NormalizedLandmark instances")
        if self.handedness not in (None, "Left", "Right"):
            raise ValueError("Invalid handedness: expected Left, Right or None")
        score = self.handedness_score
        if score is not None and (not isfinite(score) or not 0 <= score <= 1):
            raise ValueError("Handedness score must be finite and in [0, 1]")

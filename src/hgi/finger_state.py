"""Stateless, image-plane finger measurements over internal HGI hand types."""

from dataclasses import dataclass
from math import isfinite

from hgi.geometry import Point2D, distance, normalized_distance
from hgi.hand_landmarks import DetectedHand, HandLandmark


@dataclass(frozen=True, slots=True)
class GestureConfig:
    """Initial MVP thresholds, not calibrated recognition guarantees.

    aspect_ratio is image width / height, supplied by the caller. The minimum
    reference/segment length is in height-normalized image units, not pixels.
    """

    pinch_threshold: float = 0.25
    extension_ratio: float = 0.9
    thumb_spread_ratio: float = 0.2
    min_reference_distance: float = 1e-6
    image_aspect_ratio: float = 1.0

    def __post_init__(self) -> None:
        values = (
            self.pinch_threshold,
            self.extension_ratio,
            self.thumb_spread_ratio,
            self.min_reference_distance,
            self.image_aspect_ratio,
        )
        if any(isinstance(value, bool) or not isfinite(value) for value in values):
            raise ValueError("Gesture thresholds must be finite numbers, not booleans")
        if self.pinch_threshold < 0 or self.thumb_spread_ratio < 0:
            raise ValueError("Pinch and thumb spread thresholds must be nonnegative")
        if not 0 < self.extension_ratio <= 1:
            raise ValueError("Extension ratio must satisfy 0 < ratio <= 1")
        if self.min_reference_distance <= 0 or self.image_aspect_ratio <= 0:
            raise ValueError(
                "Minimum reference distance and aspect ratio must be positive"
            )


@dataclass(frozen=True, slots=True)
class FingerState:
    """Named extension flags; thumb uses a separate spread condition."""

    thumb: bool
    index: bool
    middle: bool
    ring: bool
    pinky: bool


def _hand_geometry(
    hand: DetectedHand, config: GestureConfig
) -> tuple[tuple[Point2D, ...], float]:
    points = tuple(
        Point2D(p.x * config.image_aspect_ratio, p.y) for p in hand.landmarks
    )
    reference = distance(
        points[HandLandmark.WRIST], points[HandLandmark.MIDDLE_FINGER_MCP]
    )
    if reference <= config.min_reference_distance:
        raise ValueError("Hand reference distance is degenerate or too small")
    return points, reference


def _straightness(
    points: tuple[Point2D, ...], chain: tuple[HandLandmark, ...], config: GestureConfig
) -> float:
    lengths = [
        distance(points[a], points[b]) for a, b in zip(chain, chain[1:], strict=False)
    ]
    if any(length <= config.min_reference_distance for length in lengths):
        raise ValueError("Finger segment is degenerate or too small")
    return normalized_distance(points[chain[0]], points[chain[-1]], sum(lengths))


_LONG_FINGER_CHAINS = (
    (
        HandLandmark.INDEX_FINGER_MCP,
        HandLandmark.INDEX_FINGER_PIP,
        HandLandmark.INDEX_FINGER_DIP,
        HandLandmark.INDEX_FINGER_TIP,
    ),
    (
        HandLandmark.MIDDLE_FINGER_MCP,
        HandLandmark.MIDDLE_FINGER_PIP,
        HandLandmark.MIDDLE_FINGER_DIP,
        HandLandmark.MIDDLE_FINGER_TIP,
    ),
    (
        HandLandmark.RING_FINGER_MCP,
        HandLandmark.RING_FINGER_PIP,
        HandLandmark.RING_FINGER_DIP,
        HandLandmark.RING_FINGER_TIP,
    ),
    (
        HandLandmark.PINKY_MCP,
        HandLandmark.PINKY_PIP,
        HandLandmark.PINKY_DIP,
        HandLandmark.PINKY_TIP,
    ),
)


def detect_fingers(
    hand: DetectedHand, config: GestureConfig | None = None
) -> FingerState:
    """Classify extension using corrected XY distances, never tip.y < pip.y.

    Long fingers must be nearly straight and extend away from the wrist.
    Thumb MCP/IP/tip must be nearly straight and spread away from index MCP.
    Geometry is reflection invariant; handedness and its score are not needed.
    Reject degenerate geometry instead of turning invalid data into a fist.
    """
    config = config if config is not None else GestureConfig()
    points, reference = _hand_geometry(hand, config)
    wrist = points[HandLandmark.WRIST]
    index, middle, ring, pinky = (
        _straightness(points, chain, config) >= config.extension_ratio
        and distance(wrist, points[chain[-1]]) > distance(wrist, points[chain[1]])
        for chain in _LONG_FINGER_CHAINS
    )
    thumb_chain = (
        HandLandmark.THUMB_MCP,
        HandLandmark.THUMB_IP,
        HandLandmark.THUMB_TIP,
    )
    index_base = points[HandLandmark.INDEX_FINGER_MCP]
    spread = (
        distance(points[HandLandmark.THUMB_TIP], index_base)
        - distance(points[HandLandmark.THUMB_IP], index_base)
    ) / reference
    thumb = (
        _straightness(points, thumb_chain, config) >= config.extension_ratio
        and spread >= config.thumb_spread_ratio
    )
    return FingerState(thumb, index, middle, ring, pinky)

"""Small semantic gesture suite on synthetic HGI hands, without mocks."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from hgi.finger_state import GestureConfig, detect_fingers, pinch_ratio
from hgi.gesture_detector import Gesture, GestureDetector
from hgi.hand_landmarks import DetectedHand, HandLandmark, NormalizedLandmark


def with_pinch(hand: DetectedHand, gap: float) -> DetectedHand:
    """Move thumb tip a known horizontal gap from index tip."""
    points = list(hand.landmarks)
    tip = points[HandLandmark.INDEX_FINGER_TIP]
    points[HandLandmark.THUMB_TIP] = NormalizedLandmark(tip.x + gap, tip.y, tip.z)
    return replace(hand, landmarks=tuple(points))


@pytest.mark.parametrize(
    "extended,expected",
    [
        (("index",), Gesture.POINT),
        (("thumb", "index", "middle", "ring", "pinky"), Gesture.OPEN_HAND),
        ((), Gesture.FIST),
        (("index", "middle"), Gesture.UNKNOWN),
        (("thumb", "index"), Gesture.UNKNOWN),
    ],
)
def test_supported_semantic_gestures(
    hand_factory: Callable[..., DetectedHand],
    extended: tuple[str, ...],
    expected: Gesture,
) -> None:
    assert GestureDetector().detect(hand_factory(*extended)) is expected


@pytest.mark.parametrize(
    "ratio,expected_pinch", [(0.125, True), (0.25, True), (0.5, False)]
)
def test_normalized_pinch_threshold_is_inclusive(
    hand_factory: Callable[..., DetectedHand],
    ratio: float,
    expected_pinch: bool,
) -> None:
    hand = with_pinch(hand_factory("index"), gap=ratio * 0.25)
    assert pinch_ratio(hand) == pytest.approx(ratio)
    assert (GestureDetector().detect(hand) is Gesture.PINCH) is expected_pinch


def test_pinch_priority_over_point_without_requiring_extended_thumb(
    hand_factory: Callable[..., DetectedHand],
) -> None:
    hand = with_pinch(hand_factory("index"), gap=0)
    state = detect_fingers(hand)
    assert state.index and not any((state.thumb, state.middle, state.ring, state.pinky))
    assert GestureDetector().detect(hand) is Gesture.PINCH


@pytest.mark.parametrize("scale", [0.5, 2.0])
def test_uniform_hand_scaling_preserves_ratio_and_gesture(
    hand_factory: Callable[..., DetectedHand],
    scale: float,
) -> None:
    hand = with_pinch(hand_factory("index", scale=scale), gap=0.03125 * scale)
    assert pinch_ratio(hand) == pytest.approx(0.125)
    assert GestureDetector().detect(hand) is Gesture.PINCH


def test_aspect_ratio_corrects_pinch_and_threshold_is_configurable(
    hand_factory: Callable[..., DetectedHand],
) -> None:
    hand = with_pinch(hand_factory("index", aspect_ratio=2), gap=0.015625)
    config = GestureConfig(image_aspect_ratio=2)
    assert pinch_ratio(hand, config) == pytest.approx(0.125)
    assert GestureDetector(config).detect(hand) is Gesture.PINCH
    assert (
        GestureDetector(replace(config, pinch_threshold=0.1)).detect(hand)
        is not Gesture.PINCH
    )


@pytest.mark.parametrize("reference", [0.0, 0.5e-6])
def test_degenerate_reference_is_rejected_not_recognized(
    hand_factory: Callable[..., DetectedHand],
    reference: float,
) -> None:
    hand = hand_factory()
    points = list(hand.landmarks)
    wrist = points[HandLandmark.WRIST]
    points[HandLandmark.MIDDLE_FINGER_MCP] = NormalizedLandmark(
        wrist.x, wrist.y - reference, wrist.z
    )
    hand = replace(hand, landmarks=tuple(points))
    with pytest.raises(ValueError, match="reference"):
        pinch_ratio(hand)
    with pytest.raises(ValueError, match="reference"):
        GestureDetector().detect(hand)


def test_absence_and_repeated_calls_have_no_temporal_state(
    hand_factory: Callable[..., DetectedHand],
) -> None:
    detector = GestureDetector()
    point = hand_factory("index", handedness=None)
    pinched = with_pinch(point, gap=0)
    assert detector.detect(None) is Gesture.UNKNOWN
    assert detector.detect(pinched) is Gesture.PINCH
    assert detector.detect(pinched) is Gesture.PINCH
    assert detector.detect(point) is Gesture.POINT
    assert (
        detector.detect(replace(point, handedness="Left", handedness_score=0.1))
        is Gesture.POINT
    )

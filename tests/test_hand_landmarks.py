"""Contracts for HGI hand data, without NumPy or MediaPipe objects."""

from dataclasses import FrozenInstanceError

import pytest

from hgi.hand_landmarks import DetectedHand, HandLandmark, NormalizedLandmark


def points() -> tuple[NormalizedLandmark, ...]:
    return tuple(NormalizedLandmark(i / 20, 0.5, -i / 100) for i in range(21))


def test_official_landmark_order() -> None:
    names = [
        "WRIST",
        "THUMB_CMC",
        "THUMB_MCP",
        "THUMB_IP",
        "THUMB_TIP",
        "INDEX_FINGER_MCP",
        "INDEX_FINGER_PIP",
        "INDEX_FINGER_DIP",
        "INDEX_FINGER_TIP",
        "MIDDLE_FINGER_MCP",
        "MIDDLE_FINGER_PIP",
        "MIDDLE_FINGER_DIP",
        "MIDDLE_FINGER_TIP",
        "RING_FINGER_MCP",
        "RING_FINGER_PIP",
        "RING_FINGER_DIP",
        "RING_FINGER_TIP",
        "PINKY_MCP",
        "PINKY_PIP",
        "PINKY_DIP",
        "PINKY_TIP",
    ]
    assert [(item.name, item.value) for item in HandLandmark] == [
        (name, i) for i, name in enumerate(names)
    ]


def test_hand_preserves_xyz_indexing_and_optional_metadata() -> None:
    hand = DetectedHand(points(), handedness="Right", handedness_score=0.9)
    assert hand.landmarks[HandLandmark.INDEX_FINGER_TIP] == NormalizedLandmark(
        0.4, 0.5, -0.08
    )
    assert hand.handedness == "Right"
    assert hand.handedness_score == 0.9
    unknown = DetectedHand(points())
    assert unknown.handedness is None
    assert unknown.handedness_score is None


def test_hand_and_points_are_immutable() -> None:
    hand = DetectedHand(points())
    with pytest.raises(FrozenInstanceError):
        hand.handedness = "Left"
    with pytest.raises(FrozenInstanceError):
        hand.landmarks[0].x = 1.0


@pytest.mark.parametrize("count", [20, 22])
def test_hand_requires_exactly_21_points(count: int) -> None:
    with pytest.raises(ValueError, match="21"):
        DetectedHand(tuple(NormalizedLandmark(0, 0, 0) for _ in range(count)))


@pytest.mark.parametrize(
    "coordinates", [(float("nan"), 0, 0), (0, float("inf"), 0), (0, 0, -float("inf"))]
)
def test_coordinates_must_be_finite(coordinates: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError, match="finite"):
        NormalizedLandmark(*coordinates)


def test_predictions_outside_frame_are_preserved_without_clipping() -> None:
    assert NormalizedLandmark(-0.1, 1.1, -0.3).x == -0.1


@pytest.mark.parametrize("score", [-0.1, 1.1, float("nan")])
def test_handedness_score_must_be_valid(score: float) -> None:
    with pytest.raises(ValueError, match="score"):
        DetectedHand(points(), handedness="Left", handedness_score=score)


def test_unknown_handedness_label_is_rejected() -> None:
    with pytest.raises(ValueError, match="handedness"):
        DetectedHand(points(), handedness="Up")


def test_hand_requires_immutable_landmark_collection() -> None:
    with pytest.raises(TypeError, match="tuple"):
        DetectedHand(list(points()))
    with pytest.raises(TypeError, match="NormalizedLandmark"):
        DetectedHand(tuple((0, 0, 0) for _ in range(21)))

"""Finger heuristics on synthetic internal landmarks, without image libraries."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace

import pytest

from hgi.finger_state import FingerState, GestureConfig, detect_fingers
from hgi.hand_landmarks import DetectedHand, HandLandmark, NormalizedLandmark


@pytest.mark.parametrize(
    "extended,expected",
    [
        ((), (False, False, False, False, False)),
        (("index",), (False, True, False, False, False)),
        (("index", "middle"), (False, True, True, False, False)),
        (("thumb", "index", "middle", "ring", "pinky"), (True, True, True, True, True)),
    ],
)
def test_named_finger_states(
    hand_factory: Callable[..., DetectedHand],
    extended: tuple[str, ...],
    expected: tuple[bool, bool, bool, bool, bool],
) -> None:
    state = detect_fingers(hand_factory(*extended))
    assert (state.thumb, state.index, state.middle, state.ring, state.pinky) == expected
    with pytest.raises(FrozenInstanceError):
        state.index = False


def test_thumb_uses_same_geometry_for_left_right_and_missing_metadata(
    hand_factory: Callable[..., DetectedHand],
) -> None:
    for handedness in ("Left", "Right", None):
        hand = hand_factory("thumb", handedness=handedness)
        assert hand.handedness_score is None
        assert detect_fingers(hand) == FingerState(True, False, False, False, False)


@pytest.mark.parametrize("rotation", [90, 180])
def test_in_plane_rotation_does_not_depend_on_tip_y(
    hand_factory: Callable[..., DetectedHand],
    rotation: float,
) -> None:
    hand = hand_factory("thumb", "index", rotation=rotation)
    assert detect_fingers(hand) == FingerState(True, True, False, False, False)


def test_straight_thumb_near_index_base_is_not_open(
    hand_factory: Callable[..., DetectedHand],
) -> None:
    hand = hand_factory("thumb")
    points = list(hand.landmarks)
    points[HandLandmark.THUMB_IP] = NormalizedLandmark(0.375, 0.65625, 0)
    points[HandLandmark.THUMB_TIP] = NormalizedLandmark(0.375, 0.625, 0)
    assert not detect_fingers(replace(hand, landmarks=tuple(points))).thumb


def test_aspect_correction_and_configurable_thumb_spread(
    hand_factory: Callable[..., DetectedHand],
) -> None:
    hand = hand_factory("thumb", "index", aspect_ratio=2.0)
    assert detect_fingers(hand, GestureConfig(image_aspect_ratio=2)) == FingerState(
        True, True, False, False, False
    )
    assert not detect_fingers(
        hand,
        GestureConfig(
            image_aspect_ratio=2,
            thumb_spread_ratio=0.5,
        ),
    ).thumb


def test_coincident_joint_is_rejected(
    hand_factory: Callable[..., DetectedHand],
) -> None:
    hand = hand_factory("index")
    points = list(hand.landmarks)
    points[HandLandmark.INDEX_FINGER_PIP] = points[HandLandmark.INDEX_FINGER_MCP]
    with pytest.raises(ValueError, match="segment"):
        detect_fingers(replace(hand, landmarks=tuple(points)))


def test_invalid_hand_size_is_rejected_by_internal_type(
    hand_factory: Callable[..., DetectedHand],
) -> None:
    hand = hand_factory()
    with pytest.raises(ValueError, match="21"):
        replace(hand, landmarks=hand.landmarks[:-1])


@pytest.mark.parametrize(
    "options",
    [
        {"pinch_threshold": -0.1},
        {"extension_ratio": 1.1},
        {"extension_ratio": True},
        {"thumb_spread_ratio": float("nan")},
        {"min_reference_distance": 0},
        {"image_aspect_ratio": float("inf")},
    ],
)
def test_invalid_configuration_is_rejected(options: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        GestureConfig(**options)


def test_configuration_is_immutable() -> None:
    config = GestureConfig()
    with pytest.raises(FrozenInstanceError):
        config.pinch_threshold = 0.5

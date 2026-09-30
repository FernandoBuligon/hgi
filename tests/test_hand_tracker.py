"""Adapter contracts; only the external MediaPipe boundary is replaced."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from hgi.hand_landmarks import DetectedHand, HandLandmark, NormalizedLandmark
from hgi.hand_tracker import HandTracker, HandTrackerError


def raw_hand(offset: float = 0.0) -> list[SimpleNamespace]:
    return [SimpleNamespace(x=i / 20 + offset, y=0.5, z=-i / 100) for i in range(21)]


def result(
    landmarks: list[list[SimpleNamespace]],
    handedness: list[list[SimpleNamespace]] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(hand_landmarks=landmarks, handedness=handedness or [])


@pytest.fixture
def boundary(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    detector = Mock(spec=["detect", "close"])
    detector.detect.return_value = result([])
    factory = Mock(return_value=detector)
    base_options = Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
    base_options.Delegate = SimpleNamespace(CPU="CPU")
    mp = SimpleNamespace(
        tasks=SimpleNamespace(
            BaseOptions=base_options,
            vision=SimpleNamespace(
                HandLandmarker=SimpleNamespace(create_from_options=factory),
                HandLandmarkerOptions=lambda **kwargs: SimpleNamespace(**kwargs),
                RunningMode=SimpleNamespace(IMAGE="IMAGE"),
            ),
        ),
        ImageFormat=SimpleNamespace(SRGB="SRGB"),
        Image=Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs)),
    )
    monkeypatch.setitem(sys.modules, "mediapipe", mp)
    return SimpleNamespace(mp=mp, detector=detector, factory=factory)


@pytest.fixture
def model(tmp_path: Path) -> Path:
    path = tmp_path / "fake.task"
    path.write_bytes(b"Boundary fake, not a usable MediaPipe model")
    return path


def test_image_mode_options_rgb_and_contiguous_input(
    boundary: SimpleNamespace,
    model: Path,
) -> None:
    frame = np.arange(6 * 8 * 3, dtype=np.uint8).reshape(6, 8, 3)[:, ::2]
    original = frame.copy()
    with HandTracker(
        model,
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.7,
    ) as tracker:
        assert tracker.process(frame) == ()
        options = boundary.factory.call_args.args[0]
        assert options.base_options.model_asset_path == str(model.resolve())
        assert options.base_options.delegate == "CPU"
        assert options.running_mode == "IMAGE"
        assert options.num_hands == 2
        assert options.min_hand_detection_confidence == 0.6
        assert options.min_hand_presence_confidence == 0.7
        image = boundary.detector.detect.call_args.args[0]
        assert image.image_format == "SRGB"
        assert image.data.flags.c_contiguous
        np.testing.assert_array_equal(image.data, original)
    boundary.detector.close.assert_called_once()
    np.testing.assert_array_equal(frame, original)


def test_convert_two_hands_without_external_objects(
    boundary: SimpleNamespace,
    model: Path,
) -> None:
    categories = [
        [
            SimpleNamespace(category_name="Left", score=0.1),
            SimpleNamespace(category_name="Right", score=0.9),
        ],
        [SimpleNamespace(category_name="Left", score=0.8)],
    ]
    raw = result([raw_hand(), raw_hand(0.1)], categories)
    boundary.detector.detect.return_value = raw
    with HandTracker(model, num_hands=2) as tracker:
        hands = tracker.process(np.zeros((4, 5, 3), dtype=np.uint8))
    assert len(hands) == 2
    assert all(isinstance(hand, DetectedHand) for hand in hands)
    assert hands[0].handedness == "Right"
    assert hands[0].handedness_score == 0.9
    assert hands[1].handedness == "Left"
    assert hands[1].handedness_score == 0.8
    assert hands[0].landmarks[HandLandmark.INDEX_FINGER_TIP] == NormalizedLandmark(
        0.4, 0.5, -0.08
    )
    raw.hand_landmarks[0][8].x = 999
    assert hands[0].landmarks[8].x == 0.4


@pytest.mark.parametrize(
    "handedness", [[], [[]], [[SimpleNamespace(category_name=None, score=None)]]]
)
def test_handedness_can_be_absent(
    boundary: SimpleNamespace,
    model: Path,
    handedness: list[list[SimpleNamespace]],
) -> None:
    boundary.detector.detect.return_value = result([raw_hand()], handedness)
    with HandTracker(model) as tracker:
        hand = tracker.process(np.zeros((1, 1, 3), dtype=np.uint8))[0]
    assert hand.handedness is None
    assert hand.handedness_score is None


@pytest.mark.parametrize(
    "frame,error,message",
    [
        ([[[0, 0, 0]]], TypeError, "ndarray"),
        (np.zeros((3, 4, 3), dtype=np.float32), TypeError, "uint8"),
        (np.zeros((3, 4), dtype=np.uint8), ValueError, "H.*W.*3"),
        (np.zeros((3, 4, 4), dtype=np.uint8), ValueError, "H.*W.*3"),
        (np.zeros((0, 4, 3), dtype=np.uint8), ValueError, "positive"),
    ],
)
def test_invalid_frames_do_not_reach_detector(
    boundary: SimpleNamespace,
    model: Path,
    frame: object,
    error: type[Exception],
    message: str,
) -> None:
    with HandTracker(model) as tracker, pytest.raises(error, match=message):
        tracker.process(frame)
    boundary.mp.Image.assert_not_called()
    boundary.detector.detect.assert_not_called()


def test_malformed_results_are_errors_not_empty_detections(
    boundary: SimpleNamespace,
    model: Path,
) -> None:
    boundary.detector.detect.return_value = result([raw_hand()[:20]])
    with HandTracker(model) as tracker, pytest.raises(ValueError, match="21"):
        tracker.process(np.zeros((2, 2, 3), dtype=np.uint8))
    boundary.detector.close.assert_called_once()


def test_close_is_idempotent_and_processing_after_close_is_rejected(
    boundary: SimpleNamespace,
    model: Path,
) -> None:
    tracker = HandTracker(model)
    tracker.close()
    tracker.close()
    boundary.detector.close.assert_called_once()
    with pytest.raises(RuntimeError, match="closed"):
        tracker.process(np.zeros((1, 1, 3), dtype=np.uint8))
    with pytest.raises(RuntimeError, match="closed"):
        with tracker:
            pytest.fail("A closed tracker cannot be reused")


def test_context_closes_when_caller_raises(
    boundary: SimpleNamespace, model: Path
) -> None:
    with pytest.raises(LookupError, match="caller"):
        with HandTracker(model):
            raise LookupError("caller failed")
    boundary.detector.close.assert_called_once()


@pytest.mark.parametrize(
    "error", [ValueError("invalid image"), RuntimeError("inference failed")]
)
def test_detection_errors_keep_cause_and_close_resources(
    boundary: SimpleNamespace,
    model: Path,
    error: Exception,
) -> None:
    boundary.detector.detect.side_effect = error
    with pytest.raises(HandTrackerError, match="process") as caught:
        with HandTracker(model) as tracker:
            tracker.process(np.zeros((2, 2, 3), dtype=np.uint8))
    assert caught.value.__cause__ is error
    boundary.detector.close.assert_called_once()


def test_initialization_error_is_not_swallowed(
    boundary: SimpleNamespace, model: Path
) -> None:
    error = ValueError("invalid model")
    boundary.factory.side_effect = error
    with pytest.raises(HandTrackerError, match="initialize") as caught:
        HandTracker(model)
    assert caught.value.__cause__ is error


def test_close_error_can_be_retried(boundary: SimpleNamespace, model: Path) -> None:
    error = RuntimeError("close failed")
    boundary.detector.close.side_effect = [error, None]
    tracker = HandTracker(model)
    with pytest.raises(HandTrackerError, match="close") as caught:
        tracker.close()
    assert caught.value.__cause__ is error
    tracker.close()
    assert boundary.detector.close.call_count == 2


def test_missing_model_fails_before_mediapipe_creation(
    boundary: SimpleNamespace, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError, match="model"):
        HandTracker(tmp_path / "missing.task")
    boundary.factory.assert_not_called()


@pytest.mark.parametrize(
    "options",
    [
        {"num_hands": 0},
        {"num_hands": True},
        {"num_hands": 1.5},
        {"min_hand_detection_confidence": -0.1},
        {"min_hand_presence_confidence": float("nan")},
    ],
)
def test_invalid_options_fail_before_detector_creation(
    boundary: SimpleNamespace,
    model: Path,
    options: dict[str, int | float],
) -> None:
    with pytest.raises(ValueError):
        HandTracker(model, **options)
    boundary.factory.assert_not_called()


def test_unexpected_errors_propagate(boundary: SimpleNamespace, model: Path) -> None:
    boundary.detector.detect.side_effect = OSError("unexpected")
    with pytest.raises(OSError, match="unexpected"):
        with HandTracker(model) as tracker:
            tracker.process(np.zeros((1, 1, 3), dtype=np.uint8))
    boundary.detector.close.assert_called_once()


def test_missing_mediapipe_has_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
    model: Path,
) -> None:
    monkeypatch.setitem(sys.modules, "mediapipe", None)
    with pytest.raises(HandTrackerError, match="vision extra") as caught:
        HandTracker(model)
    assert isinstance(caught.value.__cause__, ModuleNotFoundError)


def test_nonfinite_detector_coordinates_are_rejected(
    boundary: SimpleNamespace,
    model: Path,
) -> None:
    malformed = raw_hand()
    malformed[8].x = float("nan")
    boundary.detector.detect.return_value = result([malformed])
    with pytest.raises(ValueError, match="finite"):
        with HandTracker(model) as tracker:
            tracker.process(np.zeros((2, 2, 3), dtype=np.uint8))
    boundary.detector.close.assert_called_once()

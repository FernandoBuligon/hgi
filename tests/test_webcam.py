"""Synthetic full pipeline and OpenCV window/resource boundaries."""

from dataclasses import replace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from test_cursor_controller import pinched

from hgi.cursor import ControlState, CursorAction
from hgi.cursor_controller import CursorConfig
from hgi.gesture_detector import Gesture
from hgi.webcam import DemoConfig, WebcamPipeline, handle_key, run_webcam, select_hand


class FakeTracker:
    def __init__(self, hands=()):
        self.hands = hands
        self.frames = []
        self.closed = False

    def process(self, frame):
        self.frames.append(frame.copy())
        return self.hands

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


def test_selection_prefers_handedness_score_and_first_tie_without_identity(
    hand_factory,
):
    first = hand_factory("index")
    better = replace(first, handedness="Left", handedness_score=0.97)
    worse = replace(first, handedness_score=0.8)
    assert select_hand(()) is None
    assert select_hand((first, first)) is first
    assert select_hand((first, worse, better)) is better
    assert select_hand((better, replace(better))) is better


def test_bgr_to_rgb_mirroring_preserves_source_before_overlay():
    tracker = FakeTracker()
    pipeline = WebcamPipeline(tracker, CursorConfig(1920, 1080, mirror_x=False))
    frame = np.zeros((120, 160, 3), np.uint8)
    frame[:, :, 0] = 7
    frame[:, :, 2] = 99
    frame[0, 0] = [1, 2, 3]
    original = frame.copy()
    rendered, info = pipeline.process(frame)
    assert tracker.frames[0][0, -1].tolist() == [3, 2, 1]
    assert tracker.frames[0][0, 0].tolist() == [99, 0, 7]
    assert np.array_equal(frame, original)
    assert rendered.shape == frame.shape and info.hand is None
    assert pipeline.controller.state is ControlState.DISABLED


def test_point_pinch_absence_and_keys_use_only_dry_run(hand_factory, fake_clock):
    point = hand_factory("index", aspect_ratio=4 / 3)
    tracker = FakeTracker((point,))
    pipeline = WebcamPipeline(
        tracker, CursorConfig(1920, 1080, mirror_x=False), clock=fake_clock
    )
    frame = np.zeros((120, 160, 3), np.uint8)
    _, info = pipeline.process(frame)
    assert info.observation.raw is Gesture.POINT
    assert info.command.action is CursorAction.NONE
    assert not handle_key(ord("E"), pipeline.controller)
    _, info = pipeline.process(frame)
    assert info.temporal.candidate is Gesture.POINT
    assert info.temporal.stable is Gesture.UNKNOWN
    fake_clock.now += 0.08
    _, moved = pipeline.process(frame)
    assert moved.command.action is CursorAction.MOVE
    assert moved.temporal.armed
    tracker.hands = (pinched(point),)
    fake_clock.now += 0.02
    pipeline.process(frame)
    fake_clock.now += 0.08
    _, clicked = pipeline.process(frame)
    assert clicked.command.action is CursorAction.CLICK
    assert clicked.position == moved.position
    assert clicked.temporal.cooldown_active
    _, held = pipeline.process(frame)
    assert held.command.action is CursorAction.NONE
    assert clicked.command is not held.command
    tracker.hands = ()
    assert pipeline.process(frame)[1].command.action is CursorAction.NONE
    for key in ("d", "e", "r"):
        handle_key(ord(key), pipeline.controller)
    assert pipeline.controller.state is ControlState.DISABLED
    assert handle_key(ord("q"), pipeline.controller)
    assert handle_key(27, pipeline.controller)


def test_runtime_dimensions_configure_aspect_and_changes_disable_session(hand_factory):
    tracker = FakeTracker((hand_factory("index", aspect_ratio=2),))
    pipeline = WebcamPipeline(tracker, CursorConfig(1920, 1080, mirror_x=False))
    _, data = pipeline.process(np.zeros((100, 200, 3), np.uint8))
    assert data.observation.raw is Gesture.POINT
    pipeline.controller.enable()
    pipeline.process(np.zeros((100, 150, 3), np.uint8))
    assert pipeline.controller.state is ControlState.DISABLED


def test_continuous_pipeline_bounds_sink_retention():
    pipeline = WebcamPipeline(FakeTracker(), CursorConfig(1920, 1080, mirror_x=False))
    for _ in range(20):
        pipeline.process(np.zeros((120, 160, 3), np.uint8))
    assert len(pipeline.controller.sink.commands) == 1


def test_processing_error_disables_and_propagates(hand_factory):
    tracker = FakeTracker((hand_factory("index"),))
    pipeline = WebcamPipeline(tracker, CursorConfig(1920, 1080, mirror_x=False))
    frame = np.zeros((120, 160, 3), np.uint8)
    pipeline.process(frame)
    pipeline.controller.enable()
    tracker.process = Mock(side_effect=RuntimeError("inference"))
    with pytest.raises(RuntimeError, match="inference"):
        pipeline.process(frame)
    assert pipeline.controller.state is ControlState.DISABLED


@pytest.mark.parametrize("failure", [None, "process", "imshow", "waitKey"])
def test_demo_releases_camera_tracker_and_windows(tmp_path, monkeypatch, failure):
    import hgi.webcam as webcam

    model = tmp_path / "model.task"
    model.touch()
    tracker = FakeTracker()
    capture = Mock()
    capture.isOpened.return_value = True
    capture.read.return_value = (True, np.zeros((120, 160, 3), np.uint8))
    monkeypatch.setenv("DISPLAY", ":test")
    monkeypatch.setattr(webcam, "HandTracker", Mock(return_value=tracker))
    monkeypatch.setattr(cv2, "VideoCapture", Mock(return_value=capture))
    for name in ("namedWindow", "imshow", "destroyAllWindows"):
        monkeypatch.setattr(cv2, name, Mock())
    monkeypatch.setattr(cv2, "waitKey", Mock(return_value=ord("q")))
    if failure:
        target = tracker if failure == "process" else cv2
        monkeypatch.setattr(
            target, failure, Mock(side_effect=cv2.error("fake failure"))
        )
        with pytest.raises(cv2.error, match="fake failure"):
            run_webcam(DemoConfig(model_path=model))
    else:
        run_webcam(DemoConfig(model_path=model))
    assert tracker.closed
    capture.release.assert_called_once()
    cv2.destroyAllWindows.assert_called_once()


def test_missing_model_points_to_documentation_before_camera(tmp_path, monkeypatch):
    capture = Mock()
    monkeypatch.setattr(cv2, "VideoCapture", capture)
    with pytest.raises(FileNotFoundError, match="docs/MODELS.md"):
        run_webcam(DemoConfig(model_path=tmp_path / "absent.task"))
    capture.assert_not_called()

"""Synthetic full pipeline and OpenCV window/resource boundaries."""

from dataclasses import replace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from conftest import FakeClock
from test_cursor_controller import pinched

from hgi.cursor import ControlState, CursorAction
from hgi.cursor_controller import CursorConfig
from hgi.gesture_detector import Gesture
from hgi.system_actions import ActionKind, ActionResult
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


class FakeActionSink:
    def __init__(self):
        self.intents = []

    def emit(self, intent):
        self.intents.append(intent)
        return ActionResult(intent=intent, executed=True, message="fake")


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
    _, pressed = pipeline.process(frame)
    assert pressed.command.action is CursorAction.MOUSE_DOWN
    assert pressed.position == moved.position
    assert pressed.temporal.cooldown_active
    _, held = pipeline.process(frame)
    assert held.command.action is CursorAction.MOVE
    assert pressed.command is not held.command
    tracker.hands = ()
    assert pipeline.process(frame)[1].command.action is CursorAction.NONE
    for key in ("d", "e", "r"):
        handle_key(ord(key), pipeline.controller)
    assert pipeline.controller.state is ControlState.DISABLED
    assert handle_key(ord("q"), pipeline.controller)
    assert handle_key(27, pipeline.controller)


def test_system_gestures_publish_dry_run_intentions_only_when_enabled(
    hand_factory, fake_clock
):
    tracker = FakeTracker((hand_factory("index", "middle", aspect_ratio=4 / 3),))
    pipeline = WebcamPipeline(
        tracker, CursorConfig(1920, 1080, mirror_x=False), clock=fake_clock
    )
    frame = np.zeros((120, 160, 3), np.uint8)
    fake_clock.now = 0.33
    assert pipeline.process(frame)[1].system_action.intent is None
    pipeline.handle_key(ord("e"))
    for now in (0.34, 0.42):
        fake_clock.now = now
        assert pipeline.process(frame)[1].system_action.intent is None
    fake_clock.now = 0.70
    assert pipeline.process(frame)[1].system_action.intent is None
    fake_clock.now = 1.0
    state = pipeline.process(frame)[1]
    assert state.system_action.intent.kind is ActionKind.SCREENSHOT
    assert state.system_action.executed is False
    assert state.system_action.message == "dry-run"


def test_real_control_gate_executes_system_actions_only_after_enable(
    hand_factory, fake_clock
):
    sink = FakeActionSink()
    tracker = FakeTracker((hand_factory("index", "middle", aspect_ratio=4 / 3),))
    pipeline = WebcamPipeline(
        tracker,
        CursorConfig(1920, 1080, mirror_x=False),
        action_sink=sink,
        clock=fake_clock,
    )
    frame = np.zeros((120, 160, 3), np.uint8)
    for now in (0.0, 0.08, 0.33):
        fake_clock.now = now
        pipeline.process(frame)
    assert sink.intents == []
    pipeline.handle_key(ord("e"))
    for now in (1.0, 1.08, 1.36):
        fake_clock.now = now
        state = pipeline.process(frame)[1]
    assert state.system_action.intent.kind is ActionKind.SCREENSHOT
    assert state.system_action.executed is True
    assert [intent.kind for intent in sink.intents] == [ActionKind.SCREENSHOT]


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


@pytest.mark.parametrize(
    "failure", [None, "process", "namedWindow", "imshow", "waitKey"]
)
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


def test_no_display_is_reported_before_opening_camera(tmp_path, monkeypatch):
    import hgi.webcam as webcam

    model = tmp_path / "model.task"
    model.touch()
    monkeypatch.setattr(webcam.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    capture = Mock()
    monkeypatch.setattr(cv2, "VideoCapture", capture)
    with pytest.raises(webcam.DisplayError, match="graphical session"):
        run_webcam(DemoConfig(model_path=model))
    capture.assert_not_called()


def test_tracker_initialization_error_releases_camera_and_windows(
    tmp_path, monkeypatch
):
    import hgi.webcam as webcam
    from hgi.hand_tracker import HandTrackerError

    model = tmp_path / "model.task"
    model.touch()
    capture = Mock()
    capture.isOpened.return_value = True
    monkeypatch.setenv("DISPLAY", ":test")
    monkeypatch.setattr(cv2, "VideoCapture", Mock(return_value=capture))
    monkeypatch.setattr(cv2, "destroyAllWindows", Mock())
    monkeypatch.setattr(
        webcam, "HandTracker", Mock(side_effect=HandTrackerError("bad model"))
    )
    with pytest.raises(HandTrackerError, match="bad model"):
        run_webcam(DemoConfig(model_path=model))
    capture.release.assert_called_once()
    cv2.destroyAllWindows.assert_called_once()


def test_window_close_exits_and_releases_all_resources(tmp_path, monkeypatch):
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
    monkeypatch.setattr(cv2, "waitKey", Mock(return_value=-1))
    monkeypatch.setattr(cv2, "getWindowProperty", Mock(return_value=0))
    run_webcam(DemoConfig(model_path=model))
    assert tracker.closed
    capture.release.assert_called_once()
    capture.read.assert_called_once()
    cv2.destroyAllWindows.assert_called_once()


def test_cli_help_absent_model_and_forbidden_control_flag(tmp_path, capsys):
    import runpy

    main = runpy.run_path("scripts/demo_webcam.py")["main"]
    with pytest.raises(SystemExit) as help_exit:
        main(["--help"])
    assert help_exit.value.code == 0
    assert "DRY-RUN" in capsys.readouterr().out
    assert main(["--model", str(tmp_path / "absent.task")]) == 1
    assert "docs/MODELS.md" in capsys.readouterr().err
    with pytest.raises(SystemExit) as control_exit:
        main(["--control"])
    assert control_exit.value.code == 2


@pytest.mark.parametrize("camera_index, alternative", [(0, 1), (1, 0)])
def test_cli_camera_failure_suggests_alternative_without_retry(
    monkeypatch, capsys, camera_index, alternative
):
    import runpy

    import hgi.webcam as webcam
    from hgi.camera import CameraError

    run = Mock(side_effect=CameraError(f"Could not open camera {camera_index}"))
    monkeypatch.setattr(webcam, "run_webcam", run)
    main = runpy.run_path("scripts/demo_webcam.py")["main"]

    assert main(["--camera", str(camera_index)]) == 1
    message = capsys.readouterr().err
    assert f"Could not open camera {camera_index}" in message
    assert f"--camera {alternative}" in message
    run.assert_called_once()


def test_ui_click_persistence_does_not_repeat_commands_or_advance_temporal_clock(
    hand_factory, fake_clock
):
    ui_clock = FakeClock(now=10.0)
    point = hand_factory("index", aspect_ratio=4 / 3)
    tracker = FakeTracker((point,))
    pipeline = WebcamPipeline(
        tracker,
        CursorConfig(1920, 1080, mirror_x=False),
        clock=fake_clock,
        ui_clock=ui_clock,
    )
    frame = np.zeros((120, 160, 3), np.uint8)
    pipeline.process(frame)
    pipeline.handle_key(ord("e"))
    pipeline.process(frame)
    fake_clock.now += 0.08
    pipeline.process(frame)
    sink = pipeline.controller.sink
    sink.emit = Mock(wraps=sink.emit)
    tracker.hands = (pinched(point),)
    fake_clock.now += 0.02
    pipeline.process(frame)
    fake_clock.now += 0.08
    _, clicked = pipeline.process(frame)
    assert clicked.command.action is CursorAction.MOUSE_DOWN
    assert clicked.click_feedback.recent_click
    assert clicked.click_feedback.click_count == 1
    for now, recent in ((10.499, True), (10.5, False)):
        ui_clock.now = now
        _, held = pipeline.process(frame)
        assert held.command.action is CursorAction.MOVE
        assert held.click_feedback.recent_click is recent
        assert held.click_feedback.click_count == 1
        assert held.temporal == clicked.temporal  # UI time does not advance cooldown.
        assert sink.commands == (held.command,)
    actions = [call.args[0].action for call in sink.emit.call_args_list]
    assert actions == [
        CursorAction.NONE,
        CursorAction.MOUSE_DOWN,
        CursorAction.MOVE,
        CursorAction.MOVE,
    ]
    pipeline.handle_key(ord("d"))
    assert pipeline.process(frame)[1].click_feedback.click_count == 1
    pipeline.handle_key(ord("e"))
    assert pipeline.process(frame)[1].click_feedback.click_count == 1
    assert (
        pipeline.process(np.zeros((120, 200, 3), np.uint8))[
            1
        ].click_feedback.click_count
        == 1
    )
    pipeline.handle_key(ord("r"))
    reset = pipeline.process(frame)[1]
    assert (
        reset.click_feedback.click_count == 0 and not reset.click_feedback.recent_click
    )
    assert pipeline.controller.state is ControlState.DISABLED

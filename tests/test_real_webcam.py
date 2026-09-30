"""Double opt-in, native-boundary cleanup and visible output mode with fakes."""

import runpy
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from test_cursor_controller import pinched
from test_real_cursor import FakeMouseBackend
from test_webcam import FakeTracker

from hgi.cursor import ControlState, CursorAction, CursorMode, DryRunCursorSink
from hgi.overlay import overlay_lines
from hgi.real_cursor import RealCursorError, RealCursorSink
from hgi.webcam import DemoConfig, WebcamPipeline, configure_output, run_webcam


def test_default_output_does_not_construct_backend_or_query_monitor(monkeypatch):
    import hgi.webcam as webcam

    constructor = Mock(side_effect=AssertionError("real backend in dry-run"))
    monkeypatch.setattr(webcam, "RealCursorSink", constructor)
    config, sink = configure_output(DemoConfig())
    assert isinstance(sink, DryRunCursorSink)
    assert sink.mode is CursorMode.DRY_RUN
    assert (config.screen_width, config.screen_height) == (1920, 1080)
    constructor.assert_not_called()


def test_real_flag_selects_sink_and_detected_dimensions(monkeypatch):
    import hgi.webcam as webcam

    sink = RealCursorSink(backend=FakeMouseBackend())
    constructor = Mock(return_value=sink)
    monkeypatch.setattr(webcam, "RealCursorSink", constructor)
    config, selected = configure_output(DemoConfig(real_control=True))
    assert selected is sink
    assert (config.screen_width, config.screen_height) == (1001, 501)
    constructor.assert_called_once_with(screen_width=None, screen_height=None)


@pytest.mark.parametrize("real_control", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_double_opt_in_and_mode_labels(real_control, enabled, hand_factory, fake_clock):
    backend = FakeMouseBackend()
    sink = (
        RealCursorSink(backend=backend)
        if real_control
        else DryRunCursorSink(max_history=1)
    )
    tracker = FakeTracker((hand_factory("index", aspect_ratio=4 / 3),))
    from hgi.cursor_controller import CursorConfig

    config = CursorConfig(1001, 501, mirror_x=False)
    pipeline = WebcamPipeline(tracker, config, sink=sink, clock=fake_clock)
    frame = np.zeros((120, 160, 3), np.uint8)
    pipeline.process(frame)
    assert pipeline.controller.state is ControlState.DISABLED
    if enabled:
        pipeline.handle_key(ord("e"))
    pipeline.process(frame)
    fake_clock.now += 0.08
    rendered, state = pipeline.process(frame)
    assert rendered.shape == frame.shape
    assert state.command.action is (CursorAction.MOVE if enabled else CursorAction.NONE)
    assert state.mode is (
        CursorMode.REAL_CONTROL if real_control else CursorMode.DRY_RUN
    )
    header = overlay_lines(state, config)[0]
    assert f"HGI | {state.mode.value} | CONTROL: {state.control.value}" == header
    if real_control and enabled:
        backend.move_to.assert_called_once_with(
            round(state.command.x), round(state.command.y)
        )
    else:
        backend.move_to.assert_not_called()
    backend.click.assert_not_called()
    for key in ("d", "r", "q"):
        pipeline.handle_key(ord(key))
        assert pipeline.process(frame)[1].command.action is CursorAction.NONE
    # Closed PINCH while disabled cannot cause a click, regardless of flag.
    tracker.hands = (pinched(tracker.hands[0]),)
    fake_clock.now += 1
    assert pipeline.process(frame)[1].command.action is CursorAction.NONE
    backend.click.assert_not_called()


@pytest.mark.parametrize(
    "values", [{"screen_width": 800}, {"screen_height": 400}, {"real_control": 1}]
)
def test_invalid_demo_settings_fail_before_backend(values):
    with pytest.raises(ValueError):
        DemoConfig(**values)


def test_cli_default_real_flag_and_paired_override(monkeypatch, capsys):
    import hgi.webcam as webcam

    run = Mock()
    monkeypatch.setattr(webcam, "run_webcam", run)
    main = runpy.run_path("scripts/demo_webcam.py")["main"]
    assert main([]) == 0
    default = run.call_args.args[0]
    assert not default.real_control
    assert default.screen_width is None and default.screen_height is None
    assert (
        main(
            [
                "--real-control",
                "--camera",
                "1",
                "--screen-width",
                "800",
                "--screen-height",
                "400",
            ]
        )
        == 0
    )
    real = run.call_args.args[0]
    assert real.real_control and real.camera_index == 1
    assert (real.screen_width, real.screen_height) == (800, 400)
    with pytest.raises(SystemExit) as caught:
        main(["--real-control", "--screen-width", "800"])
    assert caught.value.code == 2
    assert "both" in capsys.readouterr().err


@pytest.mark.parametrize("error", [RuntimeError("mouse failure"), KeyboardInterrupt()])
def test_real_backend_fault_closes_demo_and_preserves_original(
    monkeypatch, tmp_path, hand_factory, error
):
    import hgi.webcam as webcam

    model = tmp_path / "model.task"
    model.touch()
    backend = FakeMouseBackend()
    backend.move_to.side_effect = error
    sink = RealCursorSink(backend=backend)
    monkeypatch.setattr(webcam, "RealCursorSink", Mock(return_value=sink))
    tracker = FakeTracker((hand_factory("index", aspect_ratio=4 / 3),))
    capture = Mock()
    capture.isOpened.return_value = True
    capture.read.return_value = (True, np.zeros((120, 160, 3), np.uint8))
    monkeypatch.setenv("DISPLAY", ":fake")
    monkeypatch.setattr(webcam, "HandTracker", Mock(return_value=tracker))
    monkeypatch.setattr(cv2, "VideoCapture", Mock(return_value=capture))
    for name in ("namedWindow", "imshow", "destroyAllWindows"):
        monkeypatch.setattr(cv2, name, Mock())
    monkeypatch.setattr(cv2, "waitKey", Mock(side_effect=[ord("e"), -1, -1]))
    monkeypatch.setattr(cv2, "getWindowProperty", Mock(return_value=1))
    clock = Mock(side_effect=[0.0, 0.2])
    # Inject only the time source at the temporal boundary; use the real filter.
    from hgi.temporal import TemporalGestureFilter

    monkeypatch.setattr(
        webcam, "TemporalGestureFilter", lambda **_: TemporalGestureFilter(clock=clock)
    )
    # Capture the live controller without replacing its logic.
    instances = []
    original = webcam.CursorController

    def controller_factory(*args, **kwargs):
        controller = original(*args, **kwargs)
        instances.append(controller)
        return controller

    monkeypatch.setattr(webcam, "CursorController", controller_factory)
    with pytest.raises(type(error)) as caught:
        run_webcam(DemoConfig(model_path=model, real_control=True))
    assert caught.value is error
    assert sink.failed
    assert all(c.state is ControlState.DISABLED for c in instances)
    backend.move_to.assert_called_once()
    backend.click.assert_not_called()
    capture.release.assert_called_once()
    assert tracker.closed
    cv2.destroyAllWindows.assert_called_once()


def test_real_startup_failure_does_not_fall_back_or_open_camera(monkeypatch, tmp_path):
    import hgi.webcam as webcam

    model = tmp_path / "model.task"
    model.touch()
    monkeypatch.setenv("DISPLAY", ":fake")
    camera = Mock()
    monkeypatch.setattr(webcam, "Camera", camera)
    monkeypatch.setattr(cv2, "destroyAllWindows", Mock())
    error = RealCursorError("backend unavailable")
    monkeypatch.setattr(webcam, "RealCursorSink", Mock(side_effect=error))
    with pytest.raises(RealCursorError) as caught:
        run_webcam(DemoConfig(model_path=model, real_control=True))
    assert caught.value is error
    camera.assert_not_called()
    cv2.destroyAllWindows.assert_called_once()

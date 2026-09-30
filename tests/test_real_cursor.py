"""Real-output contracts against fakes only; no native mouse or display access."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_cursor_controller import pinched

from hgi.cursor import ControlState, CursorAction, CursorCommand, CursorMode
from hgi.cursor_controller import CursorConfig, CursorController
from hgi.real_cursor import PyAutoGUIBackend, RealCursorError, RealCursorSink
from hgi.temporal import TemporalGestureFilter


class FakeMouseBackend:
    def __init__(self, size=(1001, 501)):
        self.size = Mock(return_value=size)
        self.move_to = Mock()
        self.click = Mock()


@pytest.fixture
def backend():
    return FakeMouseBackend()


def test_move_rounds_once_clicks_once_and_none_has_no_effect(backend):
    sink = RealCursorSink(backend=backend)
    assert sink.mode is CursorMode.REAL_CONTROL
    assert (sink.screen_width, sink.screen_height) == (1001, 501)
    backend.size.assert_called_once_with()
    sink.emit(CursorCommand(CursorAction.NONE))
    backend.move_to.assert_not_called()
    backend.click.assert_not_called()
    sink.emit(CursorCommand(CursorAction.MOVE, 123.5, 234.4))
    backend.move_to.assert_called_once_with(124, 234)
    sink.emit(CursorCommand(CursorAction.CLICK, 123.5, 234.4))
    backend.click.assert_called_once_with(124, 234)
    backend.move_to.assert_called_once()
    backend.size.assert_called_once()  # no monitor polling in the loop


@pytest.mark.parametrize("action", [CursorAction.MOVE, CursorAction.CLICK])
@pytest.mark.parametrize("xy", [(1001, 0), (0, 501), (1000.6, 0)])
def test_invalid_bounds_are_rejected_before_effect_and_lock_sink(backend, action, xy):
    sink = RealCursorSink(backend=backend)
    with pytest.raises(ValueError, match="bounds"):
        sink.emit(CursorCommand(action, *xy))
    assert sink.failed
    backend.move_to.assert_not_called()
    backend.click.assert_not_called()
    with pytest.raises(RealCursorError, match="restart"):
        sink.emit(CursorCommand(CursorAction.MOVE, 10, 10))


def test_last_screen_pixel_and_python_round_ties_are_valid(backend):
    sink = RealCursorSink(backend=backend)
    sink.emit(CursorCommand(CursorAction.MOVE, 1000, 500))
    sink.emit(CursorCommand(CursorAction.MOVE, 12.5, 23.5))
    assert [call.args for call in backend.move_to.call_args_list] == [
        (1000, 500),
        (12, 24),
    ]


@pytest.mark.parametrize(
    "dimensions", [(800, None), (None, 400), (1002, 501), (0, 1), (True, 400)]
)
def test_override_must_be_paired_positive_and_within_detected_screen(
    backend, dimensions
):
    with pytest.raises(ValueError):
        RealCursorSink(
            backend=backend, screen_width=dimensions[0], screen_height=dimensions[1]
        )
    backend.move_to.assert_not_called()
    backend.click.assert_not_called()


def test_paired_override_uses_top_left_rectangle_without_scaling(backend):
    sink = RealCursorSink(backend=backend, screen_width=800, screen_height=400)
    assert sink.detected_size == (1001, 501)
    assert (sink.screen_width, sink.screen_height) == (800, 400)
    sink.emit(CursorCommand(CursorAction.MOVE, 799, 399))
    backend.move_to.assert_called_once_with(799, 399)


@pytest.mark.parametrize("action", [CursorAction.MOVE, CursorAction.CLICK])
@pytest.mark.parametrize("error", [RuntimeError("backend"), KeyboardInterrupt()])
def test_failure_disables_controller_preserves_original_and_prevents_future_effects(
    backend, hand_factory, fake_clock, action, error
):
    sink = RealCursorSink(backend=backend)
    controller = CursorController(
        CursorConfig(1001, 501),
        sink=sink,
        temporal=TemporalGestureFilter(clock=fake_clock),
    )
    point = hand_factory("index")
    controller.enable()
    controller.update(point)
    fake_clock.now += 0.08
    controller.update(point)
    hand = point
    method = backend.move_to
    if action is CursorAction.CLICK:
        hand = pinched(point)
        controller.update(hand)
        fake_clock.now += 0.08
        method = backend.click
    method.side_effect = error
    before = method.call_count
    with pytest.raises(type(error)) as caught:
        controller.update(hand)
    assert caught.value is error
    assert controller.state is ControlState.DISABLED and sink.failed
    assert controller.update(hand).action is CursorAction.NONE
    controller.disable()
    controller.reset()
    controller.enable()
    controller.update(point)
    fake_clock.now += 0.08
    # Re-enabled, confirmed POINT attempts remain blocked by the latched sink.
    with pytest.raises(RealCursorError, match="restart"):
        controller.update(point)
    assert controller.state is ControlState.DISABLED
    assert method.call_count == before + 1


def test_existing_temporal_filter_keeps_sustained_pinch_to_one_click(
    backend, hand_factory, fake_clock
):
    sink = RealCursorSink(backend=backend)
    controller = CursorController(
        CursorConfig(1001, 501),
        sink=sink,
        temporal=TemporalGestureFilter(clock=fake_clock),
    )
    point = hand_factory("index")
    controller.update(point)
    backend.move_to.assert_not_called()
    backend.click.assert_not_called()
    controller.enable()
    controller.update(point)
    fake_clock.now += 0.08
    move = controller.update(point)
    pinch = pinched(point)
    controller.update(pinch)
    fake_clock.now += 0.08
    click = controller.update(pinch)
    assert click.action is CursorAction.CLICK
    backend.move_to.assert_called_once_with(round(move.x), round(move.y))
    backend.click.assert_called_once_with(round(click.x), round(click.y))
    for _ in range(10):
        fake_clock.now += 0.1
        assert controller.update(pinch).action is CursorAction.NONE
    backend.click.assert_called_once()
    before = backend.move_to.call_count, backend.click.call_count
    controller.disable()
    controller.reset()
    assert before == (backend.move_to.call_count, backend.click.call_count)


def test_pyautogui_adapter_preserves_failsafe_pause_and_only_uses_mouse(monkeypatch):
    api = SimpleNamespace(
        FAILSAFE=False,
        PAUSE=0.1,
        size=Mock(return_value=(1001, 501)),
        moveTo=Mock(),
        click=Mock(),
    )
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setitem(sys.modules, "pyautogui", api)
    adapter = PyAutoGUIBackend()
    assert adapter.size() == (1001, 501)
    assert api.FAILSAFE is True and api.PAUSE == 0.1
    api.FAILSAFE = False  # other code cannot silently disable HGI protection
    adapter.move_to(10, 20)
    assert api.FAILSAFE is True
    adapter.click(10, 20)
    api.moveTo.assert_called_once_with(10, 20, duration=0.0, logScreenshot=False)
    api.click.assert_called_once_with(
        10, 20, clicks=1, button="primary", duration=0.0, logScreenshot=False
    )
    assert api.PAUSE == 0.1


def test_wayland_is_rejected_before_backend_import(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    with pytest.raises(RealCursorError, match="Wayland"):
        PyAutoGUIBackend()


def test_unavailable_pyautogui_has_clear_error_with_original_cause(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    with pytest.raises(RealCursorError, match="PyAutoGUI") as caught:
        PyAutoGUIBackend()  # autouse fixture blocks the real import
    assert isinstance(caught.value.__cause__, ImportError)

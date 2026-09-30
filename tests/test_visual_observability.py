"""Small additions needed by a continuous visual demo, with no native calls."""

import pytest

from hgi.cursor import CursorAction, CursorCommand, DryRunCursorSink
from hgi.cursor_controller import CursorConfig, CursorController
from hgi.gesture_detector import Gesture
from hgi.temporal import TemporalGestureFilter


def test_bounded_sink_retains_latest_intentions_without_changing_default_history():
    sink = DryRunCursorSink(max_history=2)
    commands = [CursorCommand(CursorAction.NONE) for _ in range(3)]
    for command in commands:
        sink.emit(command)
    assert sink.commands == tuple(commands[-2:])


@pytest.mark.parametrize("limit", [0, -1, True, 2.5])
def test_invalid_history_limit_is_rejected(limit):
    with pytest.raises(ValueError):
        DryRunCursorSink(max_history=limit)


def test_observation_and_temporal_status_are_read_only_and_do_not_read_clock(
    hand_factory, fake_clock
):
    temporal = TemporalGestureFilter(clock=fake_clock)
    controller = CursorController(CursorConfig(1920, 1080), temporal=temporal)
    assert controller.observation is None and controller.position is None
    assert temporal.status.candidate is None and not temporal.status.armed
    controller.enable()
    controller.update(hand_factory("index"))
    assert controller.observation.raw is Gesture.POINT
    assert temporal.status.candidate is Gesture.POINT
    fake_clock.now = -1  # A status read must not call this now-invalid clock.
    assert temporal.status.stable is Gesture.UNKNOWN
    fake_clock.now = 0.08
    controller.update(hand_factory("index"))
    assert controller.position is not None and temporal.status.armed
    controller.reset()
    assert controller.observation is None and controller.position is None
    assert temporal.status.candidate is None and not temporal.status.armed

"""Fresh async samples only; temporal and cursor logic remain unchanged."""

from dataclasses import replace
from unittest.mock import Mock

import numpy as np
from test_cursor_controller import pinched

from hgi.cursor import ControlState, CursorAction
from hgi.cursor_controller import CursorConfig
from hgi.hand_tracker import LiveResult
from hgi.tracker_config import HandTrackerConfig, RunningMode
from hgi.webcam import WebcamPipeline


class LiveTracker:
    def __init__(self):
        self.latest = None
        self.submit = Mock(return_value=True)

    def poll(self):
        sample, self.latest = self.latest, None
        return sample


def pipeline_and_tracker(fake_clock):
    tracker = LiveTracker()
    pipeline = WebcamPipeline(
        tracker,
        CursorConfig(1920, 1080, mirror_x=False),
        clock=fake_clock,
        performance_clock=fake_clock,
        tracker_config=HandTrackerConfig(running_mode=RunningMode.LIVE_STREAM),
    )
    frame = np.zeros((120, 160, 3), np.uint8)
    pipeline.process(frame)
    tracker.submit.reset_mock()
    return pipeline, tracker, frame


def sample(hand, now):
    return LiveResult((hand,) if hand else (), int(now * 1000), (120, 160), now, now)


def test_pending_frames_do_not_repeat_samples_or_cancel_confirmation(
    hand_factory, fake_clock
):
    pipeline, tracker, frame = pipeline_and_tracker(fake_clock)
    pipeline.handle_key(ord("e"))
    point = hand_factory("index", aspect_ratio=4 / 3)
    tracker.latest = sample(point, 0)
    assert pipeline.process(frame)[1].command.action is CursorAction.NONE
    sink = pipeline.controller.sink
    sink.emit = Mock(wraps=sink.emit)
    fake_clock.now = 0.04
    pending = pipeline.process(frame)[1]
    assert pending.command.action is CursorAction.NONE
    sink.emit.assert_not_called()
    fake_clock.now = 0.08
    tracker.latest = sample(point, 0.08)
    assert pipeline.process(frame)[1].command.action is CursorAction.MOVE

    fake_clock.now = 0.1
    tracker.latest = sample(pinched(point), 0.1)
    pipeline.process(frame)
    fake_clock.now = 0.18
    tracker.latest = sample(pinched(point), 0.18)
    clicked = pipeline.process(frame)[1]
    assert clicked.command.action is CursorAction.CLICK
    fake_clock.now = 0.20
    pending = pipeline.process(frame)[1]
    assert pending.command.action is CursorAction.NONE
    assert pending.click_feedback.click_count == 1
    assert [c.args[0].action for c in sink.emit.call_args_list].count(
        CursorAction.CLICK
    ) == 1
    for at in (0.3, 0.5, 0.8):
        fake_clock.now = at
        tracker.latest = sample(pinched(point), at)
        assert pipeline.process(frame)[1].command.action is CursorAction.NONE
    assert pipeline.process(frame)[1].click_feedback.click_count == 1


def test_old_wrong_size_and_pre_enable_results_cannot_move(hand_factory, fake_clock):
    pipeline, tracker, frame = pipeline_and_tracker(fake_clock)
    point = hand_factory("index", aspect_ratio=4 / 3)
    fake_clock.now = 1
    pipeline.handle_key(ord("e"))
    for outdated in (
        sample(point, 0.9),
        replace(sample(point, 1), shape=(480, 640)),
        sample(point, 0),
    ):
        tracker.latest = outdated
        assert pipeline.process(frame)[1].command.action is CursorAction.NONE
    assert pipeline.controller.position is None
    assert pipeline.controller.state is ControlState.ENABLED


def test_inference_stall_requires_release_before_clicking_again(
    hand_factory, fake_clock
):
    pipeline, tracker, frame = pipeline_and_tracker(fake_clock)
    pipeline.handle_key(ord("e"))
    point = hand_factory("index", aspect_ratio=4 / 3)
    for at in (0, 0.08):
        fake_clock.now = at
        tracker.latest = sample(point, at)
        pipeline.process(frame)
    assert pipeline.process(frame)[1].temporal.armed
    fake_clock.now = 0.25
    pipeline.process(frame)
    for at in (0.26, 0.34, 0.41, 0.5, 0.6):
        fake_clock.now = at
        tracker.latest = sample(pinched(point), at)
        assert pipeline.process(frame)[1].command.action is CursorAction.NONE
    assert pipeline.process(frame)[1].click_feedback.click_count == 0
    for at in (0.7, 0.79):
        fake_clock.now = at
        tracker.latest = sample(point, at)
        pipeline.process(frame)
    for at in (0.8, 0.89):
        fake_clock.now = at
        tracker.latest = sample(pinched(point), at)
        state = pipeline.process(frame)[1]
    assert state.command.action is CursorAction.CLICK
    assert state.click_feedback.click_count == 1


def test_stalled_inference_clears_display_and_sends_no_old_intention(
    hand_factory, fake_clock
):
    pipeline, tracker, frame = pipeline_and_tracker(fake_clock)
    tracker.latest = sample(hand_factory("index", aspect_ratio=4 / 3), 0)
    assert pipeline.process(frame)[1].hand is not None
    fake_clock.now = 0.2
    assert pipeline.process(frame)[1].hand is None
    for key in ("d", "r", "q"):
        pipeline.handle_key(ord(key))
        assert pipeline.controller.state is ControlState.DISABLED
        assert pipeline.process(frame)[1].command.action is CursorAction.NONE


def test_live_poll_failure_disables_before_propagating(fake_clock):
    import pytest

    pipeline, tracker, frame = pipeline_and_tracker(fake_clock)
    pipeline.handle_key(ord("e"))
    tracker.poll = Mock(side_effect=ValueError("callback failure"))
    with pytest.raises(ValueError, match="callback failure"):
        pipeline.process(frame)
    assert pipeline.controller.state is ControlState.DISABLED
    tracker.submit.assert_not_called()


def test_repeated_enable_does_not_discard_an_inflight_sample(hand_factory, fake_clock):
    pipeline, tracker, frame = pipeline_and_tracker(fake_clock)
    pipeline.handle_key(ord("e"))
    point = hand_factory("index", aspect_ratio=4 / 3)
    tracker.latest = sample(point, 0)
    pipeline.process(frame)
    fake_clock.now = 0.04
    pipeline.handle_key(ord("e"))
    fake_clock.now = 0.08
    tracker.latest = sample(point, 0.01)
    assert pipeline.process(frame)[1].command.action is CursorAction.MOVE

"""Opt-in and temporal integration, with real HGI geometry and fake seconds."""

from dataclasses import replace

import pytest

from hgi.cursor import CursorAction, DryRunCursorSink
from hgi.cursor_controller import CursorConfig, CursorController
from hgi.temporal import TemporalGestureFilter
from test_cursor_controller import at_indicator, pinched


def make_controller(clock, sink=None) -> CursorController:
    return CursorController(
        CursorConfig(1001, 501, mirror_x=False, smoothing_alpha=0.5),
        sink=sink,
        temporal=TemporalGestureFilter(clock=clock),
    )


def establish_point(controller, clock, hand):
    controller.enable()
    assert controller.update(hand).action is CursorAction.NONE
    clock.now += 0.08
    assert controller.update(hand).action is CursorAction.MOVE


def test_default_control_is_disabled_and_detection_never_enables_it(hand_factory):
    controller = CursorController(CursorConfig(1001, 501))
    assert controller.state.name == "DISABLED"
    assert controller.update(hand_factory("index")).action is CursorAction.NONE
    assert controller.update(pinched(hand_factory("index"))).action is CursorAction.NONE
    assert controller.state.name == "DISABLED"


def test_enable_requires_fresh_confirmation_and_is_idempotent(hand_factory, fake_clock):
    controller = make_controller(fake_clock)
    hand = hand_factory("index")
    establish_point(controller, fake_clock, hand)
    controller.enable()
    assert controller.state.name == "ENABLED"
    assert controller.update(hand).action is CursorAction.MOVE


def test_unknown_noise_preserves_motion_until_the_new_gesture_is_confirmed(
    hand_factory, fake_clock
):
    controller = make_controller(fake_clock)
    establish_point(
        controller, fake_clock, at_indicator(hand_factory("index"), 0.1, 0.1)
    )
    unknown = at_indicator(hand_factory("index", "middle"), 0.9, 0.9)
    fake_clock.now = 0.1
    moved = controller.update(unknown)
    assert moved.action is CursorAction.MOVE and moved.x == pytest.approx(500)
    fake_clock.now = 0.14
    assert controller.update(hand_factory("index")).action is CursorAction.MOVE
    fake_clock.now = 0.2
    controller.update(unknown)
    fake_clock.now = 0.28
    assert controller.update(unknown).action is CursorAction.NONE


def test_tracking_gap_freezes_output_preserves_ema_then_long_loss_resets_it(
    hand_factory, fake_clock
):
    controller = make_controller(fake_clock)
    point = hand_factory("index")
    establish_point(controller, fake_clock, at_indicator(point, 0.1, 0.1))
    fake_clock.now = 0.1
    assert controller.update(None).action is CursorAction.NONE
    fake_clock.now = 0.14
    assert controller.update(at_indicator(point, 0.9, 0.9)).x == pytest.approx(500)
    fake_clock.now = 0.2
    controller.update(None)
    fake_clock.now = 0.36
    controller.update(None)
    fake_clock.now = 0.4
    assert controller.update(at_indicator(point, 0.9, 0.9)).action is CursorAction.NONE
    fake_clock.now = 0.48
    resumed = controller.update(at_indicator(point, 0.9, 0.9))
    assert resumed.action is CursorAction.MOVE and resumed.x == pytest.approx(1000)


def test_pinch_uses_last_smoothed_position_once_and_short_loss_does_not_rearm(
    hand_factory, fake_clock
):
    controller = make_controller(fake_clock)
    point = at_indicator(hand_factory("index"), 0.3, 0.4)
    establish_point(controller, fake_clock, point)
    last = controller.sink.commands[-1]
    pinch = pinched(at_indicator(hand_factory("index"), 0.8, 0.8))
    fake_clock.now = 0.1
    assert controller.update(pinch).action is CursorAction.NONE
    fake_clock.now = 0.18
    click = controller.update(pinch)
    assert click.action is CursorAction.CLICK and (click.x, click.y) == (last.x, last.y)
    fake_clock.now = 0.2
    controller.update(None)
    fake_clock.now = 0.24
    assert controller.update(pinch).action is CursorAction.NONE
    assert [c.action for c in controller.sink.commands].count(CursorAction.CLICK) == 1


def test_long_tracking_loss_discards_pinch_until_confirmed_release(
    hand_factory, fake_clock
):
    controller = make_controller(fake_clock)
    point, pinch = hand_factory("index"), pinched(hand_factory("index"))
    establish_point(controller, fake_clock, point)
    fake_clock.now = 0.1
    controller.update(pinch)
    fake_clock.now = 0.18
    assert controller.update(pinch).action is CursorAction.CLICK
    fake_clock.now = 0.2
    controller.update(None)
    fake_clock.now = 0.36
    controller.update(None)
    for now in (0.4, 0.48, 0.5):
        fake_clock.now = now
        assert controller.update(pinch).action is CursorAction.NONE
    for now in (0.6, 0.68):
        fake_clock.now = now
        controller.update(point)
    for now in (0.7, 0.78):
        fake_clock.now = now
        command = controller.update(pinch)
    assert command.action is CursorAction.CLICK


def test_disable_cancels_pending_click_and_reenable_starts_unarmed(
    hand_factory, fake_clock
):
    controller = make_controller(fake_clock)
    point, pinch = hand_factory("index"), pinched(hand_factory("index"))
    establish_point(controller, fake_clock, point)
    fake_clock.now = 0.1
    controller.update(pinch)
    history = controller.sink.commands
    controller.disable()
    assert controller.state.name == "DISABLED" and controller.sink.commands == history
    fake_clock.now = 1.0
    assert controller.update(pinch).action is CursorAction.NONE
    controller.enable()
    controller.update(pinch)
    fake_clock.now = 1.1
    assert controller.update(pinch).action is CursorAction.NONE
    assert all(c.action is not CursorAction.CLICK for c in controller.sink.commands)


def test_reenable_discards_ema_and_reset_disables_without_emitting(
    hand_factory, fake_clock
):
    controller = make_controller(fake_clock)
    point = hand_factory("index")
    establish_point(controller, fake_clock, at_indicator(point, 0.1, 0.1))
    controller.disable()
    establish_point(controller, fake_clock, at_indicator(point, 0.9, 0.9))
    assert controller.sink.commands[-1].x == pytest.approx(1000)
    before = controller.sink.commands
    controller.reset()
    assert controller.state.name == "DISABLED" and controller.sink.commands == before
    assert controller.update(pinched(point)).action is CursorAction.NONE


def test_invalid_hand_disables_and_propagates_instead_of_emitting_a_fake_command(
    hand_factory, fake_clock
):
    controller = make_controller(fake_clock)
    point = hand_factory("index")
    establish_point(controller, fake_clock, point)
    history = controller.sink.commands
    invalid = replace(point, landmarks=(point.landmarks[0],) * 21)
    with pytest.raises(ValueError, match="reference"):
        controller.update(invalid)
    assert controller.state.name == "DISABLED" and controller.sink.commands == history
    assert controller.update(point).action is CursorAction.NONE


@pytest.mark.parametrize("failure", [float("nan"), -1.0])
def test_bad_clock_disables_control_and_does_not_preserve_pending_click(
    hand_factory, fake_clock, failure
):
    controller = make_controller(fake_clock)
    point = hand_factory("index")
    establish_point(controller, fake_clock, point)
    fake_clock.now = failure
    with pytest.raises(ValueError, match="Clock"):
        controller.update(pinched(point))
    assert controller.state.name == "DISABLED"
    fake_clock.now = 0.0
    assert controller.update(pinched(point)).action is CursorAction.NONE


def test_failed_output_disables_and_preserves_original_error(hand_factory, fake_clock):
    class FailingDryRunSink(DryRunCursorSink):
        fail = False

        def emit(self, command):
            if self.fail:
                raise RuntimeError("Synthetic output failure")
            super().emit(command)

    sink = FailingDryRunSink()
    controller = make_controller(fake_clock, sink)
    point = hand_factory("index")
    establish_point(controller, fake_clock, point)
    sink.fail = True
    with pytest.raises(RuntimeError, match="Synthetic output failure"):
        controller.update(point)
    assert controller.state.name == "DISABLED"
    sink.fail = False
    assert controller.update(point).action is CursorAction.NONE


def test_only_dry_run_output_is_accepted_in_this_phase() -> None:
    with pytest.raises(TypeError, match="DryRunCursorSink"):
        CursorController(CursorConfig(1001, 501), sink=object())

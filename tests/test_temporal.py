"""Temporal contracts over real observations and an explicit fake clock."""

from dataclasses import replace

import pytest

from hgi.gesture_detector import Gesture, GestureObservation
from hgi.temporal import TemporalConfig, TemporalGestureFilter


def observed(pose: Gesture = Gesture.POINT, ratio: float = 1.0) -> GestureObservation:
    """A validated measurement, not a fake of any HGI implementation."""
    return GestureObservation(Gesture.PINCH if ratio <= 0.25 else pose, pose, ratio)


ABSENT = GestureObservation(Gesture.UNKNOWN, Gesture.UNKNOWN, None)


def test_gesture_requires_default_duration_and_fast_changes_restart_it(fake_clock):
    filter_ = TemporalGestureFilter(clock=fake_clock)
    assert filter_.update(observed()).gesture is Gesture.UNKNOWN
    fake_clock.now = 0.079
    assert not filter_.update(observed()).move
    fake_clock.now = 0.08
    assert filter_.update(observed()).move
    fake_clock.now = 0.1
    assert filter_.update(observed(Gesture.UNKNOWN)).gesture is Gesture.POINT
    fake_clock.now = 0.15
    assert filter_.update(observed()).move
    fake_clock.now = 0.16
    filter_.update(observed(Gesture.FIST))
    fake_clock.now = 0.2
    assert filter_.update(observed(Gesture.OPEN_HAND)).gesture is Gesture.POINT
    fake_clock.now = 0.28
    result = filter_.update(observed(Gesture.OPEN_HAND))
    assert result.gesture is Gesture.OPEN_HAND and result.reset_motion


def test_pinch_confirmation_emits_one_click_and_freezes_pending_motion(fake_clock):
    filter_ = TemporalGestureFilter(clock=fake_clock)
    filter_.update(observed())
    fake_clock.now = 0.08
    assert filter_.update(observed()).move
    fake_clock.now = 0.1
    pending = filter_.update(observed(ratio=0.2))
    assert not pending.move and not pending.click
    fake_clock.now = 0.18
    assert filter_.update(observed(ratio=0.2)).click
    fake_clock.now = 0.5
    held = filter_.update(observed(ratio=0.2))
    assert held.gesture is Gesture.PINCH and not held.click and not held.move


def test_inclusive_hysteresis_band_does_not_rearm_pinch(fake_clock):
    config = TemporalConfig(stabilization_seconds=0, click_cooldown_seconds=0)
    filter_ = TemporalGestureFilter(config, clock=fake_clock)
    filter_.update(observed())
    assert filter_.update(observed(ratio=0.25)).click
    for ratio in (0.26, 0.319, 0.25):
        result = filter_.update(observed(ratio=ratio))
        assert result.gesture is Gesture.PINCH and not result.click
    assert filter_.update(observed(ratio=0.32)).gesture is Gesture.POINT
    assert filter_.update(observed(ratio=0.25)).click


def test_exit_must_remain_open_long_enough_before_rearming(fake_clock):
    config = TemporalConfig(stabilization_seconds=0.125, click_cooldown_seconds=0)
    filter_ = TemporalGestureFilter(config, clock=fake_clock)
    for time in (0.0, 0.125):
        fake_clock.now = time
        filter_.update(observed())
    for time in (0.25, 0.375):
        fake_clock.now = time
        result = filter_.update(observed(ratio=0.2))
    assert result.click
    fake_clock.now = 0.5
    filter_.update(observed(ratio=0.32))
    fake_clock.now = 0.5625
    assert not filter_.update(observed(ratio=0.2)).click
    fake_clock.now = 0.75
    assert not filter_.update(observed(ratio=0.2)).click
    for time in (0.875, 1.0):
        fake_clock.now = time
        filter_.update(observed(ratio=0.32))
    for time in (1.125, 1.25):
        fake_clock.now = time
        result = filter_.update(observed(ratio=0.2))
    assert result.click


def test_cooldown_blocks_early_click_without_queuing_and_accepts_exact_boundary(
    fake_clock,
):
    filter_ = TemporalGestureFilter(
        TemporalConfig(stabilization_seconds=0), clock=fake_clock
    )
    filter_.update(observed())
    assert filter_.update(observed(ratio=0.2)).click
    fake_clock.now = 0.1
    filter_.update(observed())
    fake_clock.now = 0.299
    assert not filter_.update(observed(ratio=0.2)).click
    fake_clock.now = 0.3
    assert not filter_.update(observed(ratio=0.2)).click
    filter_.update(observed())
    assert filter_.update(observed(ratio=0.2)).click


def test_initial_closed_pinch_requires_confirmed_open_before_click(fake_clock):
    filter_ = TemporalGestureFilter(
        TemporalConfig(stabilization_seconds=0), clock=fake_clock
    )
    assert not filter_.update(observed(ratio=0.2)).click
    assert not filter_.update(observed(ratio=0.3)).click
    filter_.update(observed(ratio=0.32))
    assert filter_.update(observed(ratio=0.2)).click


def test_custom_hysteresis_uses_measurement_instead_of_the_raw_label(fake_clock):
    config = TemporalConfig(
        stabilization_seconds=0,
        enter_pinch_threshold=0.1,
        exit_pinch_threshold=0.3,
    )
    filter_ = TemporalGestureFilter(config, clock=fake_clock)
    sample = observed(ratio=0.2)
    assert sample.raw is Gesture.PINCH
    assert filter_.update(sample).move
    filter_.update(observed(ratio=0.3))
    assert filter_.update(observed(ratio=0.1)).click


def test_one_clock_read_per_temporal_update() -> None:
    calls = []

    def clock() -> float:
        calls.append(1)
        return 0.0

    filter_ = TemporalGestureFilter(clock=clock)
    filter_.update(observed())
    filter_.update(ABSENT)
    assert len(calls) == 2


def test_short_tracking_gap_preserves_stable_pinch_without_emitting_or_rearming(
    fake_clock,
):
    filter_ = TemporalGestureFilter(
        TemporalConfig(stabilization_seconds=0), clock=fake_clock
    )
    filter_.update(observed())
    filter_.update(observed(ratio=0.2))
    fake_clock.now = 0.1
    missing = filter_.update(ABSENT)
    assert missing.gesture is Gesture.PINCH
    assert not missing.move and not missing.click and not missing.reset_motion
    fake_clock.now = 0.14
    recovered = filter_.update(observed(ratio=0.2))
    assert recovered.gesture is Gesture.PINCH and not recovered.click


@pytest.mark.parametrize("reacquire_without_missing_update", [False, True])
def test_long_tracking_gap_clears_state_and_requires_release(
    fake_clock, reacquire_without_missing_update
):
    filter_ = TemporalGestureFilter(
        TemporalConfig(stabilization_seconds=0), clock=fake_clock
    )
    filter_.update(observed())
    filter_.update(observed(ratio=0.2))
    fake_clock.now = 0.1
    filter_.update(ABSENT)
    fake_clock.now = 0.25
    if not reacquire_without_missing_update:
        expired = filter_.update(ABSENT)
        assert expired.gesture is Gesture.UNKNOWN and expired.reset_motion
    recovered = filter_.update(observed(ratio=0.2))
    assert not recovered.click
    fake_clock.now = 0.3
    filter_.update(observed())
    assert filter_.update(observed(ratio=0.2)).click


def test_missing_samples_cancel_pending_confirmation_instead_of_counting_absence(
    fake_clock,
):
    filter_ = TemporalGestureFilter(clock=fake_clock)
    filter_.update(observed())
    fake_clock.now = 0.08
    filter_.update(observed())
    fake_clock.now = 0.1
    filter_.update(observed(ratio=0.2))
    fake_clock.now = 0.12
    filter_.update(ABSENT)
    fake_clock.now = 0.2
    assert not filter_.update(observed(ratio=0.2)).click
    fake_clock.now = 0.28
    assert filter_.update(observed(ratio=0.2)).click


def test_tracking_timeout_does_not_bypass_cooldown(fake_clock):
    config = TemporalConfig(stabilization_seconds=0, click_cooldown_seconds=1.0)
    filter_ = TemporalGestureFilter(config, clock=fake_clock)
    filter_.update(observed())
    filter_.update(observed(ratio=0.2))
    fake_clock.now = 0.1
    filter_.update(ABSENT)
    fake_clock.now = 0.25
    filter_.update(ABSENT)
    filter_.update(observed())
    assert not filter_.update(observed(ratio=0.2)).click


def test_manual_reset_clears_stable_pinch_pending_state_and_clock_epoch(fake_clock):
    filter_ = TemporalGestureFilter(
        TemporalConfig(stabilization_seconds=0), clock=fake_clock
    )
    filter_.update(observed())
    fake_clock.now = 1.0
    filter_.update(observed(ratio=0.2))
    filter_.reset()
    fake_clock.now = 0.0
    assert not filter_.update(observed(ratio=0.2)).click
    filter_.update(observed())
    assert filter_.update(observed(ratio=0.2)).click


@pytest.mark.parametrize(
    "changes",
    [
        {"enter_pinch_threshold": 0.32},
        {"exit_pinch_threshold": 0.2},
        {"enter_pinch_threshold": -1},
        {"exit_pinch_threshold": float("inf")},
        {"stabilization_seconds": -1},
        {"click_cooldown_seconds": float("nan")},
        {"tracking_grace_seconds": True},
    ],
)
def test_temporal_config_rejects_invalid_thresholds_and_times(changes):
    with pytest.raises(ValueError):
        replace(TemporalConfig(), **changes)


@pytest.mark.parametrize("bad_time", [float("nan"), float("inf"), True, -1.0])
def test_bad_or_regressing_clock_is_rejected_and_resets_click_state(
    fake_clock, bad_time
):
    filter_ = TemporalGestureFilter(
        TemporalConfig(stabilization_seconds=0), clock=fake_clock
    )
    filter_.update(observed())
    fake_clock.now = bad_time
    with pytest.raises(ValueError, match="Clock"):
        filter_.update(observed(ratio=0.2))
    fake_clock.now = 0.0
    assert not filter_.update(observed(ratio=0.2)).click


@pytest.mark.parametrize("ratio", [-1.0, float("nan"), float("inf"), True])
def test_invalid_measurements_cannot_generate_temporal_intentions(fake_clock, ratio):
    filter_ = TemporalGestureFilter(clock=fake_clock)
    with pytest.raises(ValueError, match="ratio"):
        filter_.update(observed(ratio=ratio))

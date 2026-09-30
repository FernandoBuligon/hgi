"""Mode/delegate/timestamp contracts against the installed API shape."""

from unittest.mock import Mock

import numpy as np
import pytest
import test_hand_tracker
from test_hand_tracker import raw_hand, result

from hgi.hand_tracker import HandTracker, HandTrackerError
from hgi.tracker_config import HandTrackerConfig, InferenceDelegate, RunningMode

boundary = test_hand_tracker.boundary
model = test_hand_tracker.model


@pytest.fixture
def modes(boundary):
    boundary.mp.tasks.BaseOptions.Delegate.GPU = "GPU"
    boundary.mp.tasks.vision.RunningMode.VIDEO = "VIDEO"
    boundary.mp.tasks.vision.RunningMode.LIVE_STREAM = "LIVE_STREAM"
    boundary.detector.detect_for_video = Mock(return_value=result([]))
    boundary.detector.detect_async = Mock()
    return boundary


@pytest.mark.parametrize("delegate", list(InferenceDelegate))
def test_video_uses_config_and_returns_internal_hands(modes, model, delegate):
    modes.detector.detect_for_video.return_value = result([raw_hand()])
    config = HandTrackerConfig(
        running_mode=RunningMode.VIDEO, delegate=delegate, min_tracking_confidence=0.7
    )
    with HandTracker(model, config=config) as tracker:
        hands = tracker.process(np.zeros((4, 5, 3), np.uint8), timestamp_ms=42)
    options = modes.factory.call_args.args[0]
    assert options.running_mode == "VIDEO"
    assert options.base_options.delegate == delegate.name
    assert options.min_tracking_confidence == 0.7
    assert modes.detector.detect_for_video.call_args.args[1] == 42
    assert len(hands[0].landmarks) == 21
    modes.detector.detect.assert_not_called()


def test_automatic_milliseconds_strictly_increase_even_within_same_tick(
    modes, model, fake_clock
):
    fake_clock.now = 1.234
    config = HandTrackerConfig(running_mode=RunningMode.VIDEO)
    with HandTracker(model, config=config, clock=fake_clock) as tracker:
        for _ in range(2):
            tracker.process(np.zeros((2, 2, 3), np.uint8))
        fake_clock.now = 1.240
        tracker.process(np.zeros((2, 2, 3), np.uint8))
    assert [c.args[1] for c in modes.detector.detect_for_video.call_args_list] == [
        1234,
        1235,
        1240,
    ]


@pytest.mark.parametrize("invalid", [-1, True, 1.5, 20, 19, 2**63])
def test_invalid_timestamps_never_reach_backend(modes, model, invalid):
    with HandTracker(
        model, config=HandTrackerConfig(running_mode=RunningMode.VIDEO)
    ) as tracker:
        frame = np.zeros((2, 2, 3), np.uint8)
        tracker.process(frame, timestamp_ms=20)
        with pytest.raises(ValueError, match="timestamp"):
            tracker.process(frame, timestamp_ms=invalid)
    assert modes.detector.detect_for_video.call_count == 1


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1, True, 1.0, 1e308])
def test_invalid_or_regressing_clock_rejected(modes, model, fake_clock, invalid):
    fake_clock.now = 2.0
    with HandTracker(
        model,
        config=HandTrackerConfig(running_mode=RunningMode.VIDEO),
        clock=fake_clock,
    ) as tracker:
        tracker.process(np.zeros((2, 2, 3), np.uint8))
        fake_clock.now = invalid
        with pytest.raises(ValueError, match="Clock"):
            tracker.process(np.zeros((2, 2, 3), np.uint8))


@pytest.mark.parametrize(
    "values",
    [
        {"running_mode": "video"},
        {"delegate": "gpu"},
        {"min_tracking_confidence": float("nan")},
        {"num_hands": True},
    ],
)
def test_configuration_is_typed_and_validated(values):
    with pytest.raises(ValueError):
        HandTrackerConfig(**values)


def test_gpu_error_is_actionable_preserves_cause_and_does_not_fall_back(modes, model):
    original = RuntimeError("EGL initialization failed")
    modes.factory.side_effect = original
    with pytest.raises(HandTrackerError, match="--delegate cpu") as caught:
        HandTracker(model, config=HandTrackerConfig(delegate=InferenceDelegate.GPU))
    assert caught.value.__cause__ is original
    modes.factory.assert_called_once()


def test_config_and_legacy_keywords_cannot_conflict(modes, model):
    with pytest.raises(ValueError, match="config"):
        HandTracker(model, config=HandTrackerConfig(), num_hands=2)


def test_image_rejects_unused_timestamp(modes, model):
    with HandTracker(model) as tracker, pytest.raises(ValueError, match="IMAGE"):
        tracker.process(np.zeros((2, 2, 3), np.uint8), timestamp_ms=1)


def test_live_mailbox_is_bounded_result_consumed_once_and_no_callback_actions(
    modes, model, fake_clock
):
    config = HandTrackerConfig(running_mode=RunningMode.LIVE_STREAM)
    with HandTracker(model, config=config, performance_clock=fake_clock) as tracker:
        frame = np.zeros((2, 3, 3), np.uint8)
        callback = modes.factory.call_args.args[0].result_callback
        assert tracker.submit(frame, timestamp_ms=1)
        assert not tracker.submit(frame, timestamp_ms=2)  # Busy: no native backlog.
        assert tracker.poll() is None
        fake_clock.now = 0.02
        callback(result([raw_hand()]), None, 1)
        sample = tracker.poll()
        assert sample.timestamp_ms == 1 and sample.shape == (2, 3)
        assert sample.latency_seconds == pytest.approx(0.02)
        assert len(sample.hands[0].landmarks) == 21
        assert tracker.poll() is None
        assert tracker.submit(frame, timestamp_ms=3)
        callback(result([]), None, 3)
        assert tracker.poll().hands == ()  # Absence differs from pending.
        assert modes.detector.detect_async.call_count == 2
        with pytest.raises(ValueError, match="submit"):
            tracker.process(frame)
    callback(result([]), None, 3)  # A late callback cannot restore a closed tracker.
    with pytest.raises(RuntimeError, match="closed"):
        tracker.poll()


def test_live_callback_failure_propagates_on_owner_thread_without_new_submission(
    modes, model
):
    with HandTracker(
        model, config=HandTrackerConfig(running_mode=RunningMode.LIVE_STREAM)
    ) as tracker:
        frame = np.zeros((2, 2, 3), np.uint8)
        tracker.submit(frame, timestamp_ms=1)
        callback = modes.factory.call_args.args[0].result_callback
        callback(result([raw_hand()[:20]]), None, 1)
        with pytest.raises(ValueError, match="21"):
            tracker.poll()
        with pytest.raises(ValueError, match="21"):
            tracker.submit(frame, timestamp_ms=2)
    assert modes.detector.detect_async.call_count == 1


def test_live_backend_failure_keeps_cause_and_does_not_lock_shutdown(modes, model):
    error = RuntimeError("async native failure")
    modes.detector.detect_async.side_effect = error
    with HandTracker(
        model, config=HandTrackerConfig(running_mode=RunningMode.LIVE_STREAM)
    ) as tracker:
        with pytest.raises(HandTrackerError) as caught:
            tracker.submit(np.zeros((2, 2, 3), np.uint8))
    assert caught.value.__cause__ is error
    modes.detector.close.assert_called_once()


def test_live_missing_callback_fails_visibly_and_stops_submission(
    modes, model, fake_clock
):
    with HandTracker(
        model,
        config=HandTrackerConfig(running_mode=RunningMode.LIVE_STREAM),
        performance_clock=fake_clock,
    ) as tracker:
        tracker.submit(np.zeros((2, 2, 3), np.uint8))
        fake_clock.now = 5
        with pytest.raises(HandTrackerError, match="timed out"):
            tracker.poll()
        with pytest.raises(HandTrackerError, match="timed out"):
            tracker.submit(np.zeros((2, 2, 3), np.uint8))
    assert modes.detector.detect_async.call_count == 1


def test_callback_latches_the_first_exception(modes, model):
    with HandTracker(
        model, config=HandTrackerConfig(running_mode=RunningMode.LIVE_STREAM)
    ) as tracker:
        tracker.submit(np.zeros((2, 2, 3), np.uint8))
        callback = modes.factory.call_args.args[0].result_callback
        callback(result([raw_hand()[:20]]), None, 1)
        with pytest.raises(ValueError) as first:
            tracker.poll()
        malformed = raw_hand()
        malformed[0].x = float("nan")
        callback(result([malformed]), None, 1)
        with pytest.raises(ValueError) as second:
            tracker.poll()
        assert second.value is first.value

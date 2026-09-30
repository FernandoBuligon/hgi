"""Deterministic observability; no hardware or FPS pass/fail thresholds."""

import pytest

from hgi.benchmark import FrameTiming, summarize


def test_rates_latency_and_percentiles_use_completed_frames_and_wall_time():
    samples = [
        FrameTiming(0.01, 0.002, 0.02, 0.032),
        FrameTiming(0.02, 0.004, 0.04, 0.064),
    ]
    report = summarize(samples, duration=0.2, captured=3)
    assert report.captured == 3 and report.processed == 2
    assert report.capture_fps == 15 and report.inference_fps == 10
    assert report.mean_inference_ms == pytest.approx(30)
    assert report.mean_latency_ms == pytest.approx(48)
    assert report.min_frame_fps == pytest.approx(1 / 0.064)
    assert report.p95_inference_ms == 40
    assert report.mean_capture_ms == 15


def test_empty_benchmark_is_explicit_not_division_by_zero():
    report = summarize([], duration=1, captured=0)
    assert report.processed == 0 and report.inference_fps == 0
    assert report.mean_inference_ms is None


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf")])
def test_invalid_duration_rejected(duration):
    with pytest.raises(ValueError):
        summarize([], duration=duration, captured=0)

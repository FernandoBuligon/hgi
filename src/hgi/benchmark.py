"""Small timing summaries, independent of vision and mouse backends."""

from dataclasses import dataclass
from math import ceil, isfinite
from statistics import fmean


@dataclass(frozen=True, slots=True)
class FrameTiming:
    """Seconds from read start through result conversion; excludes startup."""

    capture_seconds: float
    conversion_seconds: float
    inference_seconds: float
    total_seconds: float


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Wall-time throughput and per-completed-frame timing are separate."""

    captured: int
    processed: int
    duration: float
    capture_fps: float
    inference_fps: float
    min_frame_fps: float | None
    mean_capture_ms: float | None
    mean_conversion_ms: float | None
    mean_inference_ms: float | None
    mean_latency_ms: float | None
    min_inference_ms: float | None
    max_inference_ms: float | None
    p95_inference_ms: float | None


def summarize(
    samples: list[FrameTiming], *, duration: float, captured: int
) -> BenchmarkReport:
    """Aggregate observations; p95 uses nearest rank, no hardware assertions."""
    if not isfinite(duration) or duration <= 0:
        raise ValueError("Duration must be finite and positive")
    if captured < len(samples):
        raise ValueError("Captured count cannot be smaller than processed count")
    infer = sorted(s.inference_seconds * 1000 for s in samples)
    total = [s.total_seconds for s in samples]
    return BenchmarkReport(
        captured,
        len(samples),
        duration,
        captured / duration,
        len(samples) / duration,
        1 / max(total) if total and max(total) > 0 else None,
        fmean(s.capture_seconds for s in samples) * 1000 if samples else None,
        fmean(s.conversion_seconds for s in samples) * 1000 if samples else None,
        fmean(infer) if infer else None,
        fmean(total) * 1000 if total else None,
        min(infer) if infer else None,
        max(infer) if infer else None,
        infer[ceil(0.95 * len(infer)) - 1] if infer else None,
    )

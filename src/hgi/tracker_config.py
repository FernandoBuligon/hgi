"""Typed inference settings, importable without native vision dependencies."""

from argparse import ArgumentParser
from dataclasses import dataclass
from enum import Enum
from math import isfinite


class RunningMode(Enum):
    """MediaPipe execution modes; application semantics remain independent."""

    IMAGE = "image"
    VIDEO = "video"
    LIVE_STREAM = "live-stream"


class InferenceDelegate(Enum):
    """Explicit acceleration selection; CPU remains the portable default."""

    CPU = "cpu"
    GPU = "gpu"


@dataclass(frozen=True, slots=True)
class HandTrackerConfig:
    """One validated source of inference options, not gesture thresholds."""

    running_mode: RunningMode = RunningMode.IMAGE
    delegate: InferenceDelegate = InferenceDelegate.CPU
    num_hands: int = 1
    min_hand_detection_confidence: float = 0.5
    min_hand_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5

    def __post_init__(self) -> None:
        if not isinstance(self.running_mode, RunningMode) or not isinstance(
            self.delegate, InferenceDelegate
        ):
            raise ValueError("running_mode and delegate must use HGI enums")
        if (
            isinstance(self.num_hands, bool)
            or not isinstance(self.num_hands, int)
            or self.num_hands < 1
        ):
            raise ValueError("num_hands must be a positive integer")
        for value in (
            self.min_hand_detection_confidence,
            self.min_hand_presence_confidence,
            self.min_tracking_confidence,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError("Confidence thresholds must be finite and in [0, 1]")


def add_inference_arguments(parser: ArgumentParser) -> None:
    """Share the supported modes/delegates between demo and benchmark help."""
    parser.add_argument(
        "--running-mode",
        choices=[m.value for m in RunningMode],
        default=RunningMode.IMAGE.value,
        help="image: baseline synchronous; video: tracking-aware synchronous; "
        "live-stream: asynchronous, latency-oriented",
    )
    parser.add_argument(
        "--delegate",
        choices=[d.value for d in InferenceDelegate],
        default=InferenceDelegate.CPU.value,
        help="inference delegate; GPU is explicit opt-in and may be unavailable",
    )

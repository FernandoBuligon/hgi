"""Explicit inference benchmark; never constructs a mouse backend or window."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import asdict
from math import isfinite
from pathlib import Path
from time import perf_counter, sleep
from typing import TYPE_CHECKING

from hgi.benchmark import FrameTiming, summarize
from hgi.tracker_config import (
    HandTrackerConfig,
    InferenceDelegate,
    RunningMode,
    add_inference_arguments,
)

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from hgi.hand_landmarks import DetectedHand
    from hgi.hand_tracker import HandTracker


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HGI HandTracker Benchmark (no mouse control, no recording)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("models/hand_landmarker.task"),
        help="local model; see docs/MODELS.md",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--camera",
        type=int,
        help="webcam index; otherwise use a preloaded synthetic black frame",
    )
    source.add_argument(
        "--image", type=Path, help="preload a local image instead of opening webcam"
    )
    parser.add_argument(
        "--width", type=int, default=640, help="synthetic or requested camera width"
    )
    parser.add_argument(
        "--height", type=int, default=480, help="synthetic or requested camera height"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=15,
        help="measurement seconds, excluding initialization and warmup",
    )
    parser.add_argument("--warmup", type=int, default=10, help="untimed warmup frames")
    parser.add_argument(
        "--json", action="store_true", help="machine-readable summary on stdout"
    )
    add_inference_arguments(parser)
    return parser


def _infer(tracker: HandTracker, rgb: NDArray[np.uint8]) -> tuple[DetectedHand, ...]:
    """Serialize submission/completion for comparable inference microbenchmarks."""
    if tracker.config.running_mode is not RunningMode.LIVE_STREAM:
        return tracker.process(rgb)
    tracker.submit(rgb)
    deadline = perf_counter() + 5
    while perf_counter() < deadline:
        result = tracker.poll()
        if result is not None:
            return result.hands
        sleep(0.001)
    raise RuntimeError("LIVE_STREAM callback timed out after 5 seconds")


def _measure(
    tracker: HandTracker,
    read_frame: Callable[[], NDArray[np.uint8]],
    args: argparse.Namespace,
) -> dict[str, object]:
    import cv2

    for _ in range(args.warmup):
        _infer(tracker, cv2.cvtColor(read_frame(), cv2.COLOR_BGR2RGB))
    samples: list[FrameTiming] = []
    detected = 0
    shape = None
    start = perf_counter()
    while perf_counter() - start < args.duration:
        before = perf_counter()
        bgr = read_frame()
        read = perf_counter()
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        converted = perf_counter()
        hands = _infer(tracker, rgb)
        completed = perf_counter()
        detected += bool(hands)
        shape = list(bgr.shape[:2][::-1])
        samples.append(
            FrameTiming(
                read - before,
                converted - read,
                completed - converted,
                completed - before,
            )
        )
    elapsed = perf_counter() - start
    return {
        "resolution": shape,
        "frames_with_hands": detected,
        **asdict(summarize(samples, duration=elapsed, captured=len(samples))),
    }


def _run(args: argparse.Namespace) -> dict[str, object]:
    import cv2
    import numpy as np

    from hgi.camera import Camera
    from hgi.hand_tracker import HandTracker

    if not args.model.expanduser().is_file():
        raise FileNotFoundError(f"Model missing: {args.model}; see docs/MODELS.md")
    frame = np.zeros((args.height, args.width, 3), np.uint8)
    if args.image:
        frame = cv2.imread(str(args.image.expanduser()))
        if frame is None:
            raise ValueError(f"Could not read image: {args.image}")
    config = HandTrackerConfig(
        running_mode=RunningMode(args.running_mode),
        delegate=InferenceDelegate(args.delegate),
    )
    camera = (
        Camera(args.camera, width=args.width, height=args.height)
        if args.camera is not None
        else nullcontext()
    )
    with camera as capture, HandTracker(args.model, config=config) as tracker:
        reported_fps = capture.reported_fps if capture is not None else None
        read_frame = capture.read if capture is not None else lambda: frame
        measurements = _measure(tracker, read_frame, args)
    return {
        "source": "camera"
        if args.camera is not None
        else "image"
        if args.image
        else "synthetic (no hands)",
        "delegate": config.delegate.name,
        "mode": config.running_mode.name,
        "reported_camera_fps": reported_fps,
        "render_fps": None,
        "live_policy": "serial submit/wait; includes polling overhead"
        if config.running_mode is RunningMode.LIVE_STREAM
        else None,
        **measurements,
    }


def main(argv: list[str] | None = None) -> int:
    """Validate options and report observations/errors without native tracebacks."""
    parser = _parser()
    args = parser.parse_args(argv)
    if not isfinite(args.duration) or args.duration <= 0 or args.warmup < 0:
        parser.error("duration must be finite and positive; warmup nonnegative")
    if (
        args.width <= 0
        or args.height <= 0
        or (args.camera is not None and args.camera < 0)
    ):
        parser.error("width/height must be positive; camera index nonnegative")
    try:
        import cv2
    except ImportError as error:
        print(f"HGI benchmark: install HGI [vision]: {error}", file=sys.stderr)
        return 1
    try:
        output = _run(args)
        if args.json:
            print(json.dumps(output, indent=2))
        else:
            print("HGI HandTracker Benchmark\n")
            for key, value in output.items():
                print(
                    f"{key}: {value:.3f}"
                    if isinstance(value, float)
                    else f"{key}: {value}"
                )
        return 0
    except (ImportError, OSError, RuntimeError, ValueError, cv2.error) as error:
        print(f"HGI benchmark: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

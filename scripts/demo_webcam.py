"""Webcam demo: enable virtual intentions only, never system mouse or keys."""

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Parse settings and report known setup/runtime errors with nonzero exit."""
    parser = argparse.ArgumentParser(description="HGI webcam - exclusively DRY-RUN")
    parser.add_argument(
        "--model", type=Path, default=Path("models/hand_landmarker.task")
    )
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--screen-width", type=int, default=1920)
    parser.add_argument("--screen-height", type=int, default=1080)
    args = parser.parse_args(argv)
    try:
        import cv2

        from hgi.camera import CameraError
        from hgi.hand_tracker import HandTrackerError
        from hgi.webcam import DemoConfig, DisplayError, run_webcam
    except ImportError as error:
        print(
            f"Vision dependencies unavailable: {error}. "
            "Install HGI [vision]; see README.md.",
            file=sys.stderr,
        )
        return 1
    try:
        run_webcam(
            DemoConfig(
                args.model,
                args.camera,
                args.width,
                args.height,
                args.screen_width,
                args.screen_height,
            )
        )
    except (
        CameraError,
        HandTrackerError,
        DisplayError,
        FileNotFoundError,
        ValueError,
        cv2.error,
    ) as error:
        print(f"HGI: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

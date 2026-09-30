"""Webcam demo: default dry-run; real mouse needs --real-control and E."""

import argparse
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    """Describe explicit output opt-in without importing hardware libraries."""
    parser = argparse.ArgumentParser(description="HGI webcam - DRY-RUN by default")
    parser.add_argument(
        "--model", type=Path, default=Path("models/hand_landmarker.task")
    )
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--screen-width", type=int)
    parser.add_argument("--screen-height", type=int)
    parser.add_argument(
        "--real-control",
        action="store_true",
        help="select real mouse output; session still starts DISABLED (E enables)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse settings and report known setup/runtime errors with nonzero exit."""
    parser = _parser()
    args = parser.parse_args(argv)
    if (args.screen_width is None) != (args.screen_height is None):
        parser.error("Supply both --screen-width and --screen-height or neither")
    try:
        import cv2

        from hgi.camera import CameraError
        from hgi.hand_tracker import HandTrackerError
        from hgi.real_cursor import RealCursorError
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
                args.real_control,
            )
        )
    except (
        CameraError,
        HandTrackerError,
        DisplayError,
        RealCursorError,
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

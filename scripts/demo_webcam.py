"""Webcam demo: default dry-run; real mouse needs --real-control and E."""

import argparse
import sys
from pathlib import Path

from hgi.tracker_config import (
    HandTrackerConfig,
    InferenceDelegate,
    RunningMode,
    add_inference_arguments,
)


def _parser() -> argparse.ArgumentParser:
    """Describe explicit output opt-in without importing hardware libraries."""
    parser = argparse.ArgumentParser(
        description="HGI webcam - DRY-RUN by default; session starts DISABLED",
        epilog="Window controls: E enable, D disable, R reset + disable, Q/Esc quit.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("models/hand_landmarker.task"),
        help="local MediaPipe model; prepare it explicitly using docs/MODELS.md",
    )
    parser.add_argument("--camera", type=int, default=0, help="webcam device index")
    parser.add_argument(
        "--width", type=int, default=640, help="requested camera width in pixels"
    )
    parser.add_argument(
        "--height", type=int, default=480, help="requested camera height in pixels"
    )
    parser.add_argument(
        "--screen-width",
        type=int,
        help="paired with --screen-height; logical pixels, or real screen override",
    )
    parser.add_argument(
        "--screen-height",
        type=int,
        help="paired with --screen-width; default: 1920x1080 dry-run, detected if real",
    )
    parser.add_argument(
        "--real-control",
        action="store_true",
        help="select real mouse output; session still starts DISABLED (E enables)",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        help="directory for real PEACE screenshots; dry-run only shows intention",
    )
    parser.add_argument(
        "--spotify-track-uri",
        help="spotify:track URI used by ROCK; defaults to Highway to Hell",
    )
    add_inference_arguments(parser)
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
            'Install with: python -m pip install -e ".[vision]"; see README.md.',
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
                HandTrackerConfig(
                    running_mode=RunningMode(args.running_mode),
                    delegate=InferenceDelegate(args.delegate),
                ),
                args.screenshot_dir
                if args.screenshot_dir is not None
                else DemoConfig().screenshot_directory,
                args.spotify_track_uri
                if args.spotify_track_uri is not None
                else DemoConfig().spotify_track_uri,
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
        if isinstance(error, CameraError):
            alternative = 1 if args.camera == 0 else 0
            print(
                f"Try another camera index, for example: --camera {alternative}",
                file=sys.stderr,
            )
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

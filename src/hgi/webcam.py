"""Visual integration with default dry-run and explicitly selected real output."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from hgi.camera import Camera, validate_bgr_frame
from hgi.click_feedback import ClickFeedback
from hgi.cursor import DryRunCursorSink
from hgi.cursor_controller import CursorConfig, CursorController
from hgi.finger_state import GestureConfig
from hgi.geometry import Point2D, normalized_to_pixels
from hgi.gesture_detector import GestureDetector
from hgi.hand_landmarks import DetectedHand
from hgi.hand_tracker import HandTracker
from hgi.overlay import OverlayState, draw_overlay
from hgi.real_cursor import RealCursorSink
from hgi.temporal import TemporalGestureFilter


class DisplayError(RuntimeError):
    """A graphical session is unavailable for the OpenCV demo."""


class FrameTracker(Protocol):
    """RGB inference boundary usable by the real tracker and synthetic fakes."""

    def process(self, frame: NDArray[np.uint8]) -> tuple[DetectedHand, ...]:
        """Return internal HGI hands for one RGB frame."""
        ...


@dataclass(frozen=True, slots=True)
class DemoConfig:
    """Camera settings and opt-in output; None dimensions select mode defaults."""

    model_path: Path = Path("models/hand_landmarker.task")
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    screen_width: int | None = None
    screen_height: int | None = None
    real_control: bool = False

    def __post_init__(self) -> None:
        normalized_to_pixels(Point2D(0, 0), self.frame_width, self.frame_height)
        if (self.screen_width is None) != (self.screen_height is None):
            raise ValueError("Supply both screen dimensions or neither")
        if self.screen_width is not None and self.screen_height is not None:
            normalized_to_pixels(Point2D(0, 0), self.screen_width, self.screen_height)
        if not isinstance(self.real_control, bool):
            raise ValueError("real_control must be an explicit boolean")
        if (
            isinstance(self.camera_index, bool)
            or not isinstance(self.camera_index, int)
            or self.camera_index < 0
        ):
            raise ValueError("Camera index must be a nonnegative integer")


def configure_output(
    config: DemoConfig,
) -> tuple[CursorConfig, DryRunCursorSink | RealCursorSink]:
    """Choose output before capture; only real opt-in queries the monitor.

    Paired overrides define a top-left rectangle within the detected screen.
    Real startup errors propagate; never silently substitute a different mode.
    """
    sink: DryRunCursorSink | RealCursorSink
    if config.real_control:
        sink = RealCursorSink(
            screen_width=config.screen_width, screen_height=config.screen_height
        )
        width, height = sink.screen_width, sink.screen_height
    else:
        sink = DryRunCursorSink(max_history=1)
        width = config.screen_width if config.screen_width is not None else 1920
        height = config.screen_height if config.screen_height is not None else 1080
    return CursorConfig(width, height, mirror_x=False), sink


def select_hand(hands: tuple[DetectedHand, ...]) -> DetectedHand | None:
    """Prefer highest Left/Right score, first on ties/missing scores; no identity.

    The tracker exposes handedness confidence, not detection confidence. A
    change of selected hand is not detected; use R/E explicitly when switching.
    """
    return max(
        hands,
        key=lambda hand: (
            hand.handedness_score if hand.handedness_score is not None else -1
        ),
        default=None,
    )


class WebcamPipeline:
    """Mirror BGR, convert to RGB, infer, update virtual output and draw BGR.

    Default controller remains DISABLED. The same measured observation feeds
    controller and overlay when enabled. Disabled sessions measure raw gestures
    only for display. Changing delivered dimensions disables/restarts state.
    """

    def __init__(
        self,
        tracker: FrameTracker,
        config: CursorConfig,
        *,
        sink: DryRunCursorSink | RealCursorSink | None = None,
        clock: Callable[[], float] = monotonic,
        ui_clock: Callable[[], float] = monotonic,
    ) -> None:
        if config.mirror_x:
            raise ValueError("Mirrored demo input requires CursorConfig mirror_x=False")
        self._tracker = tracker
        self._config = config
        self._clock = clock
        self._click_feedback = ClickFeedback(clock=ui_clock)
        self._shape: tuple[int, int] | None = None
        self._sink = sink if sink is not None else DryRunCursorSink(max_history=1)
        self._configure(1.0)

    def _configure(self, aspect: float) -> None:
        self._detector = GestureDetector(GestureConfig(image_aspect_ratio=aspect))
        self._temporal = TemporalGestureFilter(clock=self._clock)
        self._controller = CursorController(
            self._config,
            sink=self._sink,
            detector=self._detector,
            temporal=self._temporal,
        )

    @property
    def controller(self) -> CursorController:
        """Current initially disabled session for explicit window controls."""
        return self._controller

    def process(
        self, frame: NDArray[np.uint8], *, fps: float = 0.0
    ) -> tuple[NDArray[np.uint8], OverlayState]:
        """Use actual frame shape; return annotated BGR and public snapshots.

        Input stays unchanged; mirroring creates the display/inference frame.
        Unexpected inference/drawing failures disable and propagate unchanged.
        """
        try:
            validate_bgr_frame(frame)
            shape = frame.shape[:2]
            if shape != self._shape:
                self._controller.disable()
                self._configure(shape[1] / shape[0])
                self._shape = shape
            bgr = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            hand = select_hand(self._tracker.process(rgb))
            command = self._controller.update(hand)
            observation = self._controller.observation
            if observation is None:
                observation = self._detector.observe(hand)
            state = OverlayState(
                hand,
                observation,
                command,
                self._controller.state,
                self._controller.position,
                self._temporal.status,
                fps,
                self._click_feedback.update(command.action),
                self._sink.mode,
            )
            return draw_overlay(bgr, state, self._config), state
        except BaseException:
            # Cleanup only; do not turn broken inference into a missing hand.
            self._controller.disable()
            raise

    def handle_key(self, key: int) -> bool:
        """Handle demo keys; R also resets UI count/feedback, D/E preserve them."""
        quit_requested = handle_key(key, self._controller)
        if key & 0xFF in (ord("r"), ord("R")):
            self._click_feedback.reset()
        return quit_requested


def handle_key(key: int, controller: CursorController) -> bool:
    """Consume only an OpenCV-window key; return True on Q/Esc. No OS input."""
    key &= 0xFF
    if key in (ord("q"), ord("Q"), 27):
        controller.disable()
        return True
    if key in (ord("e"), ord("E")):
        controller.enable()
    elif key in (ord("d"), ord("D")):
        controller.disable()
    elif key in (ord("r"), ord("R")):
        controller.reset()
    return False


def run_webcam(config: DemoConfig) -> None:
    """Run until Q/Esc/window close or failure; always release all resources."""
    model = config.model_path.expanduser().resolve()
    if not model.is_file():
        raise FileNotFoundError(
            f"Hand Landmarker model absent: {model}. "
            "See docs/MODELS.md; no automatic download."
        )
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        raise DisplayError(
            "OpenCV window needs a graphical session (DISPLAY/WAYLAND_DISPLAY)"
        )
    pipeline: WebcamPipeline | None = None
    try:
        cursor_config, sink = configure_output(config)
        window_name = f"HGI - {sink.mode.value}"
        with (
            Camera(
                config.camera_index,
                width=config.frame_width,
                height=config.frame_height,
            ) as camera,
            HandTracker(model) as tracker,
        ):
            pipeline = WebcamPipeline(
                tracker,
                cursor_config,
                sink=sink,
            )
            cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
            previous, fps = monotonic(), 0.0
            while True:
                frame, _ = pipeline.process(camera.read(), fps=fps)
                now = monotonic()
                elapsed = now - previous
                fps = 1.0 / elapsed if elapsed > 0 else 0.0
                previous = now
                cv2.imshow(window_name, frame)
                if pipeline.handle_key(cv2.waitKey(1)):
                    break
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
    finally:
        if pipeline is not None:
            pipeline.controller.disable()
        cv2.destroyAllWindows()

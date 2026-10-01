"""Visual integration with default dry-run and explicitly selected real output."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from time import monotonic, perf_counter
from typing import Protocol, TypeVar, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from hgi.camera import Camera, validate_bgr_frame
from hgi.click_feedback import ClickFeedback
from hgi.cursor import ControlState, CursorAction, CursorCommand, DryRunCursorSink
from hgi.cursor_controller import CursorConfig, CursorController
from hgi.finger_state import GestureConfig
from hgi.geometry import Point2D, normalized_to_pixels
from hgi.gesture_detector import Gesture, GestureDetector
from hgi.hand_landmarks import DetectedHand
from hgi.hand_tracker import HandTracker, LiveResult
from hgi.overlay import OverlayState, draw_overlay
from hgi.performance import PipelineMetrics, RateMeter
from hgi.real_cursor import RealCursorSink
from hgi.temporal import TemporalConfig, TemporalGestureFilter
from hgi.tracker_config import HandTrackerConfig, RunningMode


class DisplayError(RuntimeError):
    """A graphical session is unavailable for the OpenCV demo."""


class FrameTracker(Protocol):
    """RGB inference boundary usable by the real tracker and synthetic fakes."""

    def process(self, frame: NDArray[np.uint8]) -> tuple[DetectedHand, ...]:
        """Return internal HGI hands for one RGB frame."""
        ...


class LiveFrameTracker(Protocol):
    """Bounded asynchronous tracker; only the owner thread consumes results."""

    def submit(self, frame: NDArray[np.uint8]) -> bool:
        """Return False if the single inference slot is busy."""
        ...

    def poll(self) -> LiveResult | None:
        """Consume one new internal sample, or return None while pending."""
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
    tracker: HandTrackerConfig = HandTrackerConfig()

    def __post_init__(self) -> None:
        normalized_to_pixels(Point2D(0, 0), self.frame_width, self.frame_height)
        if (self.screen_width is None) != (self.screen_height is None):
            raise ValueError("Supply both screen dimensions or neither")
        if self.screen_width is not None and self.screen_height is not None:
            normalized_to_pixels(Point2D(0, 0), self.screen_width, self.screen_height)
        if not isinstance(self.real_control, bool):
            raise ValueError("real_control must be an explicit boolean")
        if not isinstance(self.tracker, HandTrackerConfig):
            raise ValueError("tracker must be a HandTrackerConfig")
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
    """Mirror BGR, convert to RGB, infer, update the selected sink and draw BGR.

    Default controller remains DISABLED. The same measured observation feeds
    controller and overlay when enabled. Disabled sessions measure raw gestures
    only for display. Changing delivered dimensions disables/restarts state.
    """

    def __init__(
        self,
        tracker: FrameTracker | LiveFrameTracker,
        config: CursorConfig,
        *,
        sink: DryRunCursorSink | RealCursorSink | None = None,
        clock: Callable[[], float] = monotonic,
        ui_clock: Callable[[], float] = monotonic,
        tracker_config: HandTrackerConfig | None = None,
        performance_clock: Callable[[], float] = perf_counter,
    ) -> None:
        if config.mirror_x:
            raise ValueError("Mirrored demo input requires CursorConfig mirror_x=False")
        self._tracker = tracker
        self._config = config
        self._clock = clock
        self._tracker_config = (
            tracker_config if tracker_config is not None else HandTrackerConfig()
        )
        self._performance_clock = performance_clock
        self._inference_rate = RateMeter()
        self._inference_rate.rate(performance_clock())
        self._inference_ms = 0.0
        self._overlay_ms = 0.0
        self._last_hand: DetectedHand | None = None
        self._last_result_at: float | None = None
        self._recovering = False
        self._accept_after = float("-inf")
        self._temporal_config = TemporalConfig()
        self._click_feedback = ClickFeedback(clock=ui_clock)
        self._shape: tuple[int, int] | None = None
        self._sink = sink if sink is not None else DryRunCursorSink(max_history=1)
        self._configure(1.0)

    def _configure(self, aspect: float) -> None:
        self._detector = GestureDetector(GestureConfig(image_aspect_ratio=aspect))
        self._temporal = TemporalGestureFilter(
            config=self._temporal_config, clock=self._clock
        )
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
        self,
        frame: NDArray[np.uint8],
        *,
        fps: float = 0.0,
        capture_seconds: float = 0.0,
    ) -> tuple[NDArray[np.uint8], OverlayState]:
        """Prepare, sample and render; any failure disables and propagates."""
        try:
            bgr, rgb, conversion_seconds = self._prepare(frame)
            state, drawing_start = self._observe(
                rgb,
                fps=fps,
                capture_seconds=capture_seconds,
                conversion_seconds=conversion_seconds,
            )
            rendered = draw_overlay(bgr, state, self._config)
            self._overlay_ms = (self._performance_clock() - drawing_start) * 1000
            assert state.metrics is not None
            return rendered, replace(
                state, metrics=replace(state.metrics, overlay_ms=self._overlay_ms)
            )
        except BaseException:
            # Cleanup only; do not turn broken inference into a missing hand.
            self._controller.disable()
            raise

    def _prepare(
        self, frame: NDArray[np.uint8]
    ) -> tuple[NDArray[np.uint8], NDArray[np.uint8], float]:
        """Keep source BGR unchanged and reset safely on delivered shape changes."""
        validate_bgr_frame(frame)
        shape = frame.shape[:2]
        if shape != self._shape:
            if self._shape is not None:
                self._accept_after = self._performance_clock()
            self._controller.disable()
            self._configure(shape[1] / shape[0])
            self._shape = shape
            self._last_hand = None
            self._last_result_at = None
            self._recovering = False
        bgr = cv2.flip(frame, 1)
        before = self._performance_clock()
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return bgr, rgb, self._performance_clock() - before

    def _observe(
        self,
        rgb: NDArray[np.uint8],
        *,
        fps: float,
        capture_seconds: float,
        conversion_seconds: float,
    ) -> tuple[OverlayState, float]:
        """Sample each result once and construct public UI/timing snapshots."""
        hand, fresh = self._infer(rgb)
        inferred = self._performance_clock()
        command = (
            self._controller.update(hand) if fresh else CursorCommand(CursorAction.NONE)
        )
        if (
            self._recovering
            and self._temporal.status.stable is Gesture.UNKNOWN
            and not self._temporal.status.armed
        ):
            self._recovering = False
        observation = self._controller.observation
        if observation is None:
            observation = self._detector.observe(hand)
        controlled = self._performance_clock()
        metrics = PipelineMetrics(
            self._tracker_config.running_mode.name,
            self._tracker_config.delegate.name,
            self._inference_rate.rate(controlled),
            self._inference_ms,
            capture_seconds * 1000,
            conversion_seconds * 1000,
            (controlled - inferred) * 1000,
            self._overlay_ms,
        )
        return OverlayState(
            hand,
            observation,
            command,
            self._controller.state,
            self._controller.position,
            self._temporal.status,
            fps,
            self._click_feedback.update(command.action),
            self._sink.mode,
            metrics,
        ), controlled

    def _infer(self, rgb: NDArray[np.uint8]) -> tuple[DetectedHand | None, bool]:
        """Return whether control may sample; pending results never advance EMA."""
        if self._tracker_config.running_mode is RunningMode.LIVE_STREAM:
            return self._live_hands(rgb)
        before = self._performance_clock()
        hands = cast(FrameTracker, self._tracker).process(rgb)
        completed = self._performance_clock()
        self._inference_rate.tick(completed)
        self._inference_ms = (completed - before) * 1000
        return select_hand(hands), True

    def _live_hands(self, rgb: NDArray[np.uint8]) -> tuple[DetectedHand | None, bool]:
        """Deliver fresh async hands or complete the existing tracking-loss path."""
        tracker = cast(LiveFrameTracker, self._tracker)
        result = tracker.poll()
        tracker.submit(rgb)
        now = self._performance_clock()
        max_age = self._temporal_config.tracking_grace_seconds
        completion = result.completed_at if result is not None else now
        stalled = (
            self._last_result_at is not None
            and completion - self._last_result_at > max_age
        )
        if self._recovering or stalled:
            # Complete the existing filter's loss-of-tracking path before reuse.
            self._recovering = True
            self._last_hand = None
            self._last_result_at = None
            return None, True
        if result is not None:
            if (
                result.shape != rgb.shape[:2]
                or result.submitted_at < self._accept_after
                or now - result.submitted_at > max_age
            ):
                self._last_hand = None
                self._last_result_at = None
                self._recovering = True
                return None, True
            self._last_hand = select_hand(result.hands)
            self._last_result_at = result.completed_at
            self._inference_ms = result.latency_seconds * 1000
            self._inference_rate.tick(now)
            return self._last_hand, True
        if self._last_result_at is None:
            self._last_hand = None
            return None, True
        return self._last_hand, False

    def handle_key(self, key: int) -> bool:
        """Handle demo keys; R also resets UI count/feedback, D/E preserve them."""
        already_enabled = self._controller.state is ControlState.ENABLED
        quit_requested = handle_key(key, self._controller)
        if (
            self._tracker_config.running_mode is RunningMode.LIVE_STREAM
            and (key & 0xFF not in (ord("e"), ord("E")) or not already_enabled)
            and key & 0xFF
            in (
                ord("e"),
                ord("E"),
                ord("d"),
                ord("D"),
                ord("r"),
                ord("R"),
                ord("q"),
                ord("Q"),
                27,
            )
        ):
            self._accept_after = self._performance_clock()
            self._last_hand = None
            self._last_result_at = None
            self._recovering = False
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


_Resource = TypeVar("_Resource")


@contextmanager
def _preserve_cleanup_error(
    resource: AbstractContextManager[_Resource],
) -> Iterator[_Resource]:
    """Close resources while keeping the original processing/interrupt error.

    A shutdown error on normal exit propagates. With a primary error already
    active, attach shutdown diagnostics as notes and re-raise the original.
    """
    value = resource.__enter__()
    try:
        yield value
    except BaseException as original:
        try:
            resource.__exit__(type(original), original, original.__traceback__)
        except BaseException as cleanup_error:
            original.add_note(f"Resource shutdown also failed: {cleanup_error!r}")
        raise
    else:
        resource.__exit__(None, None, None)


def _close_windows() -> None:
    """Destroy windows; keep a pending primary failure and note shutdown errors."""
    original = sys.exception()
    try:
        cv2.destroyAllWindows()
    except BaseException as cleanup_error:
        if original is None:
            raise
        original.add_note(f"Window shutdown also failed: {cleanup_error!r}")


def _run_loop(pipeline: WebcamPipeline, camera: Camera, window_name: str) -> None:
    """Run sequential frames and local key controls; no pending input queue."""
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    previous, fps = monotonic(), 0.0
    while True:
        read_start = perf_counter()
        bgr = camera.read()
        read_seconds = perf_counter() - read_start
        frame, _ = pipeline.process(bgr, fps=fps, capture_seconds=read_seconds)
        now = monotonic()
        elapsed = now - previous
        fps = 1.0 / elapsed if elapsed > 0 else 0.0
        previous = now
        cv2.imshow(window_name, frame)
        if pipeline.handle_key(cv2.waitKey(1)):
            break
        if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
            break


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
            _preserve_cleanup_error(
                Camera(
                    config.camera_index,
                    width=config.frame_width,
                    height=config.frame_height,
                )
            ) as camera,
            _preserve_cleanup_error(
                HandTracker(model, config=config.tracker)
            ) as tracker,
        ):
            pipeline = WebcamPipeline(
                tracker,
                cursor_config,
                sink=sink,
                tracker_config=config.tracker,
            )
            _run_loop(pipeline, camera, window_name)
    finally:
        if pipeline is not None:
            pipeline.controller.disable()
        _close_windows()

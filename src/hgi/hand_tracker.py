"""RGB-to-hand adapter; modes, delegates and native callbacks stay isolated."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from threading import Lock
from time import monotonic, perf_counter
from types import TracebackType
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from hgi.hand_landmarks import DetectedHand, NormalizedLandmark
from hgi.tracker_config import HandTrackerConfig, InferenceDelegate, RunningMode

if TYPE_CHECKING:
    from mediapipe import Image
    from mediapipe.tasks.python.vision.hand_landmarker import HandLandmarkerResult

LIVE_RESULT_TIMEOUT_SECONDS = 5.0


class HandTrackerError(RuntimeError):
    """MediaPipe import, initialization, processing or shutdown failure."""


@dataclass(frozen=True, slots=True)
class LiveResult:
    """One immutable HGI sample; timestamps and latency exclude cursor effects."""

    hands: tuple[DetectedHand, ...]
    timestamp_ms: int
    shape: tuple[int, int]
    submitted_at: float
    completed_at: float

    @property
    def latency_seconds(self) -> float:
        """Submit-to-callback latency, not native kernel execution duration."""
        return self.completed_at - self.submitted_at


def _convert_result(result: HandLandmarkerResult) -> tuple[DetectedHand, ...]:
    hands = []
    for index, raw_points in enumerate(result.hand_landmarks):
        points = tuple(NormalizedLandmark(p.x, p.y, p.z) for p in raw_points)
        categories = result.handedness[index] if index < len(result.handedness) else []
        category = max(
            categories,
            key=lambda item: item.score if item.score is not None else -1,
            default=None,
        )
        hands.append(
            DetectedHand(
                landmarks=points,
                handedness=category.category_name if category else None,
                handedness_score=category.score if category else None,
            )
        )
    return tuple(hands)


class HandTracker:
    """Reuse an explicitly configured detector with a local model and HGI types.

    Call process with RGB uint8 H×W×3 arrays. No camera, color conversion,
    gestures or network downloads are owned here. VIDEO timestamps use integer
    milliseconds; process(frame) supplies them from an injectable monotonic clock.
    LIVE_STREAM uses submit/poll and a bounded mailbox. Call public methods on
    one owner thread; only the native result callback shares protected state.
    """

    def __init__(
        self,
        model_path: str | Path,
        *,
        config: HandTrackerConfig | None = None,
        clock: Callable[[], float] = monotonic,
        performance_clock: Callable[[], float] = perf_counter,
        num_hands: int | None = None,
        min_hand_detection_confidence: float | None = None,
        min_hand_presence_confidence: float | None = None,
    ) -> None:
        legacy = (
            num_hands,
            min_hand_detection_confidence,
            min_hand_presence_confidence,
        )
        if config is not None and any(v is not None for v in legacy):
            raise ValueError("Use config or legacy options, not both")
        self._config = (
            config
            if config is not None
            else HandTrackerConfig(
                num_hands=1 if num_hands is None else num_hands,
                min_hand_detection_confidence=0.5
                if min_hand_detection_confidence is None
                else min_hand_detection_confidence,
                min_hand_presence_confidence=0.5
                if min_hand_presence_confidence is None
                else min_hand_presence_confidence,
            )
        )
        if not isinstance(self.config, HandTrackerConfig):
            raise ValueError("config must be a HandTrackerConfig")
        self._clock = clock
        self._performance_clock = performance_clock
        self._last_timestamp: int | None = None
        self._last_clock: float | None = None
        self._lock = Lock()
        self._pending: tuple[int, tuple[int, int], float] | None = None
        self._latest: LiveResult | None = None
        self._callback_error: BaseException | None = None
        self._closed = False
        self._stopping = False
        path = Path(model_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Hand Landmarker model file not found: {path}")
        try:
            import mediapipe as mp
        except ImportError as error:
            raise HandTrackerError(
                "MediaPipe is unavailable; install the HGI vision extra "
                "and check its dependencies"
            ) from error
        self._mp = mp
        self._landmarker = self._create_landmarker(path)

    @property
    def config(self) -> HandTrackerConfig:
        """Read-only options used at initialization, never a live mode switch."""
        return self._config

    def _create_landmarker(self, path: Path):
        mp = self._mp
        try:
            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(
                    model_asset_path=str(path),
                    delegate=getattr(
                        mp.tasks.BaseOptions.Delegate, self.config.delegate.name
                    ),
                ),
                running_mode=getattr(
                    mp.tasks.vision.RunningMode, self.config.running_mode.name
                ),
                num_hands=self.config.num_hands,
                min_hand_detection_confidence=self.config.min_hand_detection_confidence,
                min_hand_presence_confidence=self.config.min_hand_presence_confidence,
                min_tracking_confidence=self.config.min_tracking_confidence,
            )
            if self.config.running_mode is RunningMode.LIVE_STREAM:
                options.result_callback = self._on_result
            return mp.tasks.vision.HandLandmarker.create_from_options(options)
        except (AttributeError, ValueError, RuntimeError) as error:
            hint = (
                "; GPU unavailable: try --delegate cpu; see docs/PERFORMANCE.md"
                if self.config.delegate is InferenceDelegate.GPU
                else ""
            )
            raise HandTrackerError(
                "Could not initialize MediaPipe HandLandmarker "
                f"({self.config.running_mode.name}/{self.config.delegate.name})"
                f"{hint}: {error}"
            ) from error

    def _image(self, frame: NDArray[np.uint8]) -> Image:
        """Validate RGB at the boundary; external image never leaves the tracker."""
        if not isinstance(frame, np.ndarray):
            raise TypeError("RGB frame must be a numpy.ndarray")
        if frame.dtype != np.uint8:
            raise TypeError("RGB frame dtype must be uint8")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("RGB frame must have shape H × W × 3")
        if frame.shape[0] == 0 or frame.shape[1] == 0:
            raise ValueError("RGB frame height and width must be positive")
        try:
            return self._mp.Image(
                image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame)
            )
        except (ValueError, RuntimeError) as error:
            raise HandTrackerError(
                "Could not process RGB frame with MediaPipe"
            ) from error

    def _timestamp(self, timestamp_ms: int | None) -> int:
        """Require increasing signed-int64 ms; resolve same auto-clock tick by +1."""
        if timestamp_ms is None:
            now = self._clock()
            if (
                isinstance(now, bool)
                or not isinstance(now, (int, float))
                or not isfinite(now)
                or now < 0
                or now >= 2**63 / 1000
                or (self._last_clock is not None and now < self._last_clock)
            ):
                raise ValueError(
                    "Clock must return nonnegative finite monotonic seconds"
                )
            self._last_clock = now
            timestamp_ms = max(
                int(now * 1000),
                0 if self._last_timestamp is None else self._last_timestamp + 1,
            )
        if (
            isinstance(timestamp_ms, bool)
            or not isinstance(timestamp_ms, int)
            or not 0 <= timestamp_ms < 2**63
            or (
                self._last_timestamp is not None
                and timestamp_ms <= self._last_timestamp
            )
        ):
            raise ValueError(
                "timestamp_ms must be a strictly increasing nonnegative int64"
            )
        self._last_timestamp = timestamp_ms
        return timestamp_ms

    def process(
        self, frame: NDArray[np.uint8], *, timestamp_ms: int | None = None
    ) -> tuple[DetectedHand, ...]:
        """Return internal hands, or an empty tuple when no hand is detected.

        Strided inputs are made contiguous without changing RGB order. Invalid
        input/result raises TypeError/ValueError; MediaPipe failures preserve
        their original cause in HandTrackerError. The input is not modified.
        """
        self._ensure_open()
        mode = self.config.running_mode
        if mode is RunningMode.LIVE_STREAM:
            raise ValueError("LIVE_STREAM uses submit(frame) and poll(), not process()")
        image = self._image(frame)
        if mode is RunningMode.IMAGE and timestamp_ms is not None:
            raise ValueError("IMAGE does not accept a timestamp")
        timestamp = (
            self._timestamp(timestamp_ms) if mode is not RunningMode.IMAGE else None
        )
        try:
            result = (
                self._landmarker.detect(image)
                if mode is RunningMode.IMAGE
                else self._landmarker.detect_for_video(image, timestamp)
            )
        except (ValueError, RuntimeError) as error:
            raise HandTrackerError(
                "Could not process RGB frame with MediaPipe"
            ) from error
        return _convert_result(result)

    def _ensure_live(self) -> None:
        self._ensure_open()
        if self.config.running_mode is not RunningMode.LIVE_STREAM:
            raise ValueError("submit/poll require LIVE_STREAM")

    def _check_live_error(self) -> None:
        """Called under the lock; detect native errors that never reach callback."""
        if (
            self._pending is not None
            and self._performance_clock() - self._pending[2]
            >= LIVE_RESULT_TIMEOUT_SECONDS
        ):
            self._callback_error = HandTrackerError(
                "LIVE_STREAM callback timed out after 5 seconds; "
                "check MediaPipe diagnostics or use --running-mode video"
            )
            self._latest = None
            self._pending = None
        if self._callback_error is not None:
            raise self._callback_error

    def submit(
        self, frame: NDArray[np.uint8], *, timestamp_ms: int | None = None
    ) -> bool:
        """Submit only when idle; busy inputs are discarded, never queued.

        Call on the owner thread. Neither this method nor the callback creates
        cursor commands. A callback error permanently stops new submissions.
        """
        self._ensure_live()
        with self._lock:
            self._check_live_error()
            if self._pending is not None:
                return False
        image = self._image(frame)
        timestamp = self._timestamp(timestamp_ms)
        with self._lock:
            self._pending = (timestamp, frame.shape[:2], self._performance_clock())
        try:
            self._landmarker.detect_async(image, timestamp)
        except (ValueError, RuntimeError) as error:
            failure = HandTrackerError(
                f"Could not process RGB frame asynchronously: {error}"
            )
            with self._lock:
                self._callback_error = failure
                self._pending = None
            raise failure from error
        return True

    def _on_result(
        self, result: HandLandmarkerResult, _image: object, timestamp_ms: int
    ) -> None:
        """Adapt only; transfer callback errors to the owner instead of hiding them."""
        try:
            hands = _convert_result(result)
            completed = self._performance_clock()
            with self._lock:
                if self._stopping or self._closed or self._callback_error is not None:
                    return
                if self._pending is None or self._pending[0] != timestamp_ms:
                    return  # Unexpected/late results cannot replace a newer sample.
                _, shape, submitted = self._pending
                self._latest = LiveResult(
                    hands, timestamp_ms, shape, submitted, completed
                )
                self._pending = None
        except BaseException as error:
            with self._lock:
                if (
                    not self._stopping
                    and not self._closed
                    and self._callback_error is None
                ):
                    self._callback_error = error
                    self._latest = None
                    self._pending = None

    def poll(self) -> LiveResult | None:
        """Consume the latest result once; None means pending, () hands means absent."""
        self._ensure_live()
        with self._lock:
            self._check_live_error()
            result, self._latest = self._latest, None
            return result

    def close(self) -> None:
        """Close once after success; failed shutdown remains retryable."""
        if not self._closed:
            with self._lock:
                self._stopping = True
            try:
                # Native close joins callbacks: never hold our lock across it.
                self._landmarker.close()
            except RuntimeError as error:
                raise HandTrackerError(
                    "Could not close MediaPipe HandLandmarker"
                ) from error
            with self._lock:
                self._closed = True
                self._latest = None
                self._pending = None

    def _ensure_open(self) -> None:
        if self._closed or self._stopping:
            raise RuntimeError("HandTracker is closed")

    def __enter__(self) -> HandTracker:
        """Enter an initialized, open tracker context."""
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release resources on normal return or exception; never suppress errors."""
        self.close()

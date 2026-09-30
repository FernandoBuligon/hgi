"""Synchronous RGB-to-hand adapter; MediaPipe objects stay inside this module."""

from __future__ import annotations

from math import isfinite
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from hgi.hand_landmarks import DetectedHand, NormalizedLandmark

if TYPE_CHECKING:
    from mediapipe.tasks.python.vision.hand_landmarker import HandLandmarkerResult


class HandTrackerError(RuntimeError):
    """MediaPipe import, initialization, processing or shutdown failure."""


def _validate_options(
    num_hands: int, detection_confidence: float, presence_confidence: float
) -> None:
    if isinstance(num_hands, bool) or not isinstance(num_hands, int) or num_hands < 1:
        raise ValueError("num_hands must be a positive integer")
    for confidence in (detection_confidence, presence_confidence):
        if (
            isinstance(confidence, bool)
            or not isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("Confidence thresholds must be finite and in [0, 1]")


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
    """Reuse a CPU HandLandmarker in IMAGE mode with an explicit local model.

    Call process with RGB uint8 H×W×3 arrays. No camera, color conversion,
    timestamps, callbacks, gestures or network download are owned here.
    Use a context manager or close explicitly. Instances are not thread-safe.
    """

    def __init__(
        self,
        model_path: str | Path,
        *,
        num_hands: int = 1,
        min_hand_detection_confidence: float = 0.5,
        min_hand_presence_confidence: float = 0.5,
    ) -> None:
        _validate_options(
            num_hands, min_hand_detection_confidence, min_hand_presence_confidence
        )
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
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(path), delegate=mp.tasks.BaseOptions.Delegate.CPU
            ),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_hands=num_hands,
            min_hand_detection_confidence=min_hand_detection_confidence,
            min_hand_presence_confidence=min_hand_presence_confidence,
        )
        try:
            self._landmarker = mp.tasks.vision.HandLandmarker.create_from_options(
                options
            )
        except (ValueError, RuntimeError) as error:
            raise HandTrackerError(
                "Could not initialize MediaPipe HandLandmarker"
            ) from error
        self._closed = False

    def process(self, frame: NDArray[np.uint8]) -> tuple[DetectedHand, ...]:
        """Return internal hands, or an empty tuple when no hand is detected.

        Strided inputs are made contiguous without changing RGB order. Invalid
        input/result raises TypeError/ValueError; MediaPipe failures preserve
        their original cause in HandTrackerError. The input is not modified.
        """
        self._ensure_open()
        if not isinstance(frame, np.ndarray):
            raise TypeError("RGB frame must be a numpy.ndarray")
        if frame.dtype != np.uint8:
            raise TypeError("RGB frame dtype must be uint8")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("RGB frame must have shape H × W × 3")
        if frame.shape[0] == 0 or frame.shape[1] == 0:
            raise ValueError("RGB frame height and width must be positive")
        try:
            image = self._mp.Image(
                image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame)
            )
            result = self._landmarker.detect(image)
        except (ValueError, RuntimeError) as error:
            raise HandTrackerError(
                "Could not process RGB frame with MediaPipe"
            ) from error
        return _convert_result(result)

    def close(self) -> None:
        """Close once after success; failed shutdown remains retryable."""
        if not self._closed:
            try:
                self._landmarker.close()
            except RuntimeError as error:
                raise HandTrackerError(
                    "Could not close MediaPipe HandLandmarker"
                ) from error
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
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

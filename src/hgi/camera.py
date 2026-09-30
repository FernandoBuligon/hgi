"""Small OpenCV capture boundary; frames stay in memory and in BGR order."""

from __future__ import annotations

from types import TracebackType

import cv2
import numpy as np
from numpy.typing import NDArray


class CameraError(RuntimeError):
    """Camera unavailable, invalid frame or native capture failure."""


def validate_bgr_frame(frame: NDArray[np.uint8]) -> None:
    """Require a nonempty BGR uint8 H×W×3 array; color order is caller-owned."""
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8:
        raise TypeError("BGR frame must be a uint8 numpy array")
    if frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 1:
        raise ValueError("BGR frame must have nonempty shape H × W × 3")


class Camera:
    """Open one device, request dimensions and return actual frames unchanged.

    Requested resolution may be ignored by the driver; use frame.shape. A read
    failure raises immediately, never returns a fake frame or silently retries.
    Use with Camera(...) to release even when the caller raises.
    """

    def __init__(self, index: int = 0, *, width: int = 640, height: int = 480):
        for name, value, minimum in (
            ("index", index, 0),
            ("width", width, 1),
            ("height", height, 1),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"Camera {name} must be an integer >= {minimum}")
        self._closed = False
        try:
            self._capture = cv2.VideoCapture(index)
        except cv2.error as error:
            raise CameraError(f"Could not open camera {index}") from error
        try:
            if not self._capture.isOpened():
                raise CameraError(
                    f"Could not open camera {index}; check device and camera permission"
                )
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        except (cv2.error, CameraError) as error:
            self.close()
            raise CameraError(
                f"Could not configure/open camera {index}: {error}"
            ) from error

    def read(self) -> NDArray[np.uint8]:
        """Read a validated BGR frame, preserving actual dimensions and channels."""
        if self._closed:
            raise CameraError("Camera is closed")
        try:
            ok, frame = self._capture.read()
            if not ok:
                raise CameraError("Could not read camera frame; capture stopped")
            validate_bgr_frame(frame)
        except (cv2.error, TypeError, ValueError) as error:
            raise CameraError(f"Invalid/unavailable camera frame: {error}") from error
        return frame

    def close(self) -> None:
        """Release once after successful shutdown; never suppress native errors."""
        if not self._closed:
            try:
                self._capture.release()
            except cv2.error as error:
                raise CameraError("Could not release camera") from error
            self._closed = True

    def __enter__(self) -> Camera:
        """Enter an open capture; a closed device cannot be reused."""
        if self._closed:
            raise CameraError("Camera is closed")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release on success or exception without suppressing failures."""
        self.close()

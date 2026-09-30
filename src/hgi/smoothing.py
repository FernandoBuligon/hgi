"""Coordinate smoothing with no clock, FPS input or hardware dependency."""

from math import isfinite

from hgi.geometry import Point2D


def _blend_coordinate(previous: float, current: float, alpha: float) -> float:
    if previous == current:
        return current
    return (1 - alpha) * previous + alpha * current


class ExponentialSmoother:
    """An EMA of 2D points with a fixed per-update factor in 0 < alpha <= 1.

    A smaller alpha follows input more slowly. The first point and the first
    point after reset pass through unchanged. Use consistent coordinate units.
    """

    def __init__(self, alpha: float) -> None:
        if isinstance(alpha, bool) or not isfinite(alpha) or not 0 < alpha <= 1:
            raise ValueError("Alpha must be finite and satisfy 0 < alpha <= 1")
        self._alpha = alpha
        self._previous: Point2D | None = None

    @property
    def alpha(self) -> float:
        """Return the factor validated at construction; it cannot be reassigned."""
        return self._alpha

    def update(self, point: Point2D) -> Point2D:
        """Return the smoothed point, retaining only the previous output.

        Weighted addition equals previous + alpha * (current - previous),
        while avoiding overflow in the subtraction of opposing large values.
        An unchanged axis passes through exactly, avoiding rounding drift.
        """
        if self._previous is None:
            self._previous = point
        else:
            self._previous = Point2D(
                _blend_coordinate(self._previous.x, point.x, self._alpha),
                _blend_coordinate(self._previous.y, point.y, self._alpha),
            )
        return self._previous

    def reset(self) -> None:
        """Discard previous output so the next point initializes the EMA again."""
        self._previous = None

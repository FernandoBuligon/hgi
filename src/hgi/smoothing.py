"""Coordinate smoothing with no clock, FPS input or hardware dependency."""

from math import isfinite

from hgi.geometry import Point2D


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
        """
        if self._previous is None:
            self._previous = point
        else:
            self._previous = Point2D(
                (1 - self._alpha) * self._previous.x + self._alpha * point.x,
                (1 - self._alpha) * self._previous.y + self._alpha * point.y,
            )
        return self._previous

    def reset(self) -> None:
        """Discard previous output so the next point initializes the EMA again."""
        self._previous = None

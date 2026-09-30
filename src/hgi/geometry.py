"""Pure 2D geometry; callers choose and keep coordinate units consistent."""

from dataclasses import dataclass
from math import hypot, isfinite


def _require_finite(value: float) -> float:
    if not isfinite(value):
        raise ValueError("Values must be finite")
    return value


@dataclass(frozen=True, slots=True)
class Point2D:
    """A finite point in normalized or pixel coordinates, including negatives.

    The type does not attach a unit or device to a point. Name variables for
    their coordinate space and convert explicitly before combining points.
    """

    x: float
    y: float

    def __post_init__(self) -> None:
        _require_finite(self.x)
        _require_finite(self.y)


def distance(first: Point2D, second: Point2D) -> float:
    """Return Euclidean distance in the points' shared units.

    Reject results beyond finite float range rather than propagating infinity.
    """
    return _require_finite(hypot(second.x - first.x, second.y - first.y))


def normalized_distance(
    first: Point2D, second: Point2D, reference_distance: float
) -> float:
    """Divide distance by a positive, finite reference in the same units."""
    _require_finite(reference_distance)
    if reference_distance <= 0:
        raise ValueError("Reference distance must be positive")
    return _require_finite(distance(first, second) / reference_distance)


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Limit a finite value to an inclusive interval; equal bounds are valid."""
    _require_finite(value)
    _require_finite(minimum)
    _require_finite(maximum)
    if minimum > maximum:
        raise ValueError("Minimum must not exceed maximum")
    return min(max(value, minimum), maximum)

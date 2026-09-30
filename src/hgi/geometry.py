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


@dataclass(frozen=True, slots=True)
class Region2D:
    """Inclusive camera bounds in a shared coordinate space, with positive spans.

    Use normalized bounds or pixel bounds consistently with the input point.
    Margins are represented directly by choosing a smaller region.
    """

    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        for bound in (self.left, self.top, self.right, self.bottom):
            _require_finite(bound)
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("Region must have positive horizontal and vertical spans")
        _require_finite(self.right - self.left)
        _require_finite(self.bottom - self.top)


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


def _validate_dimensions(width: int, height: int) -> None:
    for dimension in (width, height):
        if (
            isinstance(dimension, bool)
            or not isinstance(dimension, int)
            or dimension <= 0
        ):
            raise ValueError("Dimensions must be positive integers")


def normalized_to_pixels(point: Point2D, width: int, height: int) -> Point2D:
    """Clip normalized coordinates and map 0..1 to 0..dimension-1.

    Keep subpixel floats: no rounding occurs here. A one-pixel axis is always 0.
    """
    _validate_dimensions(width, height)
    return Point2D(
        clamp(point.x, 0.0, 1.0) * (width - 1),
        clamp(point.y, 0.0, 1.0) * (height - 1),
    )


def pixels_to_normalized(point: Point2D, width: int, height: int) -> Point2D:
    """Clip pixels and invert normalized_to_pixels; one-pixel axes return 0.

    The inverse is unique only for axes with more than one pixel. Out-of-bounds
    points are clipped, so their original values cannot be recovered.
    """
    _validate_dimensions(width, height)
    return Point2D(
        0.0 if width == 1 else clamp(point.x, 0.0, width - 1) / (width - 1),
        0.0 if height == 1 else clamp(point.y, 0.0, height - 1) / (height - 1),
    )


def mirror_horizontal(point: Point2D) -> Point2D:
    """Reflect X as 1-X in normalized space, preserving Y without clipping."""
    return Point2D(1.0 - point.x, point.y)


def map_camera_to_screen(
    point: Point2D,
    camera_region: Region2D,
    screen_width: int,
    screen_height: int,
    *,
    mirror_x: bool = False,
) -> Point2D:
    """Map a useful camera region to supplied screen dimensions, with clipping.

    Mirror relative to the useful region after normalization, never relative
    to an assumed full frame. All inputs are numbers; no devices are queried.
    """
    x = clamp(point.x, camera_region.left, camera_region.right)
    y = clamp(point.y, camera_region.top, camera_region.bottom)
    normalized = Point2D(
        (x - camera_region.left) / (camera_region.right - camera_region.left),
        (y - camera_region.top) / (camera_region.bottom - camera_region.top),
    )
    if mirror_x:
        normalized = mirror_horizontal(normalized)
    return normalized_to_pixels(normalized, screen_width, screen_height)

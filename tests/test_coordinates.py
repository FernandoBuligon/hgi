"""Conversions and camera-to-screen mapping use supplied numbers only."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from hgi.geometry import (
    Point2D,
    Region2D,
    map_camera_to_screen,
    mirror_horizontal,
    normalized_to_pixels,
    pixels_to_normalized,
)


def test_region_preserves_bounds_and_is_immutable() -> None:
    region = Region2D(-10, -20, 10, 20)
    assert (region.left, region.top, region.right, region.bottom) == (-10, -20, 10, 20)
    with pytest.raises(FrozenInstanceError):
        region.left = 0  # type: ignore[misc]


@pytest.mark.parametrize(
    "bounds", [(1, 0, 1, 2), (2, 0, 1, 2), (0, 2, 1, 2), (0, 3, 1, 2)]
)
def test_region_rejects_empty_or_reversed_axes(
    bounds: tuple[float, float, float, float],
) -> None:
    with pytest.raises(ValueError):
        Region2D(*bounds)


@pytest.mark.parametrize("value", [nan, inf, -inf])
@pytest.mark.parametrize("position", [0, 1, 2, 3])
def test_region_rejects_nonfinite_bounds(value: float, position: int) -> None:
    bounds = [0.0, 0.0, 1.0, 1.0]
    bounds[position] = value
    with pytest.raises(ValueError, match="finite"):
        Region2D(*bounds)


@pytest.mark.parametrize("bounds", [(-1e308, 0, 1e308, 1), (0, -1e308, 1, 1e308)])
def test_region_rejects_unrepresentable_span(
    bounds: tuple[float, float, float, float],
) -> None:
    with pytest.raises(ValueError, match="finite"):
        Region2D(*bounds)


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        (Point2D(0, 0), Point2D(0, 0)),
        (Point2D(1, 1), Point2D(1919, 1079)),
        (Point2D(0.5, 0.5), Point2D(959.5, 539.5)),
        (Point2D(-0.1, 1.1), Point2D(0, 1079)),
        (Point2D(1.1, -0.1), Point2D(1919, 0)),
    ],
)
def test_normalized_to_pixels(point: Point2D, expected: Point2D) -> None:
    assert normalized_to_pixels(point, 1920, 1080) == expected


@pytest.mark.parametrize("size", [(10**16, 100), (100, 10**16)])
def test_float_rounding_cannot_exceed_last_pixel(size: tuple[int, int]) -> None:
    result = normalized_to_pixels(Point2D(1.0, 1.0), *size)
    assert 0 <= result.x <= size[0] - 1
    assert 0 <= result.y <= size[1] - 1


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        (Point2D(0, 0), Point2D(0, 0)),
        (Point2D(1919, 1079), Point2D(1, 1)),
        (Point2D(959.5, 539.5), Point2D(0.5, 0.5)),
        (Point2D(-10, 2000), Point2D(0, 1)),
        (Point2D(2000, -10), Point2D(1, 0)),
    ],
)
def test_pixels_to_normalized(point: Point2D, expected: Point2D) -> None:
    assert pixels_to_normalized(point, 1920, 1080) == expected


@pytest.mark.parametrize("size", [(640, 480), (1920, 1080), (5, 9)])
def test_conversion_round_trip(size: tuple[int, int]) -> None:
    point = Point2D(0.2, 0.7)
    restored = pixels_to_normalized(normalized_to_pixels(point, *size), *size)
    assert (restored.x, restored.y) == pytest.approx((point.x, point.y))


@pytest.mark.parametrize(
    ("size", "pixels", "normalized"),
    [
        ((1, 1), Point2D(0, 0), Point2D(0, 0)),
        ((1, 5), Point2D(0, 3), Point2D(0, 0.75)),
        ((5, 1), Point2D(2, 0), Point2D(0.5, 0)),
    ],
)
def test_single_pixel_dimension_has_canonical_zero(
    size: tuple[int, int], pixels: Point2D, normalized: Point2D
) -> None:
    assert normalized_to_pixels(Point2D(0.5, 0.75), *size) == pixels
    assert pixels_to_normalized(pixels, *size) == normalized


@pytest.mark.parametrize("function", [normalized_to_pixels, pixels_to_normalized])
@pytest.mark.parametrize("dimension", [0, -1, True, 1.5, "1920", None])
@pytest.mark.parametrize("axis", ["width", "height"])
def test_conversions_reject_invalid_dimensions(
    function: Callable[[Point2D, int, int], Point2D], dimension: object, axis: str
) -> None:
    dimensions = {"width": 1920, "height": 1080}
    dimensions[axis] = dimension  # type: ignore[assignment]
    with pytest.raises(ValueError, match="positive integers"):
        function(Point2D(0.5, 0.5), **dimensions)


@pytest.mark.parametrize(
    ("x", "expected"), [(0, 1), (0.25, 0.75), (0.5, 0.5), (1, 0), (-0.25, 1.25)]
)
def test_mirror_horizontal_reflects_x_and_preserves_y(
    x: float, expected: float
) -> None:
    assert mirror_horizontal(Point2D(x, 0.7)) == Point2D(expected, 0.7)


def test_mirror_horizontal_is_its_own_inverse() -> None:
    point = Point2D(0.2, 0.7)
    restored = mirror_horizontal(mirror_horizontal(point))
    assert (restored.x, restored.y) == pytest.approx((point.x, point.y))


@pytest.mark.parametrize(
    ("camera_point", "expected"),
    [
        (Point2D(10, 20), Point2D(0, 0)),
        (Point2D(110, 220), Point2D(100, 200)),
        (Point2D(60, 120), Point2D(50, 100)),
        (Point2D(-100, 120), Point2D(0, 100)),
        (Point2D(1000, 120), Point2D(100, 100)),
        (Point2D(60, -100), Point2D(50, 0)),
        (Point2D(60, 1000), Point2D(50, 200)),
    ],
)
def test_map_camera_region_to_screen(camera_point: Point2D, expected: Point2D) -> None:
    assert (
        map_camera_to_screen(camera_point, Region2D(10, 20, 110, 220), 101, 201)
        == expected
    )


@pytest.mark.parametrize(("mirror_x", "expected_x"), [(False, 250), (True, 750)])
def test_mapping_mirrors_relative_to_useful_region(
    mirror_x: bool, expected_x: float
) -> None:
    point = map_camera_to_screen(
        Point2D(200, 150), Region2D(100, 50, 500, 250), 1001, 501, mirror_x=mirror_x
    )
    assert point == Point2D(expected_x, 250)


def test_mapping_accepts_normalized_camera_region() -> None:
    point = map_camera_to_screen(
        Point2D(0.4, 0.5), Region2D(0.2, 0.2, 0.8, 0.8), 1920, 1080
    )
    assert (point.x, point.y) == pytest.approx((1919 / 3, 1079 / 2))


@pytest.mark.parametrize("mirror_x", [False, True])
def test_mapping_always_stays_inside_supplied_screen(mirror_x: bool) -> None:
    region = Region2D(10, 20, 110, 220)
    for x in [-1e308, 10, 60, 110, 1e308]:
        for y in [-1e308, 20, 120, 220, 1e308]:
            result = map_camera_to_screen(
                Point2D(x, y), region, 1920, 1080, mirror_x=mirror_x
            )
            assert 0 <= result.x <= 1919
            assert 0 <= result.y <= 1079


def test_mapping_supports_single_pixel_screen() -> None:
    assert map_camera_to_screen(
        Point2D(0.5, 0.5), Region2D(0, 0, 1, 1), 1, 1
    ) == Point2D(0, 0)


@pytest.mark.parametrize("size", [(0, 1080), (1920, -1)])
def test_mapping_rejects_invalid_screen_dimensions(size: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        map_camera_to_screen(Point2D(0.5, 0.5), Region2D(0, 0, 1, 1), *size)

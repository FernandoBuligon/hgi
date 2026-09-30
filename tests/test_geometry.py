"""Deterministic geometry checks in explicit, caller-supplied coordinate spaces."""

from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from hgi.geometry import Point2D, clamp, distance, normalized_distance


def test_point_preserves_coordinates_and_is_immutable() -> None:
    point = Point2D(-2.5, 3.0)
    assert (point.x, point.y) == (-2.5, 3.0)
    with pytest.raises(FrozenInstanceError):
        point.x = 4.0  # type: ignore[misc]


@pytest.mark.parametrize("value", [nan, inf, -inf])
@pytest.mark.parametrize("axis", ["x", "y"])
def test_point_rejects_nonfinite_coordinates(value: float, axis: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        Point2D(**{axis: value, "y" if axis == "x" else "x": 0.0})


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (Point2D(2, 3), Point2D(2, 3), 0),
        (Point2D(1, 2), Point2D(6, 2), 5),
        (Point2D(1, 2), Point2D(1, 8), 6),
        (Point2D(0, 0), Point2D(3, 4), 5),
        (Point2D(-3, -4), Point2D(0, 0), 5),
    ],
)
def test_distance(first: Point2D, second: Point2D, expected: float) -> None:
    assert distance(first, second) == pytest.approx(expected)
    assert distance(second, first) == pytest.approx(expected)


def test_distance_rejects_unrepresentable_result() -> None:
    with pytest.raises(ValueError, match="finite"):
        distance(Point2D(-1e308, 0), Point2D(1e308, 0))


def test_normalized_distance_is_invariant_under_uniform_scaling() -> None:
    ratio = normalized_distance(Point2D(0, 0), Point2D(3, 4), 10)
    scaled = normalized_distance(Point2D(0, 0), Point2D(30, 40), 100)
    assert ratio == scaled == 0.5


@pytest.mark.parametrize("reference", [0, -1, nan, inf, -inf])
def test_normalized_distance_rejects_invalid_reference(reference: float) -> None:
    with pytest.raises(ValueError):
        normalized_distance(Point2D(0, 0), Point2D(1, 1), reference)


def test_normalized_distance_rejects_overflow() -> None:
    with pytest.raises(ValueError, match="finite"):
        normalized_distance(Point2D(0, 0), Point2D(1e308, 0), 1e-308)


@pytest.mark.parametrize(
    ("value", "expected"), [(-1, 0), (0, 0), (0.4, 0.4), (1, 1), (2, 1)]
)
def test_clamp(value: float, expected: float) -> None:
    assert clamp(value, 0, 1) == expected


def test_clamp_supports_negative_and_collapsed_intervals() -> None:
    assert clamp(-3, -5, -1) == -3
    assert clamp(10, 2, 2) == 2


def test_clamp_rejects_reversed_interval() -> None:
    with pytest.raises(ValueError):
        clamp(0, 2, 1)


@pytest.mark.parametrize("value", [nan, inf, -inf])
@pytest.mark.parametrize("position", [0, 1, 2])
def test_clamp_rejects_nonfinite_arguments(value: float, position: int) -> None:
    arguments = [0.5, 0.0, 1.0]
    arguments[position] = value
    with pytest.raises(ValueError, match="finite"):
        clamp(*arguments)

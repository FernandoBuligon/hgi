"""EMA behavior is deterministic, per update and independent of devices/time."""

from math import inf, nan

import pytest

from hgi.geometry import Point2D
from hgi.smoothing import ExponentialSmoother


def test_first_point_initializes_without_bias() -> None:
    smoother = ExponentialSmoother(alpha=0.2)
    assert smoother.update(Point2D(20, -10)) == Point2D(20, -10)


def test_predictable_sequence_smooths_both_axes() -> None:
    smoother = ExponentialSmoother(alpha=0.5)
    smoother.update(Point2D(0, 0))
    assert smoother.update(Point2D(10, 20)) == Point2D(5, 10)
    assert smoother.update(Point2D(10, 20)) == Point2D(7.5, 15)
    assert smoother.update(Point2D(0, 0)) == Point2D(3.75, 7.5)


def test_low_alpha_moves_less_than_high_alpha() -> None:
    slow = ExponentialSmoother(alpha=0.1)
    fast = ExponentialSmoother(alpha=0.9)
    for smoother in (slow, fast):
        smoother.update(Point2D(0, 0))
    assert slow.update(Point2D(100, -100)) == Point2D(10, -10)
    assert fast.update(Point2D(100, -100)) == Point2D(90, -90)


def test_alpha_one_follows_input_exactly() -> None:
    smoother = ExponentialSmoother(alpha=1)
    smoother.update(Point2D(1e308, 2))
    assert smoother.update(Point2D(-1e308, -20)) == Point2D(-1e308, -20)


def test_weighted_average_avoids_overflow_for_opposing_large_points() -> None:
    smoother = ExponentialSmoother(alpha=0.5)
    smoother.update(Point2D(1e308, -1e308))
    assert smoother.update(Point2D(-1e308, 1e308)) == Point2D(0, 0)


@pytest.mark.parametrize("alpha", [0, -0.1, 1.01, nan, inf, -inf, True, False])
def test_invalid_alpha_is_rejected(alpha: float) -> None:
    with pytest.raises(ValueError):
        ExponentialSmoother(alpha=alpha)


def test_alpha_is_read_only_after_validation() -> None:
    smoother = ExponentialSmoother(alpha=0.5)
    assert smoother.alpha == 0.5
    with pytest.raises(AttributeError):
        smoother.alpha = 0  # type: ignore[misc]


def test_reset_reinitializes_with_next_point() -> None:
    smoother = ExponentialSmoother(alpha=0.2)
    smoother.reset()
    smoother.update(Point2D(10, 20))
    smoother.update(Point2D(50, 100))
    smoother.reset()
    assert smoother.update(Point2D(-20, -30)) == Point2D(-20, -30)


def test_smoothers_do_not_share_state() -> None:
    first = ExponentialSmoother(alpha=0.5)
    second = ExponentialSmoother(alpha=0.5)
    first.update(Point2D(0, 0))
    assert second.update(Point2D(100, 100)) == Point2D(100, 100)
    assert first.update(Point2D(10, 20)) == Point2D(5, 10)


@pytest.mark.parametrize("alpha", [1e-12, 0.1, 0.5, 0.9, 1])
def test_smoothing_stays_between_previous_output_and_input(alpha: float) -> None:
    smoother = ExponentialSmoother(alpha=alpha)
    previous = smoother.update(Point2D(10, -10))
    for point in (Point2D(100, 100), Point2D(-50, -40), Point2D(0, 0)):
        result = smoother.update(point)
        assert min(previous.x, point.x) <= result.x <= max(previous.x, point.x)
        assert min(previous.y, point.y) <= result.y <= max(previous.y, point.y)
        previous = result

"""Bounded timing observations never advance gesture clocks."""

import pytest

from hgi.performance import RateMeter


def test_rate_counts_events_in_one_second_window():
    meter = RateMeter()
    assert meter.rate(10) == 0
    meter.tick(10.1)
    meter.tick(10.2)
    assert meter.rate(10.5) == pytest.approx(4)
    assert meter.rate(11.3) == 0


def test_monotonic_time_required():
    meter = RateMeter()
    meter.tick(1)
    with pytest.raises(ValueError, match="monotonic"):
        meter.rate(0)

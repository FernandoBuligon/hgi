"""UI-only CLICK persistence, with deterministic seconds and no device access."""

from dataclasses import FrozenInstanceError

import pytest

from hgi.click_feedback import ClickFeedback
from hgi.cursor import CursorAction


def test_feedback_starts_empty_and_ignores_nonclick_actions(fake_clock):
    feedback = ClickFeedback(clock=fake_clock)
    for action in (CursorAction.NONE, CursorAction.MOVE):
        snapshot = feedback.update(action)
        assert snapshot.click_count == 0 and not snapshot.recent_click


def test_click_stays_visible_until_500ms_without_recounting(fake_clock):
    feedback = ClickFeedback(clock=fake_clock)
    fake_clock.now = 10.0
    clicked = feedback.update(CursorAction.CLICK)
    assert clicked.click_count == 1 and clicked.recent_click
    for now, action in ((10.1, CursorAction.NONE), (10.499, CursorAction.MOVE)):
        fake_clock.now = now
        snapshot = feedback.update(action)
        assert snapshot.click_count == 1 and snapshot.recent_click
    fake_clock.now = 10.5
    expired = feedback.update(CursorAction.NONE)
    assert expired.click_count == 1 and not expired.recent_click
    assert clicked.recent_click  # Later updates cannot mutate an earlier snapshot.
    with pytest.raises(FrozenInstanceError):
        clicked.click_count = 99


def test_new_click_increments_once_and_restarts_only_the_ui_deadline(fake_clock):
    feedback = ClickFeedback(clock=fake_clock)
    feedback.update(CursorAction.CLICK)
    fake_clock.now = 0.4
    second = feedback.update(CursorAction.CLICK)
    assert second.click_count == 2 and second.recent_click
    fake_clock.now = 0.5
    assert feedback.update(CursorAction.NONE).recent_click
    fake_clock.now = 0.4 + 0.5
    expired = feedback.update(CursorAction.NONE)
    assert expired.click_count == 2 and not expired.recent_click


def test_reset_and_independent_ui_sessions(fake_clock):
    first, second = ClickFeedback(clock=fake_clock), ClickFeedback(clock=fake_clock)
    first.update(CursorAction.CLICK)
    assert second.update(CursorAction.NONE).click_count == 0
    first.reset()
    cleared = first.update(CursorAction.NONE)
    assert cleared.click_count == 0 and not cleared.recent_click

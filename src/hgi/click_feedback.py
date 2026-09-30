"""UI-only click count and transient feedback, independent of gesture timing."""

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from hgi.cursor import CursorAction

_CLICK_DISPLAY_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class ClickFeedbackState:
    """Display snapshot; contains no command, position or permission to click."""

    click_count: int = 0
    recent_click: bool = False


class ClickFeedback:
    """Observe each emitted action once; never retain or emit cursor commands.

    Each CLICK increments the session count and restarts a 500 ms display
    deadline. MOVE/NONE only sample visibility. Use a separate monotonic clock
    for UI, not the temporal filter's clock. No background timer is needed.
    """

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self.reset()

    def reset(self) -> None:
        """Start an empty UI session, without touching controller/filter/sink."""
        self._click_count = 0
        self._last_click_at: float | None = None

    def update(self, action: CursorAction) -> ClickFeedbackState:
        """Count a newly emitted action and return visibility at this UI sample."""
        now = self._clock()
        if action is CursorAction.CLICK:
            self._click_count += 1
            self._last_click_at = now
        recent = (
            self._last_click_at is not None
            and now < self._last_click_at + _CLICK_DISPLAY_SECONDS
        )
        return ClickFeedbackState(self._click_count, recent)

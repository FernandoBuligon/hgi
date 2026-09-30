"""Typed cursor intentions and an inspectable output with no device access."""

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from hgi.geometry import Point2D
from hgi.gesture_detector import Gesture


class ControlState(Enum):
    """Explicit logical opt-in; ENABLED still uses only dry-run output."""

    DISABLED = "DISABLED"
    ENABLED = "ENABLED"


class CursorAction(Enum):
    """Logical actions only; NONE records an update without movement or click."""

    MOVE = "MOVE"
    CLICK = "CLICK"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class CursorCommand:
    """Immutable intention in logical screen pixels, retaining subpixels.

    MOVE/CLICK require finite, nonnegative X/Y. NONE has no position. Screen
    upper bounds belong to the controller, which knows the supplied dimensions.
    An optional gesture records provenance without invoking any external action.
    """

    action: CursorAction
    x: float | None = None
    y: float | None = None
    gesture: Gesture | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, CursorAction):
            raise TypeError("Cursor action must be a CursorAction")
        if self.gesture is not None and not isinstance(self.gesture, Gesture):
            raise TypeError("Originating gesture must be a Gesture or None")
        if self.action is CursorAction.NONE:
            if self.x is not None or self.y is not None:
                raise ValueError("NONE must not contain a position")
            return
        if self.x is None or self.y is None:
            raise ValueError("MOVE and CLICK require both position coordinates")
        Point2D(self.x, self.y)
        if any(isinstance(value, bool) or value < 0 for value in (self.x, self.y)):
            raise ValueError("Cursor coordinates must be nonnegative numbers")


class CursorSink(Protocol):
    """Small output boundary; implementations define how intentions are observed."""

    def emit(self, command: CursorCommand) -> None:
        """Receive one intention. Only an in-memory implementation exists now."""
        ...


class DryRunCursorSink:
    """Store intentions in order without performing I/O or controlling devices.

    History is unbounded by default; set max_history for continuous visual demos.
    Instances and their controllers are intended for sequential use.
    """

    def __init__(self, *, max_history: int | None = None) -> None:
        if max_history is not None and (
            isinstance(max_history, bool)
            or not isinstance(max_history, int)
            or max_history < 1
        ):
            raise ValueError("max_history must be a positive integer or None")
        self._commands: deque[CursorCommand] = deque(maxlen=max_history)

    @property
    def commands(self) -> tuple[CursorCommand, ...]:
        """Return an immutable snapshot; later emissions cannot change it."""
        return tuple(self._commands)

    def emit(self, command: CursorCommand) -> None:
        """Append the intention to this sink's private history, with no effects."""
        self._commands.append(command)

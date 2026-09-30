"""Opt-in mouse boundary; this is the only module that imports PyAutoGUI."""

from __future__ import annotations

import os
import sys
from typing import Protocol

from hgi.cursor import CursorAction, CursorCommand, CursorMode
from hgi.geometry import Point2D, normalized_to_pixels


class RealCursorError(RuntimeError):
    """Real output is unavailable or has been stopped; restart to try again."""


class MouseBackend(Protocol):
    """Injectable device boundary; no gesture interpretation or timing."""

    def size(self) -> tuple[int, int]:
        """Return the available screen dimensions without sending input."""
        ...

    def move_to(self, x: int, y: int) -> None:
        """Move once to the supplied integer pixels."""
        ...

    def click(self, x: int, y: int) -> None:
        """Perform one primary click at the supplied integer pixels."""
        ...


class PyAutoGUIBackend:
    """Lazy PyAutoGUI adapter with FAILSAFE enabled and PAUSE unchanged.

    Linux real control requires X11; XWayland does not grant Wayland desktop
    control and is rejected. Construction and size queries never send input.
    Runtime mouse exceptions propagate unchanged; the sink latches the failure.
    """

    def __init__(self) -> None:
        if sys.platform.startswith("linux") and (
            os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
            or os.environ.get("WAYLAND_DISPLAY")
        ):
            raise RealCursorError("PyAutoGUI real control requires X11, not Wayland")
        try:
            import pyautogui
        except Exception as error:
            raise RealCursorError(
                "PyAutoGUI unavailable: install HGI [control] and check display/"
                "input permissions. Use default dry-run; see README.md."
            ) from error
        self._api = pyautogui
        self._api.FAILSAFE = True

    def size(self) -> tuple[int, int]:
        """Query resolution only when this explicitly selected backend exists."""
        return tuple(self._api.size())

    def move_to(self, x: int, y: int) -> None:
        """Forward exactly one instantaneous MOVE with native fail-safe/pause."""
        self._api.FAILSAFE = True
        self._api.moveTo(x, y, duration=0.0, logScreenshot=False)

    def click(self, x: int, y: int) -> None:
        """Forward one primary click at the command target; never send keys."""
        self._api.FAILSAFE = True
        self._api.click(
            x, y, clicks=1, button="primary", duration=0.0, logScreenshot=False
        )


class RealCursorSink:
    """Translate each MOVE/CLICK once; NONE has no device effect.

    Coordinates use Python round (ties to even), then bounds validation, never
    remapping/clipping/EMA. A paired screen override may restrict the detected
    top-left rectangle. Any action failure permanently stops this instance,
    including interrupts; no reset, retry, pending command or debounce exists.
    The caller must use CursorController's DISABLED/enable gate for sessions.
    """

    def __init__(
        self,
        *,
        backend: MouseBackend | None = None,
        screen_width: int | None = None,
        screen_height: int | None = None,
    ) -> None:
        if (screen_width is None) != (screen_height is None):
            raise ValueError("Supply both screen dimensions or neither")
        self._backend = backend if backend is not None else PyAutoGUIBackend()
        self._detected_size = self._backend.size()
        width, height = self._detected_size
        normalized_to_pixels(Point2D(0, 0), width, height)
        self._width = width if screen_width is None else screen_width
        self._height = height if screen_height is None else screen_height
        normalized_to_pixels(Point2D(0, 0), self._width, self._height)
        if self._width > width or self._height > height:
            raise ValueError("Screen override exceeds detected screen bounds")
        self._failed = False

    @property
    def mode(self) -> CursorMode:
        """Identify real output independently of controller enable/disable."""
        return CursorMode.REAL_CONTROL

    @property
    def detected_size(self) -> tuple[int, int]:
        """Screen size sampled once at construction, without monitor polling."""
        return self._detected_size

    @property
    def screen_width(self) -> int:
        """Width supplied to the existing cursor pipeline."""
        return self._width

    @property
    def screen_height(self) -> int:
        """Height supplied to the existing cursor pipeline."""
        return self._height

    @property
    def failed(self) -> bool:
        """True after any action failure; a stopped sink cannot be reused."""
        return self._failed

    def _coordinates(self, command: CursorCommand) -> tuple[int, int]:
        assert command.x is not None and command.y is not None
        x, y = round(command.x), round(command.y)
        if not (
            0 <= command.x < self._width
            and 0 <= command.y < self._height
            and 0 <= x < self._width
            and 0 <= y < self._height
        ):
            raise ValueError("Cursor coordinates exceed screen bounds")
        return x, y

    def emit(self, command: CursorCommand) -> None:
        """Execute one intention or propagate its original failure and stop."""
        if command.action is CursorAction.NONE:
            return
        if self._failed:
            raise RealCursorError("Real cursor stopped after failure; restart demo")
        try:
            x, y = self._coordinates(command)
            if command.action is CursorAction.MOVE:
                self._backend.move_to(x, y)
            elif command.action is CursorAction.CLICK:
                self._backend.click(x, y)
        except BaseException:
            self._failed = True
            raise

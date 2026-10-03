"""Typed non-cursor gesture actions with dry-run and injectable real backends."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from pathlib import Path
from time import monotonic
from typing import Protocol

from hgi.gesture_detector import Gesture

DEFAULT_SPOTIFY_TRACK_URI = "spotify:track:2zYzyRzz6pRmhPzyfMEC8s"


class ActionKind(Enum):
    """System-level intentions produced by stable non-cursor gestures."""

    VOLUME_UP = "VOLUME_UP"
    VOLUME_DOWN = "VOLUME_DOWN"
    SCREENSHOT = "SCREENSHOT"
    PLAY_SPOTIFY_TRACK = "PLAY_SPOTIFY_TRACK"


@dataclass(frozen=True, slots=True)
class ActionIntent:
    """A typed action request without cursor coordinates."""

    kind: ActionKind
    path: Path | None = None
    uri: str | None = None


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Current-frame action result; empty means no new system intention."""

    intent: ActionIntent | None = None
    executed: bool = False
    message: str | None = None


class ActionSink(Protocol):
    """Output boundary for non-cursor actions."""

    def emit(self, intent: ActionIntent) -> ActionResult:
        """Observe or execute one typed action."""
        ...


@dataclass(frozen=True, slots=True)
class ActionConfig:
    """Small set of user-visible defaults for advanced gesture actions."""

    volume_step_percent: int = 5
    action_stable_seconds: float = 0.25
    volume_repeat_seconds: float = 0.35
    screenshot_cooldown_seconds: float = 2.0
    rock_stable_seconds: float = 0.7
    rock_cooldown_seconds: float = 5.0
    spotify_track_uri: str = DEFAULT_SPOTIFY_TRACK_URI
    screenshot_directory: Path = Path.home() / "Pictures" / "HGI"

    def __post_init__(self) -> None:
        if (
            isinstance(self.volume_step_percent, bool)
            or not isinstance(self.volume_step_percent, int)
            or not 1 <= self.volume_step_percent <= 100
        ):
            raise ValueError("volume_step_percent must be an integer in 1..100")
        for value in (
            self.action_stable_seconds,
            self.volume_repeat_seconds,
            self.screenshot_cooldown_seconds,
            self.rock_stable_seconds,
            self.rock_cooldown_seconds,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError("Action timings must be finite nonnegative numbers")
        if not self.spotify_track_uri.startswith("spotify:track:"):
            raise ValueError("spotify_track_uri must be a spotify:track URI")


class DryRunActionSink:
    """Record action intentions without changing volume, files or applications."""

    def __init__(self, *, max_history: int | None = None) -> None:
        self._intents: deque[ActionIntent] = deque(maxlen=max_history)

    @property
    def intents(self) -> tuple[ActionIntent, ...]:
        """Immutable snapshot of virtual system actions."""
        return tuple(self._intents)

    def emit(self, intent: ActionIntent) -> ActionResult:
        self._intents.append(intent)
        return ActionResult(intent=intent, executed=False, message="dry-run")


class VolumeBackend(Protocol):
    """Real volume backend; implementations clamp internally."""

    def change(self, delta_percent: int) -> None:
        """Apply a signed percentage change within safe bounds."""
        ...


class ScreenshotBackend(Protocol):
    """Real screenshot backend isolated from tests."""

    def save(self, path: Path) -> None:
        """Capture the current screen to path."""
        ...


class SpotifyBackend(Protocol):
    """Real Spotify backend without web API credentials."""

    def play_track(self, uri: str) -> None:
        """Open or switch Spotify to the supplied track URI."""
        ...


class CommandVolumeBackend:
    """Use wpctl first, with pactl fallback, never shell interpolation."""

    _WPCTL_PATTERN = re.compile(r"Volume:\s+([0-9]+(?:\.[0-9]+)?)")
    _PACTL_PATTERN = re.compile(r"/\s*([0-9]{1,3})%\s*/")

    def __init__(self) -> None:
        self._wpctl = shutil.which("wpctl")
        self._pactl = shutil.which("pactl")
        if self._wpctl is None and self._pactl is None:
            raise RuntimeError("No supported volume backend found (wpctl or pactl)")

    def _current_percent(self) -> int:
        if self._wpctl is not None:
            result = subprocess.run(
                [self._wpctl, "get-volume", "@DEFAULT_AUDIO_SINK@"],
                check=True,
                capture_output=True,
                text=True,
            )
            match = self._WPCTL_PATTERN.search(result.stdout)
            if match is None:
                raise RuntimeError("Could not parse wpctl volume")
            return round(float(match.group(1)) * 100)
        assert self._pactl is not None
        result = subprocess.run(
            [self._pactl, "get-sink-volume", "@DEFAULT_SINK@"],
            check=True,
            capture_output=True,
            text=True,
        )
        match = self._PACTL_PATTERN.search(result.stdout)
        if match is None:
            raise RuntimeError("Could not parse pactl volume")
        return int(match.group(1))

    def change(self, delta_percent: int) -> None:
        target = min(100, max(0, self._current_percent() + delta_percent))
        if self._wpctl is not None:
            subprocess.run(
                [self._wpctl, "set-volume", "@DEFAULT_AUDIO_SINK@", f"{target}%"],
                check=True,
            )
            return
        assert self._pactl is not None
        subprocess.run(
            [self._pactl, "set-sink-volume", "@DEFAULT_SINK@", f"{target}%"],
            check=True,
        )


class PyAutoGUIScreenshotBackend:
    """Use PyAutoGUI only when real control is explicitly selected."""

    def __init__(self) -> None:
        try:
            import pyautogui
        except Exception as error:
            raise RuntimeError("PyAutoGUI screenshot backend unavailable") from error
        self._api = pyautogui
        self._api.FAILSAFE = True

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        image = self._api.screenshot()
        image.save(path)


class LocalSpotifyBackend:
    """Open Spotify track URIs locally via MPRIS when possible, else app URI."""

    def __init__(self) -> None:
        self._busctl = shutil.which("busctl")
        self._spotify = shutil.which("spotify")
        self._xdg_open = shutil.which("xdg-open")
        if self._busctl is None and self._spotify is None and self._xdg_open is None:
            raise RuntimeError("No local Spotify opener found")

    def _call_mpris(self, member: str, *args: str) -> bool:
        if self._busctl is None:
            return False
        command = [
            self._busctl,
            "--user",
            "call",
            "org.mpris.MediaPlayer2.spotify",
            "/org/mpris/MediaPlayer2",
            "org.mpris.MediaPlayer2.Player",
            member,
        ]
        command.extend(args)
        return subprocess.run(command, check=False).returncode == 0

    def play_track(self, uri: str) -> None:
        if self._call_mpris("OpenUri", "s", uri):
            self._call_mpris("Play")
            return
        opener = [self._spotify, uri] if self._spotify else [self._xdg_open, uri]
        subprocess.Popen([part for part in opener if part is not None])


class RealActionSink:
    """Execute typed system actions through small injected backends."""

    def __init__(
        self,
        config: ActionConfig,
        *,
        volume: VolumeBackend | None = None,
        screenshot: ScreenshotBackend | None = None,
        spotify: SpotifyBackend | None = None,
    ) -> None:
        self._config = config
        self._volume = volume
        self._screenshot = screenshot
        self._spotify = spotify

    def emit(self, intent: ActionIntent) -> ActionResult:
        if intent.kind is ActionKind.VOLUME_UP:
            if self._volume is None:
                self._volume = CommandVolumeBackend()
            self._volume.change(self._config.volume_step_percent)
        elif intent.kind is ActionKind.VOLUME_DOWN:
            if self._volume is None:
                self._volume = CommandVolumeBackend()
            self._volume.change(-self._config.volume_step_percent)
        elif intent.kind is ActionKind.SCREENSHOT:
            assert intent.path is not None
            if self._screenshot is None:
                self._screenshot = PyAutoGUIScreenshotBackend()
            self._screenshot.save(intent.path)
        elif intent.kind is ActionKind.PLAY_SPOTIFY_TRACK:
            assert intent.uri is not None
            if self._spotify is None:
                self._spotify = LocalSpotifyBackend()
            self._spotify.play_track(intent.uri)
        return ActionResult(intent=intent, executed=True)


class GestureActionController:
    """Map already-stable gestures to non-cursor intentions with debounce."""

    def __init__(
        self,
        config: ActionConfig | None = None,
        *,
        sink: ActionSink | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._config = config if config is not None else ActionConfig()
        self._sink = sink if sink is not None else DryRunActionSink(max_history=1)
        self._clock = clock
        self.reset()

    @property
    def config(self) -> ActionConfig:
        """Return immutable action thresholds/defaults."""
        return self._config

    def reset(self) -> None:
        """Rearm one-shot actions and clear gesture hold state."""
        self._gesture: Gesture | None = None
        self._since = 0.0
        self._last_volume: float | None = None
        self._last_screenshot: float | None = None
        self._last_rock: float | None = None
        self._screenshot_armed = True
        self._rock_armed = True

    def _intent_for(self, gesture: Gesture, now: float) -> ActionIntent | None:
        held = now - self._since
        if gesture in (Gesture.THUMBS_UP, Gesture.THUMBS_DOWN):
            if held < self._config.action_stable_seconds:
                return None
            if (
                self._last_volume is not None
                and now < self._last_volume + self._config.volume_repeat_seconds
            ):
                return None
            self._last_volume = now
            kind = (
                ActionKind.VOLUME_UP
                if gesture is Gesture.THUMBS_UP
                else ActionKind.VOLUME_DOWN
            )
            return ActionIntent(kind)
        if gesture is Gesture.PEACE:
            if not self._screenshot_armed or held < self._config.action_stable_seconds:
                return None
            if (
                self._last_screenshot is not None
                and now
                < self._last_screenshot + self._config.screenshot_cooldown_seconds
            ):
                return None
            self._screenshot_armed = False
            self._last_screenshot = now
            timestamp = datetime.fromtimestamp(now).strftime("%Y-%m-%d_%H-%M-%S")
            path = self._config.screenshot_directory / f"HGI_{timestamp}.png"
            return ActionIntent(ActionKind.SCREENSHOT, path=path)
        if gesture is Gesture.ROCK:
            if not self._rock_armed or held < self._config.rock_stable_seconds:
                return None
            if (
                self._last_rock is not None
                and now < self._last_rock + self._config.rock_cooldown_seconds
            ):
                return None
            self._rock_armed = False
            self._last_rock = now
            return ActionIntent(
                ActionKind.PLAY_SPOTIFY_TRACK, uri=self._config.spotify_track_uri
            )
        return None

    def update(self, gesture: Gesture, *, enabled: bool) -> ActionResult:
        """Return at most one action for this frame; disabled sessions reset."""
        if not enabled:
            self.reset()
            return ActionResult()
        now = self._clock()
        if gesture is not self._gesture:
            if gesture is not Gesture.PEACE:
                self._screenshot_armed = True
            if gesture is not Gesture.ROCK:
                self._rock_armed = True
            self._gesture = gesture
            self._since = now
            self._last_volume = None
        intent = self._intent_for(gesture, now)
        if intent is None:
            return ActionResult()
        try:
            return self._sink.emit(intent)
        except Exception as error:
            return ActionResult(
                intent=intent, executed=False, message=f"error: {error}"
            )

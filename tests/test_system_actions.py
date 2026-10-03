"""System gesture action contracts with fake sinks and fake clocks only."""

from pathlib import Path
from types import SimpleNamespace

from hgi.gesture_detector import Gesture
from hgi.system_actions import (
    ActionConfig,
    ActionIntent,
    ActionKind,
    ActionResult,
    CommandVolumeBackend,
    DryRunActionSink,
    GestureActionController,
    RealActionSink,
)


def action_controller(fake_clock):
    sink = DryRunActionSink()
    controller = GestureActionController(
        ActionConfig(
            action_stable_seconds=0.25,
            volume_repeat_seconds=0.35,
            screenshot_cooldown_seconds=2.0,
            rock_stable_seconds=0.7,
            rock_cooldown_seconds=5.0,
            screenshot_directory=Path("/tmp/hgi-tests"),
        ),
        sink=sink,
        clock=fake_clock,
    )
    return controller, sink


def test_volume_repeats_while_thumb_gesture_is_held(fake_clock):
    controller, sink = action_controller(fake_clock)
    assert controller.update(Gesture.THUMBS_UP, enabled=True) == ActionResult()
    fake_clock.now = 0.25
    assert (
        controller.update(Gesture.THUMBS_UP, enabled=True).intent.kind
        is ActionKind.VOLUME_UP
    )
    fake_clock.now = 0.59
    assert controller.update(Gesture.THUMBS_UP, enabled=True) == ActionResult()
    fake_clock.now = 0.60
    assert (
        controller.update(Gesture.THUMBS_UP, enabled=True).intent.kind
        is ActionKind.VOLUME_UP
    )
    assert [intent.kind for intent in sink.intents] == [
        ActionKind.VOLUME_UP,
        ActionKind.VOLUME_UP,
    ]
    fake_clock.now = 0.61
    controller.update(Gesture.UNKNOWN, enabled=True)
    fake_clock.now = 0.86
    controller.update(Gesture.THUMBS_DOWN, enabled=True)
    fake_clock.now = 1.11
    assert (
        controller.update(Gesture.THUMBS_DOWN, enabled=True).intent.kind
        is ActionKind.VOLUME_DOWN
    )


def test_screenshot_is_one_shot_per_activation_and_uses_cooldown(fake_clock):
    controller, sink = action_controller(fake_clock)
    controller.update(Gesture.PEACE, enabled=True)
    fake_clock.now = 0.25
    first = controller.update(Gesture.PEACE, enabled=True)
    assert first.intent.kind is ActionKind.SCREENSHOT
    assert first.intent.path.name.startswith("HGI_")
    fake_clock.now = 1.0
    assert controller.update(Gesture.PEACE, enabled=True) == ActionResult()
    controller.update(Gesture.UNKNOWN, enabled=True)
    fake_clock.now = 1.25
    assert controller.update(Gesture.PEACE, enabled=True) == ActionResult()
    fake_clock.now = 3.26
    second = controller.update(Gesture.PEACE, enabled=True)
    assert second.intent.kind is ActionKind.SCREENSHOT
    assert len(sink.intents) == 2


def test_rock_requires_longer_stability_and_sends_configured_uri_once(fake_clock):
    controller, sink = action_controller(fake_clock)
    uri = controller.config.spotify_track_uri
    controller.update(Gesture.ROCK, enabled=True)
    fake_clock.now = 0.69
    assert controller.update(Gesture.ROCK, enabled=True) == ActionResult()
    fake_clock.now = 0.70
    played = controller.update(Gesture.ROCK, enabled=True)
    assert played.intent.kind is ActionKind.PLAY_SPOTIFY_TRACK
    assert played.intent.uri == uri
    fake_clock.now = 4.0
    assert controller.update(Gesture.ROCK, enabled=True) == ActionResult()
    controller.update(Gesture.UNKNOWN, enabled=True)
    fake_clock.now = 5.01
    controller.update(Gesture.ROCK, enabled=True)
    fake_clock.now = 5.71
    assert (
        controller.update(Gesture.ROCK, enabled=True).intent.kind
        is ActionKind.PLAY_SPOTIFY_TRACK
    )
    assert [intent.kind for intent in sink.intents] == [
        ActionKind.PLAY_SPOTIFY_TRACK,
        ActionKind.PLAY_SPOTIFY_TRACK,
    ]


def test_disabled_session_resets_pending_system_actions(fake_clock):
    controller, sink = action_controller(fake_clock)
    controller.update(Gesture.THUMBS_UP, enabled=True)
    fake_clock.now = 0.25
    assert controller.update(Gesture.THUMBS_UP, enabled=False) == ActionResult()
    fake_clock.now = 0.5
    assert controller.update(Gesture.THUMBS_UP, enabled=True) == ActionResult()
    assert sink.intents == ()


def test_real_action_sink_uses_injected_backends_without_touching_real_system(tmp_path):
    class Volume:
        changes = []

        def change(self, delta_percent):
            self.changes.append(delta_percent)

    class Screenshot:
        paths = []

        def save(self, path):
            self.paths.append(path)

    class Spotify:
        uris = []

        def play_track(self, uri):
            self.uris.append(uri)

    config = ActionConfig(
        screenshot_directory=tmp_path, spotify_track_uri="spotify:track:abc"
    )
    volume, screenshot, spotify = Volume(), Screenshot(), Spotify()
    sink = RealActionSink(config, volume=volume, screenshot=screenshot, spotify=spotify)

    sink.emit(ActionIntent(ActionKind.VOLUME_UP))
    sink.emit(ActionIntent(ActionKind.VOLUME_DOWN))
    shot = tmp_path / "shot.png"
    sink.emit(ActionIntent(ActionKind.SCREENSHOT, path=shot))
    sink.emit(ActionIntent(ActionKind.PLAY_SPOTIFY_TRACK, uri=config.spotify_track_uri))

    assert volume.changes == [5, -5]
    assert screenshot.paths == [shot]
    assert spotify.uris == [config.spotify_track_uri]


def test_volume_backend_clamps_wpctl_to_100_and_uses_argument_lists(monkeypatch):
    import hgi.system_actions as actions

    calls = []

    def fake_which(name):
        return f"/usr/bin/{name}" if name == "wpctl" else None

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if "get-volume" in command:
            return SimpleNamespace(stdout="Volume: 0.98\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(actions.shutil, "which", fake_which)
    monkeypatch.setattr(actions.subprocess, "run", fake_run)

    CommandVolumeBackend().change(5)

    assert calls[0][0] == ["/usr/bin/wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]
    assert calls[1][0] == [
        "/usr/bin/wpctl",
        "set-volume",
        "@DEFAULT_AUDIO_SINK@",
        "100%",
    ]
    assert calls[0][1]["check"] is True
    assert calls[1][1]["check"] is True


def test_action_failures_are_reported_without_resetting_the_controller(fake_clock):
    class FailingSink:
        def emit(self, intent):
            raise RuntimeError("spotify unavailable")

    controller = GestureActionController(
        ActionConfig(rock_stable_seconds=0.0, rock_cooldown_seconds=0.0),
        sink=FailingSink(),
        clock=fake_clock,
    )
    result = controller.update(Gesture.ROCK, enabled=True)

    assert result.intent.kind is ActionKind.PLAY_SPOTIFY_TRACK
    assert result.executed is False
    assert "spotify unavailable" in result.message

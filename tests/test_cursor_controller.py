"""Synthetic integration of recognition, mapping, EMA and dry-run output."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace

import pytest

from hgi.cursor import CursorAction, CursorCommand, DryRunCursorSink
from hgi.cursor_controller import CursorConfig, CursorController
from hgi.finger_state import GestureConfig
from hgi.geometry import Region2D
from hgi.gesture_detector import Gesture, GestureDetector
from hgi.hand_landmarks import DetectedHand, HandLandmark


def at_indicator(hand: DetectedHand, x: float, y: float) -> DetectedHand:
    """Translate the entire pose, preserving its geometric gesture."""
    tip = hand.landmarks[HandLandmark.INDEX_FINGER_TIP]
    return replace(
        hand,
        landmarks=tuple(
            replace(point, x=point.x + x - tip.x, y=point.y + y - tip.y)
            for point in hand.landmarks
        ),
    )


def pinched(hand: DetectedHand) -> DetectedHand:
    """Close the thumb/index gap using real internal landmarks."""
    points = list(hand.landmarks)
    points[HandLandmark.THUMB_TIP] = points[HandLandmark.INDEX_FINGER_TIP]
    return replace(hand, landmarks=tuple(points))


@pytest.mark.parametrize("width,height", [(1920, 1080), (801, 601), (1, 1)])
def test_point_center_uses_supplied_screen_dimensions(hand_factory, width, height):
    controller = CursorController(CursorConfig(width, height))
    command = controller.update(at_indicator(hand_factory("index"), 0.5, 0.5))
    assert command == CursorCommand(
        CursorAction.MOVE, (width - 1) / 2, (height - 1) / 2, Gesture.POINT
    )


@pytest.mark.parametrize(
    "x,y,expected",
    [
        (0.2, 0.3, (0, 0)),
        (0.8, 0.7, (1000, 500)),
        (-0.5, -0.5, (0, 0)),
        (1.5, 1.5, (1000, 500)),
    ],
)
def test_active_region_reaches_edges_and_clips_predictions(
    hand_factory, x, y, expected
):
    config = CursorConfig(
        1001, 501, active_region=Region2D(0.2, 0.3, 0.8, 0.7), mirror_x=False
    )
    command = CursorController(config).update(at_indicator(hand_factory("index"), x, y))
    assert (command.x, command.y) == pytest.approx(expected)


def test_raw_camera_motion_to_user_right_moves_virtual_cursor_right(hand_factory):
    """Facing an unmirrored camera, physical right decreases raw image X."""
    controller = CursorController(CursorConfig(1001, 501, smoothing_alpha=1.0))
    before = controller.update(at_indicator(hand_factory("index"), 0.7, 0.5))
    after = controller.update(at_indicator(hand_factory("index"), 0.3, 0.5))
    assert (before.x, after.x) == pytest.approx((250, 750))
    assert before.y == after.y == 250


def test_already_mirrored_input_can_disable_second_reflection(hand_factory):
    controller = CursorController(CursorConfig(1001, 501, mirror_x=False))
    command = controller.update(at_indicator(hand_factory("index"), 0.7, 0.5))
    assert command.x == pytest.approx(750)


def test_point_sequence_reuses_ema_in_both_axes(hand_factory):
    controller = CursorController(
        CursorConfig(1001, 501, mirror_x=False, smoothing_alpha=0.25)
    )
    pose = hand_factory("index")
    commands = [
        controller.update(at_indicator(pose, x, y))
        for x, y in [(0.1, 0.1), (0.9, 0.9), (0.9, 0.9)]
    ]
    assert [(c.x, c.y) for c in commands] == [(0, 0), (250, 125), (437.5, 218.75)]


@pytest.mark.parametrize(
    "pose,gesture",
    [
        (None, Gesture.UNKNOWN),
        (("index", "middle"), Gesture.UNKNOWN),
        ((), Gesture.FIST),
        (("thumb", "index", "middle", "ring", "pinky"), Gesture.OPEN_HAND),
    ],
)
def test_inactivity_emits_none_and_discards_old_motion(hand_factory, pose, gesture):
    sink = DryRunCursorSink()
    controller = CursorController(CursorConfig(1001, 501, mirror_x=False), sink=sink)
    controller.update(at_indicator(hand_factory("index"), 0.1, 0.1))
    idle = controller.update(None if pose is None else hand_factory(*pose))
    resumed = controller.update(at_indicator(hand_factory("index"), 0.9, 0.9))
    assert idle == CursorCommand(CursorAction.NONE, gesture=gesture)
    assert (resumed.x, resumed.y) == (1000, 500)
    assert sink.commands[1] == idle


def test_pinch_clicks_last_virtual_position_once_and_does_not_move(hand_factory):
    sink = DryRunCursorSink()
    controller = CursorController(CursorConfig(1001, 501), sink=sink)
    moved = controller.update(at_indicator(hand_factory("index"), 0.3, 0.4))
    pinch = pinched(at_indicator(hand_factory("index"), 0.8, 0.8))
    click = controller.update(pinch)
    held = controller.update(pinch)
    assert click == CursorCommand(CursorAction.CLICK, moved.x, moved.y, Gesture.PINCH)
    assert held == CursorCommand(CursorAction.NONE, gesture=Gesture.PINCH)
    controller.update(hand_factory("index"))
    assert controller.update(pinch).action is CursorAction.CLICK
    assert [c.action for c in sink.commands] == [
        CursorAction.MOVE,
        CursorAction.CLICK,
        CursorAction.NONE,
        CursorAction.MOVE,
        CursorAction.CLICK,
    ]


def test_initial_pinch_click_uses_mapped_indicator_without_a_move(hand_factory):
    controller = CursorController(CursorConfig(1001, 501))
    command = controller.update(pinched(at_indicator(hand_factory("index"), 0.3, 0.5)))
    assert command.action is CursorAction.CLICK
    assert (command.x, command.y) == pytest.approx((750, 250))


def test_pinch_preserves_ema_for_point_resume(hand_factory):
    controller = CursorController(
        CursorConfig(1001, 501, mirror_x=False, smoothing_alpha=0.5)
    )
    pose = hand_factory("index")
    controller.update(at_indicator(pose, 0.1, 0.1))
    controller.update(pinched(at_indicator(pose, 0.9, 0.9)))
    resumed = controller.update(at_indicator(pose, 0.9, 0.9))
    assert (resumed.x, resumed.y) == (500, 250)


def test_reset_clears_position_ema_and_pinch_edge_but_keeps_output_history(
    hand_factory,
):
    sink = DryRunCursorSink()
    controller = CursorController(CursorConfig(1001, 501, mirror_x=False), sink=sink)
    pose = hand_factory("index")
    controller.update(at_indicator(pose, 0.1, 0.1))
    controller.update(pinched(pose))
    controller.reset()
    click = controller.update(pinched(at_indicator(pose, 0.9, 0.9)))
    assert (click.action, click.x, click.y) == (CursorAction.CLICK, 1000, 500)
    controller.reset()
    assert controller.update(at_indicator(pose, 0.9, 0.9)).x == 1000
    assert len(sink.commands) == 4


def test_tracking_loss_rearms_logical_pinch_edge_as_documented(hand_factory):
    controller = CursorController(CursorConfig(1001, 501))
    hand = pinched(hand_factory("index"))
    assert controller.update(hand).action is CursorAction.CLICK
    controller.update(None)
    assert controller.update(hand).action is CursorAction.CLICK


def test_invalid_geometry_propagates_and_clears_previous_motion(hand_factory):
    controller = CursorController(CursorConfig(1001, 501, mirror_x=False))
    pose = hand_factory("index")
    controller.update(at_indicator(pose, 0.1, 0.1))
    invalid = replace(pose, landmarks=(pose.landmarks[0],) * 21)
    with pytest.raises(ValueError, match="reference"):
        controller.update(invalid)
    assert controller.update(at_indicator(pose, 0.9, 0.9)).x == 1000


def test_recognition_thresholds_can_be_injected_without_mocking_logic(hand_factory):
    pose = hand_factory("index")
    detector = GestureDetector(GestureConfig(pinch_threshold=10.0))
    controller = CursorController(CursorConfig(1001, 501), detector=detector)
    assert controller.update(pose).action is CursorAction.CLICK


@pytest.mark.parametrize(
    "changes",
    [
        {"screen_width": 0},
        {"screen_height": True},
        {"screen_width": 1.5},
        {"active_region": Region2D(-0.1, 0, 0.9, 1)},
        {"active_region": Region2D(0, 0, 1.1, 1)},
        {"mirror_x": 1},
        {"smoothing_alpha": 0},
        {"smoothing_alpha": float("nan")},
    ],
)
def test_config_rejects_invalid_values_before_processing(changes):
    with pytest.raises(ValueError):
        CursorConfig(**({"screen_width": 1001, "screen_height": 501} | changes))


def test_config_is_immutable_and_default_output_is_dry_run() -> None:
    config = CursorConfig(1001, 501)
    with pytest.raises(FrozenInstanceError):
        config.mirror_x = False
    controller = CursorController(config)
    assert controller.config is config
    assert isinstance(controller.sink, DryRunCursorSink)
    idle = controller.update(None)
    assert controller.sink.commands == (idle,)


def test_controllers_do_not_share_smoothing_state(
    hand_factory: Callable[..., DetectedHand],
):
    config = CursorConfig(1001, 501, mirror_x=False)
    first, second = CursorController(config), CursorController(config)
    pose = hand_factory("index")
    first.update(at_indicator(pose, 0.1, 0.1))
    assert second.update(at_indicator(pose, 0.9, 0.9)).x == 1000

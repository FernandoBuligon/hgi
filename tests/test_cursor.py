"""Contracts for cursor intentions and the in-memory dry-run output."""

import ast
import inspect
from dataclasses import FrozenInstanceError

import pytest

from hgi.cursor import CursorAction, CursorCommand, DryRunCursorSink
from hgi.gesture_detector import Gesture


def test_commands_are_immutable_typed_intentions() -> None:
    command = CursorCommand(CursorAction.MOVE, 1200.0, 540.0, Gesture.POINT)
    assert (command.action, command.x, command.y, command.gesture) == (
        CursorAction.MOVE,
        1200.0,
        540.0,
        Gesture.POINT,
    )
    with pytest.raises(FrozenInstanceError):
        command.x = 0.0


@pytest.mark.parametrize(
    "action,x,y",
    [
        (CursorAction.MOVE, None, None),
        (CursorAction.CLICK, 1.0, None),
        (CursorAction.NONE, 1.0, 2.0),
        (CursorAction.MOVE, float("nan"), 0.0),
        (CursorAction.CLICK, 0.0, float("inf")),
        (CursorAction.MOVE, -1.0, 0.0),
        (CursorAction.MOVE, True, 0.0),
    ],
)
def test_invalid_command_positions_are_rejected(action, x, y) -> None:
    with pytest.raises(ValueError):
        CursorCommand(action, x, y)


def test_enum_contracts_reject_untyped_actions_and_gestures() -> None:
    with pytest.raises(TypeError, match="action"):
        CursorCommand("MOVE", 1.0, 2.0)
    with pytest.raises(TypeError, match="gesture"):
        CursorCommand(CursorAction.MOVE, 1.0, 2.0, "POINT")


def test_dry_run_preserves_order_and_exposes_an_immutable_snapshot() -> None:
    sink = DryRunCursorSink()
    move = CursorCommand(CursorAction.MOVE, 12.5, 24.5, Gesture.POINT)
    click = CursorCommand(CursorAction.CLICK, 12.5, 24.5, Gesture.PINCH)
    idle = CursorCommand(CursorAction.NONE)
    sink.emit(move)
    snapshot = sink.commands
    sink.emit(click)
    sink.emit(idle)
    assert snapshot == (move,)
    assert sink.commands == (move, click, idle)
    assert idle.x is None and idle.y is None and idle.gesture is None


def test_dry_run_instances_do_not_share_history() -> None:
    first, second = DryRunCursorSink(), DryRunCursorSink()
    first.emit(CursorCommand(CursorAction.NONE))
    assert second.commands == ()


def test_cursor_layer_only_imports_standard_library_and_pure_hgi_modules() -> None:
    """Keep device/OS backends outside the command and controller boundary."""
    import hgi.cursor
    import hgi.cursor_controller

    allowed = {
        "dataclasses",
        "enum",
        "typing",
        "hgi.cursor",
        "hgi.geometry",
        "hgi.gesture_detector",
        "hgi.hand_landmarks",
        "hgi.smoothing",
    }
    for module in (hgi.cursor, hgi.cursor_controller):
        tree = ast.parse(inspect.getsource(module))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        assert imports <= allowed

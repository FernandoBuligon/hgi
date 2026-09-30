"""Finite synthetic dry-run demo: python scripts/demo_cursor.py (installed HGI)."""

from dataclasses import dataclass, replace

from hgi.cursor import CursorAction, DryRunCursorSink
from hgi.cursor_controller import CursorConfig, CursorController
from hgi.hand_landmarks import DetectedHand, HandLandmark, NormalizedLandmark
from hgi.temporal import TemporalGestureFilter

# Official landmark order: wrist, thumb, index, middle, ring, pinky.
# Only the index chain is extended. These are illustrative, not recorded hands.
_POINT_POSE = (
    (0.5, 0.875),
    (0.4375, 0.75),
    (0.375, 0.6875),
    (0.4375, 0.65625),
    (0.5, 0.6875),
    (0.375, 0.625),
    (0.375, 0.5),
    (0.375, 0.4375),
    (0.375, 0.375),
    (0.5, 0.625),
    (0.5, 0.5),
    (0.5, 0.59375),
    (0.5, 0.6875),
    (0.625, 0.625),
    (0.625, 0.5),
    (0.625, 0.59375),
    (0.625, 0.6875),
    (0.75, 0.625),
    (0.75, 0.5),
    (0.75, 0.59375),
    (0.75, 0.6875),
)


def _point_hand(x: float, y: float) -> DetectedHand:
    origin_x, origin_y = _POINT_POSE[HandLandmark.INDEX_FINGER_TIP]
    return DetectedHand(
        tuple(
            NormalizedLandmark(px + x - origin_x, py + y - origin_y, 0.0)
            for px, py in _POINT_POSE
        )
    )


@dataclass
class SimulatedClock:
    """Explicit demo time, without sleeping or consulting a real clock."""

    now: float = 0.0

    def __call__(self) -> float:
        return self.now


def main() -> None:
    """Show explicit opt-in, stabilization, cooldown and disarming in dry-run."""
    clock = SimulatedClock()
    sink = DryRunCursorSink()
    controller = CursorController(
        CursorConfig(1920, 1080),
        sink=sink,
        temporal=TemporalGestureFilter(clock=clock),
    )
    first, second = _point_hand(0.5, 0.5), _point_hand(0.4, 0.6)
    points = list(second.landmarks)
    points[HandLandmark.THUMB_TIP] = points[HandLandmark.INDEX_FINGER_TIP]
    pinch = replace(second, landmarks=tuple(points))

    def show(at: float, hand: DetectedHand | None, label: str) -> None:
        clock.now = at
        command = controller.update(hand)
        position = (
            ""
            if command.action is CursorAction.NONE
            else (f" x={command.x:.1f} y={command.y:.1f}")
        )
        print(f"t={at:.2f} {label} -> {command.action.value}{position}")

    print(controller.state.value)
    show(0.0, first, "POINT")
    print("enable()")
    controller.enable()
    for at, hand, label in (
        (0.0, first, "POINT instável"),
        (0.08, first, "POINT estável"),
        (0.1, pinch, "PINCH instável"),
        (0.18, pinch, "PINCH estável"),
        (0.2, pinch, "PINCH mantido"),
        (0.22, second, "abertura instável"),
        (0.3, second, "abertura confirmada"),
        (0.32, pinch, "PINCH instável"),
        (0.4, pinch, "PINCH durante cooldown"),
        (0.6, pinch, "PINCH sem fila"),
        (0.7, second, "nova abertura"),
        (0.8, second, "abertura confirmada"),
        (0.82, pinch, "PINCH instável"),
        (0.9, pinch, "novo PINCH estável"),
    ):
        show(at, hand, label)
    print("disable()")
    controller.disable()
    show(1.0, first, "POINT")


if __name__ == "__main__":
    main()

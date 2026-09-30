"""Finite synthetic dry-run demo: python scripts/demo_cursor.py (installed HGI)."""

from dataclasses import replace

from hgi.cursor import CursorAction, DryRunCursorSink
from hgi.cursor_controller import CursorConfig, CursorController
from hgi.hand_landmarks import DetectedHand, HandLandmark, NormalizedLandmark

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


def main() -> None:
    """Print only intentions, without a camera, monitor query or device backend."""
    sink = DryRunCursorSink()
    controller = CursorController(CursorConfig(1920, 1080), sink=sink)
    first, second = _point_hand(0.5, 0.5), _point_hand(0.4, 0.6)
    points = list(second.landmarks)
    points[HandLandmark.THUMB_TIP] = points[HandLandmark.INDEX_FINGER_TIP]
    pinch = replace(second, landmarks=tuple(points))
    for hand in (first, second, pinch, pinch, None):
        controller.update(hand)
    for command in sink.commands:
        if command.action is CursorAction.NONE:
            print("NONE")
        else:
            print(f"{command.action.value} x={command.x:.1f} y={command.y:.1f}")


if __name__ == "__main__":
    main()

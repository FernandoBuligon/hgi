"""OpenCV drawing over HGI types; no MediaPipe graphical utilities or actions."""

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from hgi.camera import validate_bgr_frame
from hgi.cursor import ControlState, CursorCommand
from hgi.cursor_controller import CursorConfig
from hgi.geometry import Point2D, map_camera_to_screen, normalized_to_pixels
from hgi.gesture_detector import Gesture, GestureObservation
from hgi.hand_landmarks import DetectedHand, HandLandmark
from hgi.temporal import TemporalStatus

_FINGER_CHAINS = (
    (
        HandLandmark.WRIST,
        HandLandmark.THUMB_CMC,
        HandLandmark.THUMB_MCP,
        HandLandmark.THUMB_IP,
        HandLandmark.THUMB_TIP,
    ),
    (
        HandLandmark.WRIST,
        HandLandmark.INDEX_FINGER_MCP,
        HandLandmark.INDEX_FINGER_PIP,
        HandLandmark.INDEX_FINGER_DIP,
        HandLandmark.INDEX_FINGER_TIP,
    ),
    (
        HandLandmark.MIDDLE_FINGER_MCP,
        HandLandmark.MIDDLE_FINGER_PIP,
        HandLandmark.MIDDLE_FINGER_DIP,
        HandLandmark.MIDDLE_FINGER_TIP,
    ),
    (
        HandLandmark.RING_FINGER_MCP,
        HandLandmark.RING_FINGER_PIP,
        HandLandmark.RING_FINGER_DIP,
        HandLandmark.RING_FINGER_TIP,
    ),
    (
        HandLandmark.PINKY_MCP,
        HandLandmark.PINKY_PIP,
        HandLandmark.PINKY_DIP,
        HandLandmark.PINKY_TIP,
        HandLandmark.WRIST,
    ),
    (
        HandLandmark.INDEX_FINGER_MCP,
        HandLandmark.MIDDLE_FINGER_MCP,
        HandLandmark.RING_FINGER_MCP,
        HandLandmark.PINKY_MCP,
    ),
)
HAND_CONNECTIONS = tuple(
    (start, end)
    for chain in _FINGER_CHAINS
    for start, end in zip(chain, chain[1:], strict=False)
)
_GREEN = (80, 220, 80)
_YELLOW = (0, 220, 255)
_WHITE = (255, 255, 255)


@dataclass(frozen=True, slots=True)
class OverlayState:
    """Only public snapshots and current-frame data required for rendering."""

    hand: DetectedHand | None
    observation: GestureObservation
    command: CursorCommand
    control: ControlState
    position: Point2D | None
    temporal: TemporalStatus
    fps: float = 0.0


def overlay_lines(state: OverlayState, config: CursorConfig) -> tuple[str, ...]:
    """Build readable labels; confidence is explicitly the Left/Right score."""
    hand, temporal = state.hand, state.temporal
    score = hand.handedness_score if hand else None
    confidence = "--" if score is None else f"{score:.2f}"
    ratio = state.observation.pinch_ratio
    pinch = "--" if ratio is None else f"{ratio:.2f}"
    position = state.position
    cursor = "--" if position is None else f"{position.x:.0f}, {position.y:.0f}"
    candidate = temporal.candidate.value if temporal.candidate else "--"
    lines = (
        f"HGI | DRY-RUN | CONTROL: {state.control.value}",
        f"Hand: {hand.handedness or '--' if hand else '--'} | "
        f"Confidence (Left/Right): {confidence}",
        f"RAW: {state.observation.raw.value} | STABLE: {temporal.stable.value}",
        f"candidate: {candidate} | armed: {'yes' if temporal.armed else 'no'} | "
        f"cooldown: {'active' if temporal.cooldown_active else 'inactive'}",
        f"Pinch: {pinch} | Cursor: {cursor} | Action: {state.command.action.value}",
        f"FPS: {state.fps:.1f} | "
        f"Logical screen: {config.screen_width}x{config.screen_height}",
    )
    if hand is None:
        return (*lines, "Index normalized: -- | screen target: --")
    tip = hand.landmarks[HandLandmark.INDEX_FINGER_TIP]
    target = map_camera_to_screen(
        Point2D(tip.x, tip.y),
        config.active_region,
        config.screen_width,
        config.screen_height,
        mirror_x=config.mirror_x,
    )
    return (
        *lines,
        f"Index normalized: ({tip.x:.2f}, {tip.y:.2f}) | "
        f"screen target: ({target.x:.0f}, {target.y:.0f})",
    )


def _pixel(point: Point2D, width: int, height: int) -> tuple[int, int]:
    mapped = normalized_to_pixels(point, width, height)
    return round(mapped.x), round(mapped.y)


def _draw_hand(frame: NDArray[np.uint8], state: OverlayState) -> None:
    if state.hand is None:
        return
    height, width = frame.shape[:2]
    points = tuple(
        _pixel(Point2D(p.x, p.y), width, height) for p in state.hand.landmarks
    )
    pinched = (
        state.observation.raw is Gesture.PINCH or state.temporal.stable is Gesture.PINCH
    )
    color = _YELLOW if pinched else _GREEN
    for start, end in HAND_CONNECTIONS:
        cv2.line(frame, points[start], points[end], _GREEN, 2, cv2.LINE_AA)
    for point in points:
        cv2.circle(frame, point, 3, _WHITE, -1, cv2.LINE_AA)
    cv2.circle(frame, points[HandLandmark.INDEX_FINGER_TIP], 9, color, 2, cv2.LINE_AA)
    if pinched:
        cv2.line(
            frame,
            points[HandLandmark.THUMB_TIP],
            points[HandLandmark.INDEX_FINGER_TIP],
            color,
            3,
            cv2.LINE_AA,
        )


def _text(
    frame: NDArray[np.uint8], text: str, location: tuple[int, int], scale: float
) -> None:
    for color, thickness in (((0, 0, 0), 3), (_WHITE, 1)):
        cv2.putText(
            frame,
            text,
            location,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA,
        )


def draw_overlay(
    frame: NDArray[np.uint8], state: OverlayState, config: CursorConfig
) -> NDArray[np.uint8]:
    """Annotate a BGR frame in place, using actual dimensions; never resize it.

    Index screen target is unsmoothed. Cursor is the retained virtual output,
    which may be frozen on PINCH or during short loss. CLICK is a frame event.
    """
    validate_bgr_frame(frame)
    height, width = frame.shape[:2]
    region = config.active_region
    start = _pixel(Point2D(region.left, region.top), width, height)
    end = _pixel(Point2D(region.right, region.bottom), width, height)
    cv2.rectangle(frame, start, end, _GREEN, 1)
    _draw_hand(frame, state)
    scale = max(0.25, min(width / 640, height / 480, 1.0) * 0.45)
    spacing = max(13, round(22 * min(width / 640, height / 480, 1.0)))
    for index, line in enumerate(overlay_lines(state, config)):
        _text(frame, line, (8, 20 + index * spacing), scale)
    _text(frame, "ACTIVE AREA = full logical screen", (start[0] + 4, end[1] - 8), scale)
    _text(
        frame, "E enable | D disable | R reset | Q / Esc quit", (8, height - 10), scale
    )
    return frame

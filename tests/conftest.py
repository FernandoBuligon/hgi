"""Readable synthetic hands; all geometry remains real HGI code."""

from collections.abc import Callable
from dataclasses import dataclass
from math import cos, radians, sin
from typing import Literal

import pytest

from hgi.hand_landmarks import DetectedHand, HandLandmark, NormalizedLandmark


@dataclass
class FakeClock:
    """Explicit seconds for temporal tests; no sleeping or real clock access."""

    now: float = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def fake_clock() -> FakeClock:
    """Return a separate controllable clock for each test."""
    return FakeClock()


@pytest.fixture
def hand_factory() -> Callable[..., DetectedHand]:
    """Build a palm facing the image, optionally mirrored/scaled/rotated.

    Finger names select extended chains. aspect_ratio encodes a rectangular
    image's normalized coordinates; the recognizer must undo that X scaling.
    """

    def make_hand(
        *extended: str,
        handedness: Literal["Left", "Right"] | None = "Right",
        scale: float = 1.0,
        rotation: float = 0.0,
        aspect_ratio: float = 1.0,
    ) -> DetectedHand:
        coordinates = [(0.5, 0.875)] * len(HandLandmark)
        coordinates[HandLandmark.THUMB_CMC] = (0.4375, 0.75)
        coordinates[HandLandmark.THUMB_MCP] = (0.375, 0.6875)
        if "thumb" in extended:
            coordinates[HandLandmark.THUMB_IP] = (0.3125, 0.625)
            coordinates[HandLandmark.THUMB_TIP] = (0.25, 0.5625)
        else:
            coordinates[HandLandmark.THUMB_IP] = (0.4375, 0.65625)
            coordinates[HandLandmark.THUMB_TIP] = (0.5, 0.6875)
        bases = (
            ("index", HandLandmark.INDEX_FINGER_MCP, 0.375),
            ("middle", HandLandmark.MIDDLE_FINGER_MCP, 0.5),
            ("ring", HandLandmark.RING_FINGER_MCP, 0.625),
            ("pinky", HandLandmark.PINKY_MCP, 0.75),
        )
        for name, base, x in bases:
            ys = (
                (0.625, 0.5, 0.4375, 0.375)
                if name in extended
                else (0.625, 0.5, 0.59375, 0.6875)
            )
            for offset, y in enumerate(ys):
                coordinates[base + offset] = (x, y)
        angle = radians(rotation)
        points = []
        for x, y in coordinates:
            dx = (1 - x if handedness == "Left" else x) - 0.5
            dy = y - 0.875
            points.append(
                NormalizedLandmark(
                    (0.5 + scale * (dx * cos(angle) - dy * sin(angle))) / aspect_ratio,
                    0.875 + scale * (dx * sin(angle) + dy * cos(angle)),
                    0.0,
                )
            )
        return DetectedHand(tuple(points), handedness=handedness)

    return make_hand

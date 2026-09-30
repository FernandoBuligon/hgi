"""Overlay contracts over synthetic frames, without display or pixel snapshots."""

from dataclasses import replace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from hgi.cursor import ControlState, CursorAction, CursorCommand
from hgi.cursor_controller import CursorConfig
from hgi.geometry import Point2D
from hgi.gesture_detector import Gesture, GestureObservation
from hgi.overlay import OverlayState, draw_overlay, overlay_lines
from hgi.temporal import TemporalStatus


def state(hand=None, action=CursorAction.NONE):
    gesture = Gesture.PINCH if action is CursorAction.CLICK else Gesture.POINT
    return OverlayState(
        hand=hand,
        observation=GestureObservation(gesture, Gesture.POINT, 0.18 if hand else None),
        command=CursorCommand(action, 100.0, 200.0, gesture)
        if action is not CursorAction.NONE
        else CursorCommand(action, gesture=gesture),
        control=ControlState.ENABLED,
        position=Point2D(100, 200),
        temporal=TemporalStatus(gesture, gesture, False, True),
        fps=27.4,
    )


@pytest.mark.parametrize("action", list(CursorAction))
@pytest.mark.parametrize("shape", [(480, 640, 3), (240, 320, 3)])
def test_overlay_keeps_bgr_dimensions_and_accepts_actions(hand_factory, shape, action):
    frame = np.zeros(shape, dtype=np.uint8)
    result = draw_overlay(
        frame, state(hand_factory("index"), action), CursorConfig(1920, 1080)
    )
    assert result is frame and result.shape == shape and result.dtype == np.uint8
    assert np.any(result)


def test_missing_hand_and_confidence_are_readable_and_drawable(hand_factory):
    config = CursorConfig(1920, 1080)
    for hand in (None, replace(hand_factory("index"), handedness=None)):
        data = state(hand)
        lines = "\n".join(overlay_lines(data, config))
        assert "Confidence (Left/Right): --" in lines
        assert "DRY-RUN" in lines and "CONTROL: ENABLED" in lines
        assert "RAW: POINT" in lines and "STABLE: POINT" in lines
        draw_overlay(np.zeros((480, 640, 3), np.uint8), data, config)


def test_draws_all_landmarks_highlights_indicator_and_actual_active_region(
    hand_factory, monkeypatch
):
    circle, rectangle = Mock(wraps=cv2.circle), Mock(wraps=cv2.rectangle)
    monkeypatch.setattr(cv2, "circle", circle)
    monkeypatch.setattr(cv2, "rectangle", rectangle)
    frame = np.zeros((120, 160, 3), np.uint8)
    draw_overlay(frame, state(hand_factory("index")), CursorConfig(1920, 1080))
    assert circle.call_count == 22  # 21 landmarks plus the index highlight.
    assert any(
        call.args[1:3] == ((16, 12), (143, 107)) for call in rectangle.call_args_list
    )


def test_labels_explain_virtual_click_temporal_state_and_target(hand_factory):
    hand = replace(hand_factory("index"), handedness_score=0.97)
    lines = "\n".join(
        overlay_lines(state(hand, CursorAction.CLICK), CursorConfig(1920, 1080))
    )
    for label in (
        "Hand: Right",
        "0.97",
        "RAW: PINCH",
        "STABLE: PINCH",
        "candidate: PINCH",
        "Pinch: 0.18",
        "armed: no",
        "cooldown: active",
        "Cursor: 100, 200",
        "Action: CLICK",
        "normalized:",
        "screen target:",
        "FPS: 27.4",
    ):
        assert label in lines


@pytest.mark.parametrize("frame", [np.zeros((2, 2), np.uint8), np.zeros((2, 2, 3))])
def test_invalid_overlay_frame_is_rejected(frame):
    with pytest.raises((TypeError, ValueError)):
        draw_overlay(frame, state(), CursorConfig(1920, 1080))

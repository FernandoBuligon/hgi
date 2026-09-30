"""Camera contracts with a fake OpenCV capture; never open real hardware."""

from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from hgi.camera import Camera, CameraError


@pytest.fixture
def capture(monkeypatch):
    fake = Mock()
    fake.isOpened.return_value = True
    fake.read.return_value = (True, np.zeros((120, 160, 3), dtype=np.uint8))
    monkeypatch.setattr(cv2, "VideoCapture", Mock(return_value=fake))
    return fake


def test_open_requests_resolution_but_read_preserves_actual_dimensions(capture):
    with Camera(2, width=640, height=480) as camera:
        cv2.VideoCapture.assert_called_once_with(2)
        capture.set.assert_any_call(cv2.CAP_PROP_FRAME_WIDTH, 640)
        capture.set.assert_any_call(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        frame = camera.read()
        assert frame is capture.read.return_value[1]
        assert frame.shape == (120, 160, 3)
    capture.release.assert_called_once()


def test_unavailable_camera_releases_and_reports_index(capture):
    capture.isOpened.return_value = False
    with pytest.raises(CameraError, match="2"):
        Camera(2)
    capture.release.assert_called_once()


@pytest.mark.parametrize(
    "result",
    [
        (False, None),
        (True, None),
        (True, np.zeros((0, 2, 3), dtype=np.uint8)),
        (True, np.zeros((2, 2), dtype=np.uint8)),
        (True, np.zeros((2, 2, 4), dtype=np.uint8)),
        (True, np.zeros((2, 2, 3), dtype=np.float32)),
    ],
)
def test_failed_or_invalid_frame_is_explicit_and_context_closes(capture, result):
    capture.read.return_value = result
    with pytest.raises(CameraError, match="frame"):
        with Camera() as camera:
            camera.read()
    capture.release.assert_called_once()


def test_context_releases_on_caller_exception_and_close_is_idempotent(capture):
    with pytest.raises(RuntimeError, match="caller"):
        with Camera() as camera:
            raise RuntimeError("caller")
    camera.close()
    capture.release.assert_called_once()
    with pytest.raises(CameraError, match="closed"):
        camera.read()


def test_native_error_preserves_cause_and_releases_during_setup(capture):
    capture.set.side_effect = cv2.error("native setup")
    with pytest.raises(CameraError) as failure:
        Camera()
    assert isinstance(failure.value.__cause__, cv2.error)
    capture.release.assert_called_once()


def test_native_read_error_closes_and_preserves_cause(capture):
    capture.read.side_effect = cv2.error("native read")
    with pytest.raises(CameraError) as failure:
        with Camera() as camera:
            camera.read()
    assert isinstance(failure.value.__cause__, cv2.error)
    capture.release.assert_called_once()


@pytest.mark.parametrize(
    "options", [{"index": -1}, {"index": True}, {"width": 0}, {"height": 2.5}]
)
def test_invalid_configuration_does_not_open_capture(capture, options):
    with pytest.raises(ValueError):
        Camera(**options)
    cv2.VideoCapture.assert_not_called()


@pytest.mark.parametrize(
    "reported,expected", [(25.0, 25.0), (0.0, None), (float("nan"), None)]
)
def test_reported_fps_is_metadata_not_effective_throughput(
    monkeypatch, reported, expected
):
    capture = Mock()
    capture.isOpened.return_value = True
    capture.get.return_value = reported
    monkeypatch.setattr(cv2, "VideoCapture", Mock(return_value=capture))
    with Camera(1) as camera:
        assert camera.reported_fps == expected
    capture.get.assert_called_once_with(cv2.CAP_PROP_FPS)

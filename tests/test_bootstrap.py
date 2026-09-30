"""Bootstrap checks without camera, display or automation dependencies."""

import subprocess
import sys
from importlib import import_module

import pytest


def test_import_is_quiet_without_hardware_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Importing the package must be quiet and safe in a headless environment."""
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    import_module("hgi.__main__")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import hgi.__main__; "
            "assert not {'cv2', 'mediapipe', 'numpy', 'pyautogui'} "
            "& sys.modules.keys()",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_module_entrypoint_identifies_project() -> None:
    """Running the installed module identifies HGI and exits successfully."""
    result = subprocess.run(
        [sys.executable, "-m", "hgi"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "HGI — Hand Gesture Interface"
    assert result.stderr == ""

"""Exercise benchmark CLI with a fake tracker; never open webcam in pytest."""

import runpy
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import cv2
import pytest

from hgi.tracker_config import InferenceDelegate, RunningMode


def test_benchmark_help_and_missing_model_never_open_camera(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        cv2, "VideoCapture", Mock(side_effect=AssertionError("hardware"))
    )
    main = runpy.run_path("scripts/benchmark_hand_tracker.py")["main"]
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0
    assert "--running-mode" in capsys.readouterr().out
    assert main(["--model", str(tmp_path / "absent.task"), "--camera", "1"]) == 1
    assert "docs/MODELS.md" in capsys.readouterr().err
    cv2.VideoCapture.assert_not_called()
    with pytest.raises(SystemExit):
        main(["--real-control"])


def test_synthetic_benchmark_selects_options_counts_results_and_closes(
    tmp_path, monkeypatch, capsys
):
    import hgi.hand_tracker as tracking

    namespace = runpy.run_path("scripts/benchmark_hand_tracker.py")
    main = namespace["main"]
    counter = iter(i * 0.001 for i in range(1000))
    main.__globals__["perf_counter"] = lambda: next(counter)
    tracker = SimpleNamespace(
        process=Mock(return_value=()),
        config=SimpleNamespace(running_mode=RunningMode.VIDEO),
    )
    resource = MagicMock()
    resource.__enter__.return_value = tracker
    factory = Mock(return_value=resource)
    monkeypatch.setattr(tracking, "HandTracker", factory)
    monkeypatch.setattr(
        cv2, "VideoCapture", Mock(side_effect=AssertionError("hardware"))
    )
    path = tmp_path / "fake.task"
    path.touch()
    assert (
        main(
            [
                "--model",
                str(path),
                "--duration",
                "0.02",
                "--warmup",
                "0",
                "--delegate",
                "gpu",
                "--running-mode",
                "video",
                "--json",
            ]
        )
        == 0
    )
    config = factory.call_args.kwargs["config"]
    assert (
        config.running_mode is RunningMode.VIDEO
        and config.delegate is InferenceDelegate.GPU
    )
    assert tracker.process.call_count > 0
    assert '"frames_with_hands": 0' in capsys.readouterr().out
    resource.__exit__.assert_called_once()
    cv2.VideoCapture.assert_not_called()

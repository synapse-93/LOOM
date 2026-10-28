"""CLI exposure tests for backend selection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loom.__main__ import main


def _create_mock_artifacts() -> MagicMock:
    mock = MagicMock()
    mock.video_artifact.resolution = (1920, 1080)
    mock.video_artifact.fps = 30.0
    mock.video_artifact.duration_seconds = 10.0
    mock.video_artifact.frame_count = 300
    mock.frame_set_artifact.frame_paths = [Path("f1.jpg")]
    mock.capture_analysis_artifact.selected_frames = [Path("f1.jpg")]
    mock.capture_analysis_artifact.rejected_frames = []
    mock.capture_analysis_artifact.average_sharpness = 120.0
    mock.capture_analysis_artifact.coverage_score = 0.85
    mock.capture_analysis_artifact.guidance_notes = []
    mock.run_id = "test_run"
    mock.selected_frames_dir = Path("frames/selected")
    mock.capture_report_path = Path("reports/capture.json")
    mock.metadata_report_path = Path("reports/metadata.json")
    mock.reconstruction_result = None
    mock.mesh_processing_result = None
    return mock


def test_help_exposes_backend_and_generic_binary_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--reconstruction-backend" in help_text
    assert "--reconstruction-binary" in help_text
    assert "--meshroom-path" in help_text


def test_cli_sets_reconstruction_backend_and_binary() -> None:
    with patch("loom.__main__.run_phase1_pipeline", return_value=_create_mock_artifacts()) as mock_pipeline:
        code = main([
            "--video", "dummy.mp4",
            "--reconstruction-backend", "colmap",
            "--reconstruction-binary", "custom_colmap.exe",
        ])
        assert code == 0
        mock_pipeline.assert_called_once()
        cfg = mock_pipeline.call_args[1]["config"]
        assert cfg.reconstruction.backend == "colmap"
        assert cfg.reconstruction.binary_path == Path("custom_colmap.exe")


def test_cli_supports_meshroom_path_backward_compatible_alias() -> None:
    with patch("loom.__main__.run_phase1_pipeline", return_value=_create_mock_artifacts()) as mock_pipeline:
        code = main([
            "--video", "dummy.mp4",
            "--reconstruction-backend", "meshroom",
            "--meshroom-path", "custom_meshroom.exe",
        ])
        assert code == 0
        mock_pipeline.assert_called_once()
        cfg = mock_pipeline.call_args[1]["config"]
        assert cfg.reconstruction.backend == "meshroom"
        assert cfg.reconstruction.binary_path == Path("custom_meshroom.exe")


def test_cli_log_level_case_insensitive() -> None:
    with patch("loom.__main__.run_phase1_pipeline", return_value=_create_mock_artifacts()):
        with patch("loom.__main__.setup_logging") as mock_setup_log:
            code = main(["--video", "dummy.mp4", "--log-level", "debug"])
            assert code == 0
            mock_setup_log.assert_called_with(level="DEBUG")


def test_cli_log_level_invalid_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--log-level", "notareallevel"])
    assert exc.value.code == 2

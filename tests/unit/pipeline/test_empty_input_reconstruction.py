"""Test zero-selected-frames guard in pipeline runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from loom.config.models import LoomConfig
from loom.pipeline.artifacts import FrameSetArtifact, VideoArtifact, CaptureAnalysisArtifact
from loom.pipeline.runner import run_phase1_pipeline
from loom.reconstruction.models import ReconstructionStatus


def test_zero_selected_frames_skips_reconstruction_cleanly(tmp_path: Path) -> None:
    # Setup dummy video and output dir
    video_path = tmp_path / "dummy.mp4"
    video_path.write_bytes(b"dummy-video-content")

    output_dir = tmp_path / "outputs"
    output_dir.mkdir()

    cfg = LoomConfig()
    cfg.reconstruction.backend = "colmap"
    cfg.output_dir = output_dir

    with patch("loom.video.ingest.VideoIngestor.ingest") as mock_ingest, \
         patch("loom.video.frames.FrameExtractor.extract") as mock_extract, \
         patch("loom.capture.quality.FrameQualityAssessor.assess_and_filter") as mock_filter, \
         patch("loom.reconstruction.runner.ReconstructionRunner.get_engine") as mock_get_engine:

        mock_ingest.return_value = VideoArtifact(
            stage_name="ingest",
            duration_seconds=1.0,
            frame_count=5,
            fps=30.0,
            resolution=(1920, 1080),
            metadata={"file_size_bytes": 1000, "codec": "h264"},
        )

        mock_extract.return_value = FrameSetArtifact(
            stage_name="frames",
            frames_dir=tmp_path / "raw",
            frame_paths=[tmp_path / f"frame_{i}.jpg" for i in range(5)],
            total_extracted=5,
        )

        mock_analysis = CaptureAnalysisArtifact(
            stage_name="capture_quality",
            selected_frames=[],
            rejected_frames=[],
            average_sharpness=10.0,
            coverage_score=0.0,
            guidance_notes=["Severe blur detected"],
            metadata={"selected_count": 0, "rejected_count": 5},
        )
        mock_filter.return_value = (mock_analysis, [])

        # Run pipeline with reconstruct=True
        artifacts = run_phase1_pipeline(
            video_path=video_path,
            config=cfg,
            reconstruct=True,
            clean_mesh=False,
        )

        # Ensure reconstruction engine was never instantiated or invoked
        mock_get_engine.assert_not_called()

        # Verify reconstruction artifact status
        recon_art = artifacts.reconstruction_result
        assert recon_art is not None
        assert recon_art.status == ReconstructionStatus.INVALID_INPUT
        assert recon_art.success is False
        assert "0 frames selected by quality filter" in (recon_art.error_message or "")
        assert "Recapturing" in (recon_art.error_message or "")

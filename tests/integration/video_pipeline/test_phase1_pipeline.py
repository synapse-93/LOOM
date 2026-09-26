"""Integration tests for Phase 1 end-to-end video ingest and capture quality pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from loom.config.models import LoomConfig, VideoConfig, CaptureConfig
from loom.pipeline.runner import run_phase1_pipeline
from loom.reconstruction.models import ReconstructionResult, ReconstructionStatus


def test_phase1_pipeline_end_to_end(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify complete Phase 1 pipeline execution on synthetic video.

    Pipeline flow:
    synthetic video
        ↓
    VideoIngestor
        ↓
    metadata extraction
        ↓
    FrameExtractor (streaming)
        ↓
    quality analysis (sharpness, brightness, contrast, blur, redundancy)
        ↓
    selected frames
        ↓
    CaptureAnalysisArtifact
        ↓
    JSON reports + log verification
    """
    output_root = tmp_path / "loom_outputs"
    config = LoomConfig(
        output_dir=output_root,
        video=VideoConfig(sample_interval=1, max_frames=50),
        capture=CaptureConfig(sharpness_threshold=50.0, redundancy_threshold=0.98),
    )

    result = run_phase1_pipeline(synthetic_video_path, config)

    assert result.run_dir.is_dir()
    assert result.metadata_report_path.is_file()
    assert result.capture_report_path.is_file()

    # 1. Output directory layout verification
    raw_frames_dir = result.run_dir / "frames" / "raw"
    selected_frames_dir = result.run_dir / "frames" / "selected"
    reports_dir = result.run_dir / "reports"
    logs_dir = result.run_dir / "logs"

    assert raw_frames_dir.is_dir()
    assert selected_frames_dir.is_dir()
    assert reports_dir.is_dir()
    assert logs_dir.is_dir()

    # 2. Raw and selected frames
    raw_files = list(raw_frames_dir.glob("frame_*.jpg"))
    assert len(raw_files) == 30  # synthetic video has 30 frames
    assert (raw_frames_dir / "manifest.json").is_file()

    selected_files = list(selected_frames_dir.glob("frame_*.jpg"))
    assert len(selected_files) > 0
    assert len(selected_files) <= len(raw_files)
    assert len(result.capture_analysis_artifact.selected_frames) == len(selected_files)

    # 3. Metadata report
    metadata_json_path = reports_dir / "metadata.json"
    assert metadata_json_path.is_file()
    with open(metadata_json_path, "r", encoding="utf-8") as f:
        meta_data = json.load(f)

    assert meta_data["frame_count"] == 30
    assert meta_data["width"] == 320
    assert meta_data["height"] == 240
    assert meta_data["fps"] == 15.0

    # 4. Capture analysis report
    analysis_json_path = reports_dir / "capture_analysis.json"
    assert analysis_json_path.is_file()
    with open(analysis_json_path, "r", encoding="utf-8") as f:
        analysis_data = json.load(f)

    assert "selected_frames" in analysis_data
    assert "rejected_frames" in analysis_data
    assert "average_sharpness" in analysis_data
    assert "guidance_notes" in analysis_data
    assert "metadata" in analysis_data
    assert analysis_data["metadata"]["selected_count"] == len(selected_files)
    assert analysis_data["metadata"]["rejected_count"] == len(raw_files) - len(selected_files)

    # 5. Pipeline log file
    log_file = logs_dir / "pipeline.log"
    assert log_file.is_file()
    assert log_file.stat().st_size > 0


def test_phase1_pipeline_multiple_runs_do_not_collide(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify sequential pipeline runs produce distinct run directories without overwriting."""
    output_root = tmp_path / "loom_outputs"
    config = LoomConfig(
        output_dir=output_root,
        video=VideoConfig(sample_interval=2, max_frames=10),
    )

    result1 = run_phase1_pipeline(synthetic_video_path, config)
    # Ensure slightly different timestamp if called quickly
    import time
    time.sleep(1.05)
    result2 = run_phase1_pipeline(synthetic_video_path, config)

    assert result1.run_dir != result2.run_dir
    assert result1.run_dir.is_dir()
    assert result2.run_dir.is_dir()


def test_phase1_pipeline_with_reconstruction_unavailable(
    synthetic_video_path: Path, tmp_path: Path
) -> None:
    """Verify that when reconstruct=True is passed but Meshroom is absent, pipeline gracefully reports BINARY_UNAVAILABLE."""
    output_root = tmp_path / "loom_outputs"
    config = LoomConfig(
        output_dir=output_root,
        video=VideoConfig(sample_interval=5, max_frames=5),
    )

    result = run_phase1_pipeline(synthetic_video_path, config, reconstruct=True)

    # Phase 1 completes successfully
    assert result.run_dir.is_dir()
    assert result.metadata_report_path.is_file()
    assert result.capture_report_path.is_file()
    assert len(result.capture_analysis_artifact.selected_frames) > 0

    # Phase 2 result is present and categorized as BINARY_UNAVAILABLE (since Meshroom is not on host)
    assert result.reconstruction_result is not None
    assert result.reconstruction_result.success is False
    assert result.reconstruction_result.status == ReconstructionStatus.BINARY_UNAVAILABLE
    assert result.reconstruction_result.mesh_path is None
    assert "executable not found" in result.reconstruction_result.error_message.lower()

    # reports/reconstruction.json is generated with standardized schema
    assert result.reconstruction_report_path is not None
    assert result.reconstruction_report_path.is_file()

    with open(result.reconstruction_report_path, "r", encoding="utf-8") as rf:
        recon_data = json.load(rf)

    assert recon_data["backend"] == "meshroom"
    assert recon_data["status"] == "binary_unavailable"
    assert recon_data["success"] is False
    assert recon_data["mesh_generated"] is False
    assert recon_data["mesh_path"] is None
    assert recon_data["point_cloud_path"] is None
    assert recon_data["sparse_reconstruction"] is None
    assert "workspace_path" in recon_data
    assert "input_frames" in recon_data
    assert recon_data["input_frames"] == len(result.capture_analysis_artifact.selected_frames)


def test_phase1_pipeline_with_reconstruction_mocked_success(
    synthetic_video_path: Path, tmp_path: Path
) -> None:
    """Verify end-to-end Phase 1 + Phase 2 execution with a mocked successful reconstruction engine."""
    output_root = tmp_path / "loom_outputs"
    config = LoomConfig(
        output_dir=output_root,
        video=VideoConfig(sample_interval=5, max_frames=5),
    )

    mock_mesh_file = tmp_path / "mock_mesh.obj"
    mock_mesh_file.write_text("v 0 0 0\nv 1 1 1\nf 1 2 3\n")
    mock_pc_file = tmp_path / "mock_dense.ply"
    mock_pc_file.write_text("ply format ascii\n")
    mock_sparse_file = tmp_path / "mock_sparse.ply"
    mock_sparse_file.write_text("ply format ascii\n")
    mock_poses_file = tmp_path / "cameras.sfm"
    mock_poses_file.write_text(json.dumps({"views": [1, 2], "poses": [1, 2]}))

    mock_engine = MagicMock()
    mock_engine.is_available.return_value = True
    mock_engine.reconstruct.return_value = ReconstructionResult(
        success=True,
        status=ReconstructionStatus.SUCCESS,
        backend_name="meshroom",
        mesh_path=mock_mesh_file,
        point_cloud_path=mock_pc_file,
        dense_point_cloud_path=mock_pc_file,
        sparse_reconstruction_path=mock_sparse_file,
        camera_poses_path=mock_poses_file,
        registered_cameras_count=2,
        input_frames_count=2,
        registration_ratio=1.0,
        point_count=1500,
        execution_time_seconds=12.5,
    )

    with patch("loom.pipeline.runner.ReconstructionRunner.get_engine", return_value=mock_engine):
        result = run_phase1_pipeline(synthetic_video_path, config, reconstruct=True)

    assert result.reconstruction_result is not None
    assert result.reconstruction_result.success is True
    assert result.reconstruction_result.status == ReconstructionStatus.SUCCESS
    assert result.reconstruction_result.mesh_path == mock_mesh_file

    with open(result.reconstruction_report_path, "r", encoding="utf-8") as rf:
        recon_data = json.load(rf)

    assert recon_data["status"] == "success"
    assert recon_data["success"] is True
    assert recon_data["mesh_generated"] is True
    assert recon_data["mesh_path"] == str(mock_mesh_file)
    assert recon_data["point_cloud_path"] == str(mock_pc_file)
    assert recon_data["dense_point_cloud_path"] == str(mock_pc_file)
    assert recon_data["sparse_reconstruction"] == str(mock_sparse_file)
    assert recon_data["registered_cameras"] == 2
    assert recon_data["registration_ratio"] == 1.0
    assert recon_data["point_count"] == 1500


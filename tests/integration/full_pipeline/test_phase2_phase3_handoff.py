"""Integration tests for Phase 2 -> Phase 3 handoff and failure discrimination."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from loom.config.models import LoomConfig, MeshConfig, VideoConfig
from loom.pipeline.runner import run_phase1_pipeline
from loom.reconstruction.models import ReconstructionResult, ReconstructionStatus
from tests.fixtures.mesh_fixtures import create_photogrammetry_raw_mesh, save_fixture_mesh


def test_phase1_to_phase2_to_phase3_full_success(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify complete video -> reconstruction -> mesh processing pipeline flow.

    Pipeline flow:
    synthetic video
        ↓ (Phase 1)
    selected keyframes
        ↓ (Phase 2 Reconstruction)
    raw photogrammetry mesh
        ↓ (Phase 3 Mesh Processing)
    cleaned intermediate mesh + geometry report
    """
    output_root = tmp_path / "loom_outputs"
    config = LoomConfig(
        output_dir=output_root,
        video=VideoConfig(sample_interval=5, max_frames=5),
        mesh=MeshConfig(close_holes=True, max_hole_edges=30),
    )

    # Generate a realistic raw photogrammetry mesh as the mock reconstruction output
    raw_mesh = create_photogrammetry_raw_mesh(radius=5.0)
    raw_mesh_file = tmp_path / "mock_texturedMesh.obj"
    save_fixture_mesh(raw_mesh, raw_mesh_file)

    mock_pc = tmp_path / "dense.ply"
    mock_pc.write_text("ply format ascii\n")
    mock_sfm = tmp_path / "cameras.sfm"
    mock_sfm.write_text(json.dumps({"views": [1, 2, 3], "poses": [1, 2, 3]}))

    mock_engine = MagicMock()
    mock_engine.is_available.return_value = True
    mock_engine.reconstruct.return_value = ReconstructionResult(
        success=True,
        status=ReconstructionStatus.SUCCESS,
        backend_name="meshroom",
        mesh_path=raw_mesh_file,
        point_cloud_path=mock_pc,
        camera_poses_path=mock_sfm,
        registered_cameras_count=3,
        input_frames_count=3,
        registration_ratio=1.0,
        execution_time_seconds=15.0,
    )

    with patch("loom.pipeline.runner.ReconstructionRunner.get_engine", return_value=mock_engine):
        result = run_phase1_pipeline(
            video_path=synthetic_video_path,
            config=config,
            reconstruct=True,
            clean_mesh=True,
        )

    # 1. Phase 2 verification
    assert result.reconstruction_result is not None
    assert result.reconstruction_result.success is True
    assert result.reconstruction_result.status == ReconstructionStatus.SUCCESS
    assert result.reconstruction_report_path.is_file()

    # 2. Phase 3 handoff verification
    assert result.mesh_processing_result is not None
    assert result.mesh_processing_result.success is True
    assert result.geometry_report_path is not None
    assert result.geometry_report_path.is_file()

    # 3. Cleaned output mesh verification
    cleaned_mesh_path = result.mesh_processing_result.output_mesh_path
    assert cleaned_mesh_path.is_file()
    assert cleaned_mesh_path.stat().st_size > 0
    assert cleaned_mesh_path.name == "cleaned_mock_texturedMesh.obj"

    # 4. Geometry report content verification
    with open(result.geometry_report_path, "r", encoding="utf-8") as f:
        geom_report = json.load(f)

    assert geom_report["success"] is True
    assert geom_report["vertex_count_before"] > geom_report["vertex_count_after"]
    assert geom_report["face_count_before"] > geom_report["face_count_after"]
    assert geom_report["repairs_successful"] >= 1


def test_phase2_process_failure_skips_phase3(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify that when reconstruction fails, Phase 3 is skipped and failure is isolated."""
    output_root = tmp_path / "loom_outputs"
    config = LoomConfig(
        output_dir=output_root,
        video=VideoConfig(sample_interval=5, max_frames=5),
    )

    mock_engine = MagicMock()
    mock_engine.is_available.return_value = True
    mock_engine.reconstruct.return_value = ReconstructionResult(
        success=False,
        status=ReconstructionStatus.PROCESS_FAILED,
        backend_name="meshroom",
        mesh_path=None,
        error_message="Feature matching failed completely",
        input_frames_count=5,
    )

    with patch("loom.pipeline.runner.ReconstructionRunner.get_engine", return_value=mock_engine):
        result = run_phase1_pipeline(
            video_path=synthetic_video_path,
            config=config,
            reconstruct=True,
            clean_mesh=True,
        )

    assert result.reconstruction_result is not None
    assert result.reconstruction_result.success is False
    assert result.reconstruction_result.status == ReconstructionStatus.PROCESS_FAILED
    # Phase 3 was not run because reconstruction produced no mesh
    assert result.mesh_processing_result is None
    assert result.geometry_report_path is None


def test_phase2_success_with_corrupt_mesh_distinguishes_geometry_failure(
    synthetic_video_path: Path, tmp_path: Path
) -> None:
    """Verify that if reconstruction outputs a corrupt mesh, geometry failure is distinguished."""
    output_root = tmp_path / "loom_outputs"
    config = LoomConfig(
        output_dir=output_root,
        video=VideoConfig(sample_interval=5, max_frames=5),
    )

    # Empty / corrupt mesh file
    corrupt_mesh = tmp_path / "corrupt_reconstruction.obj"
    corrupt_mesh.write_text("invalid content not a mesh\n")

    mock_engine = MagicMock()
    mock_engine.is_available.return_value = True
    mock_engine.reconstruct.return_value = ReconstructionResult(
        success=True,
        status=ReconstructionStatus.SUCCESS,
        backend_name="meshroom",
        mesh_path=corrupt_mesh,
        input_frames_count=5,
    )

    with patch("loom.pipeline.runner.ReconstructionRunner.get_engine", return_value=mock_engine):
        result = run_phase1_pipeline(
            video_path=synthetic_video_path,
            config=config,
            reconstruct=True,
            clean_mesh=True,
        )

    # Reconstruction itself succeeded (backend finished and left an artifact)
    assert result.reconstruction_result is not None
    assert result.reconstruction_result.success is True

    # Geometry processing explicitly failed and recorded failure status
    assert result.mesh_processing_result is not None
    assert result.mesh_processing_result.success is False
    assert result.mesh_processing_result.status == "FAILED"
    assert "mesh processing failed" in result.mesh_processing_result.error_message.lower()

    # Geometry report exists and documents the processing failure
    assert result.geometry_report_path.is_file()
    with open(result.geometry_report_path, "r", encoding="utf-8") as gf:
        report_data = json.load(gf)
    assert report_data["success"] is False
    assert "error_message" in report_data

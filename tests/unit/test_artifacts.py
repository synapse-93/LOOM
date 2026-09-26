"""Tests for typed pipeline artifact models."""

from __future__ import annotations

from pathlib import Path
import pytest
from loom.pipeline.artifacts import (
    BaseArtifact,
    ExportArtifact,
    FrameSetArtifact,
    MeshArtifact,
    PointCloudArtifact,
    PrintabilityArtifact,
    ReconstructionArtifact,
    ScaledMeshArtifact,
    ValidationArtifact,
    VideoArtifact,
)


def test_base_artifact_creation() -> None:
    """Verify base artifact immutability and metadata tracking."""
    art = BaseArtifact(stage_name="test_stage", metadata={"source": "test"})
    assert art.stage_name == "test_stage"
    assert art.metadata["source"] == "test"
    assert art.created_at is not None

    with pytest.raises(AttributeError):
        # Artifacts must be immutable (frozen)
        art.stage_name = "new_stage"  # type: ignore[misc]


def test_video_artifact() -> None:
    """Verify VideoArtifact properties."""
    v = VideoArtifact(
        stage_name="video_ingest",
        video_path=Path("data/raw/sample.mp4"),
        duration_seconds=12.5,
        frame_count=375,
        resolution=(1920, 1080),
        fps=30.0,
    )
    assert v.fps == 30.0
    assert v.resolution == (1920, 1080)


def test_mesh_and_scaled_mesh_artifacts() -> None:
    """Verify MeshArtifact and ScaledMeshArtifact properties."""
    m = MeshArtifact(
        stage_name="mesh_processing",
        mesh_path=Path("outputs/meshes/cleaned.obj"),
        vertex_count=5000,
        face_count=10000,
        is_cleaned=True,
    )
    assert m.is_cleaned is True
    assert m.vertex_count == 5000

    s = ScaledMeshArtifact(
        stage_name="scaling",
        mesh_path=Path("outputs/meshes/scaled.obj"),
        scale_factor=1.2345,
        units="mm",
        marker_detected=True,
    )
    assert s.scale_factor == 1.2345
    assert s.units == "mm"

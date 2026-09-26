"""Contract and interface tests for interchangeable reconstruction engine adapters."""

from __future__ import annotations

from pathlib import Path
import pytest
from loom.reconstruction.base import ReconstructionEngine
from loom.reconstruction.colmap import ColmapAdapter
from loom.reconstruction.meshroom import MeshroomAdapter
from loom.reconstruction.models import ReconstructionJobConfig
from loom.reconstruction.runner import ReconstructionRunner


def test_reconstruction_runner_factory() -> None:
    """Verify ReconstructionRunner provides valid instances of configured engines."""
    engine_meshroom = ReconstructionRunner.get_engine("meshroom")
    assert isinstance(engine_meshroom, ReconstructionEngine)
    assert engine_meshroom.backend_name == "meshroom"

    engine_colmap = ReconstructionRunner.get_engine("colmap")
    assert isinstance(engine_colmap, ReconstructionEngine)
    assert engine_colmap.backend_name == "colmap"

    with pytest.raises(ValueError, match="Unknown reconstruction backend"):
        ReconstructionRunner.get_engine("non_existent_engine")


def test_meshroom_adapter_contract(tmp_path: Path) -> None:
    """Verify MeshroomAdapter respects the ReconstructionEngine contract."""
    adapter = MeshroomAdapter()
    assert adapter.backend_name == "meshroom"
    # is_available returns boolean without raising
    is_avail = adapter.is_available()
    assert isinstance(is_avail, bool)

    cfg = ReconstructionJobConfig(workspace_dir=tmp_path / "test_workspace")
    # Empty frame list raises ValueError per Phase 2 validation
    with pytest.raises(ValueError, match="empty list of frames"):
        adapter.reconstruct([], cfg)


def test_colmap_adapter_contract() -> None:
    """Verify ColmapAdapter respects the ReconstructionEngine contract."""
    adapter = ColmapAdapter()
    assert adapter.backend_name == "colmap"
    is_avail = adapter.is_available()
    assert isinstance(is_avail, bool)

    cfg = ReconstructionJobConfig(workspace_dir=Path("outputs/test"))
    with pytest.raises(NotImplementedError):
        adapter.reconstruct([], cfg)


def test_reconstruction_result_contract() -> None:
    """Verify ReconstructionResult contract enforces expected fields, aliases, and zero-hallucination None values."""
    from loom.reconstruction.models import ReconstructionResult, ReconstructionStatus

    # Default result has None for unmeasured values
    res = ReconstructionResult(
        success=False,
        status=ReconstructionStatus.BINARY_UNAVAILABLE,
        backend_name="meshroom",
        input_frames_count=15,
        error_message="Executable not found",
    )

    assert res.success is False
    assert res.status == ReconstructionStatus.BINARY_UNAVAILABLE
    assert res.backend == "meshroom"
    assert res.backend_name == "meshroom"
    assert res.input_frames_count == 15
    assert res.input_frame_count == 15
    assert res.registered_cameras_count is None
    assert res.registered_camera_count is None
    assert res.registration_ratio is None
    assert res.point_count is None
    assert res.mesh_path is None
    assert res.raw_mesh_path is None
    assert res.sparse_reconstruction_path is None
    assert res.dense_point_cloud_path is None
    assert res.point_cloud_path is None
    assert res.camera_poses_path is None
    assert res.workspace_path is None
    assert res.log_path is None
    assert res.execution_time_seconds == 0.0
    assert res.error_message == "Executable not found"


def test_reconstruction_status_enumeration() -> None:
    """Verify all 7 distinct failure and completion classifications exist."""
    from loom.reconstruction.models import ReconstructionStatus

    expected = {
        "success",
        "partial",
        "binary_unavailable",
        "invalid_input",
        "process_failed",
        "timeout",
        "artifact_missing",
    }
    actual = {s.value for s in ReconstructionStatus}
    assert actual == expected


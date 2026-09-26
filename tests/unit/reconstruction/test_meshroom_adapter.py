"""Unit tests for Meshroom reconstruction adapter with mocked subprocess execution."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from loom.reconstruction.exceptions import (
    ReconstructionArtifactNotFoundError,
    ReconstructionBinaryNotFoundError,
    ReconstructionExecutionError,
    ReconstructionInvalidInputError,
    ReconstructionPartialError,
    ReconstructionTimeoutError,
)
from loom.reconstruction.meshroom import DiscoveredArtifacts, MeshroomAdapter
from loom.reconstruction.models import (
    ReconstructionJobConfig,
    ReconstructionResult,
    ReconstructionStage,
    ReconstructionStatus,
)
from loom.reconstruction.runner import ReconstructionRunner


@pytest.fixture
def dummy_frames(tmp_path: Path) -> list[Path]:
    """Create a set of dummy image files for testing."""
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(3):
        f = frame_dir / f"frame_{i:04d}.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nfakeimagebytes")
        frames.append(f)
    return frames


@pytest.fixture
def dummy_binary(tmp_path: Path) -> Path:
    """Create a dummy executable file."""
    bin_path = tmp_path / "meshroom_batch.exe"
    bin_path.write_text("#!/bin/sh\nexit 0\n")
    return bin_path


def test_meshroom_adapter_init() -> None:
    """Verify default initialization."""
    adapter = MeshroomAdapter()
    assert adapter.backend_name == "meshroom"
    assert adapter.binary_path is None


def test_binary_missing_raises_error(tmp_path: Path, dummy_frames: list[Path]) -> None:
    """Verify that a missing binary raises ReconstructionBinaryNotFoundError."""
    non_existent = tmp_path / "does_not_exist" / "meshroom_batch.exe"
    adapter = MeshroomAdapter(binary_path=non_existent)
    assert not adapter.is_available()

    job_cfg = ReconstructionJobConfig(
        workspace_dir=tmp_path / "workspace",
        binary_path=non_existent,
    )
    with pytest.raises(ReconstructionBinaryNotFoundError, match="Meshroom executable .* not found"):
        adapter.reconstruct(dummy_frames, job_cfg)


def test_zero_input_frames_raises_error(tmp_path: Path, dummy_binary: Path) -> None:
    """Verify that an empty list of frames raises ValueError."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    job_cfg = ReconstructionJobConfig(
        workspace_dir=tmp_path / "workspace",
        binary_path=dummy_binary,
    )
    with pytest.raises(ValueError, match="empty list of frames"):
        adapter.reconstruct([], job_cfg)


def test_nonexistent_input_frame_raises_error(tmp_path: Path, dummy_binary: Path) -> None:
    """Verify that referencing non-existent frame files raises FileNotFoundError."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    job_cfg = ReconstructionJobConfig(
        workspace_dir=tmp_path / "workspace",
        binary_path=dummy_binary,
    )
    fake_frame = tmp_path / "ghost_frame.png"
    with pytest.raises(FileNotFoundError, match="Input frame does not exist"):
        adapter.reconstruct([fake_frame], job_cfg)


def test_command_construction(tmp_path: Path, dummy_binary: Path) -> None:
    """Verify CLI argument construction conforms to Meshroom specifications."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    in_dir = tmp_path / "input"
    out_dir = tmp_path / "output"
    cache_dir = tmp_path / "cache"

    cfg = ReconstructionJobConfig(
        workspace_dir=out_dir,
        additional_args=["--overrides", "param=val"],
    )

    cmd = adapter.build_command(
        binary_path=dummy_binary,
        input_dir=in_dir,
        output_dir=out_dir,
        cache_dir=cache_dir,
        config=cfg,
    )
    assert cmd[0] == str(dummy_binary)
    assert "--input" in cmd
    assert cmd[cmd.index("--input") + 1] == str(in_dir.resolve())
    assert "--output" in cmd
    assert cmd[cmd.index("--output") + 1] == str(out_dir.resolve())
    assert "--cache" in cmd
    assert cmd[cmd.index("--cache") + 1] == str(cache_dir.resolve())
    assert "--overrides" in cmd
    assert "param=val" in cmd


def test_parse_camera_sfm_valid(tmp_path: Path) -> None:
    """Verify parsing valid AliceVision cameras.sfm JSON."""
    sfm_data = {
        "views": [{"viewId": "1"}, {"viewId": "2"}, {"viewId": "3"}, {"viewId": "4"}],
        "poses": [{"poseId": "1"}, {"poseId": "2"}, {"poseId": "3"}],
    }
    sfm_file = tmp_path / "cameras.sfm"
    sfm_file.write_text(json.dumps(sfm_data))

    poses, ratio = MeshroomAdapter.parse_camera_sfm(sfm_file)
    assert poses == 3
    assert ratio == 0.75


def test_parse_camera_sfm_missing_or_corrupt(tmp_path: Path) -> None:
    """Verify parsing non-existent or corrupt SFM file returns None tuple."""
    p, r = MeshroomAdapter.parse_camera_sfm(tmp_path / "nonexistent.sfm")
    assert p is None
    assert r is None

    bad_file = tmp_path / "corrupt.sfm"
    bad_file.write_text("not json content")
    p, r = MeshroomAdapter.parse_camera_sfm(bad_file)
    assert p is None
    assert r is None


def test_discover_output_artifacts(tmp_path: Path) -> None:
    """Verify artifact discovery identifies mesh, point cloud, and camera sfm."""
    out_dir = tmp_path / "mesh_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Empty directory
    mesh, pc, sfm = MeshroomAdapter.discover_output_artifacts(out_dir)
    assert mesh is None
    assert pc is None
    assert sfm is None

    # Populate artifacts
    mesh_file = out_dir / "texturedMesh.obj"
    mesh_file.write_text("v 0 0 0\n")
    cloud_file = out_dir / "cloud_and_poses.ply"
    cloud_file.write_text("ply\n")
    sfm_file = out_dir / "cameras.sfm"
    sfm_file.write_text("{}")

    mesh, pc, sfm = MeshroomAdapter.discover_output_artifacts(out_dir)
    assert mesh == mesh_file.resolve()
    assert pc == cloud_file.resolve()
    assert sfm == sfm_file.resolve()


def test_successful_reconstruction_mocked(tmp_path: Path, dummy_frames: list[Path], dummy_binary: Path) -> None:
    """Verify end-to-end execution flow with mocked subprocess generating output artifacts."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    ws_dir = tmp_path / "recon_run"
    job_cfg = ReconstructionJobConfig(
        workspace_dir=ws_dir,
        binary_path=dummy_binary,
    )

    def fake_popen(*args, **kwargs):
        # Create output artifacts in workspace/output
        out_dir = ws_dir / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "texturedMesh.obj").write_text("v 0 0 0\nv 1 1 1\nf 1 2 3\n")
        (out_dir / "cloud_and_poses.ply").write_text("ply format ascii\n")
        sfm_content = {
            "views": [{"viewId": "1"}, {"viewId": "2"}, {"viewId": "3"}],
            "poses": [{"poseId": "1"}, {"poseId": "2"}],
        }
        (out_dir / "cameras.sfm").write_text(json.dumps(sfm_content))

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            "[AliceVision] CameraInit successful\n[AliceVision] Meshing completed\n",
            "",
        )
        mock_proc.returncode = 0
        return mock_proc

    with patch("subprocess.Popen", side_effect=fake_popen):
        result = adapter.reconstruct(dummy_frames, job_cfg)

    assert result.success is True
    assert result.backend == "meshroom"
    assert result.mesh_path is not None
    assert result.mesh_path.name == "texturedMesh.obj"
    assert result.point_cloud_path is not None
    assert result.registered_cameras_count == 2
    assert result.input_frames_count == 3
    assert result.registration_ratio == pytest.approx(2 / 3, abs=0.01)
    assert result.execution_time_seconds >= 0

    log_path = ws_dir / "logs" / "reconstruction.log"
    assert log_path.is_file()
    assert "[AliceVision] Meshing completed" in log_path.read_text()


def test_subprocess_nonzero_exit_raises_execution_error(
    tmp_path: Path, dummy_frames: list[Path], dummy_binary: Path
) -> None:
    """Verify that a non-zero exit code raises ReconstructionExecutionError."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    ws_dir = tmp_path / "recon_fail"
    job_cfg = ReconstructionJobConfig(workspace_dir=ws_dir, binary_path=dummy_binary)

    def fake_fail_popen(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("FATAL: Could not match features\n", "")
        mock_proc.returncode = 1
        return mock_proc

    with patch("subprocess.Popen", side_effect=fake_fail_popen):
        with pytest.raises(ReconstructionExecutionError, match="Meshroom exited with non-zero return code 1"):
            adapter.reconstruct(dummy_frames, job_cfg)


def test_subprocess_timeout_raises_execution_error(
    tmp_path: Path, dummy_frames: list[Path], dummy_binary: Path
) -> None:
    """Verify that subprocess timeout raises ReconstructionExecutionError."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    ws_dir = tmp_path / "recon_timeout"
    job_cfg = ReconstructionJobConfig(
        workspace_dir=ws_dir,
        binary_path=dummy_binary,
        timeout_seconds=1,
    )

    def fake_timeout_popen(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd=["meshroom_batch"], timeout=1)
        mock_proc.kill.return_value = None
        return mock_proc

    with patch("subprocess.Popen", side_effect=fake_timeout_popen):
        with pytest.raises(ReconstructionExecutionError, match="Meshroom reconstruction timed out"):
            adapter.reconstruct(dummy_frames, job_cfg)


def test_missing_mesh_output_reports_failure(
    tmp_path: Path, dummy_frames: list[Path], dummy_binary: Path
) -> None:
    """Verify that if subprocess exits with 0 but no mesh is found, success is False."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    ws_dir = tmp_path / "recon_no_mesh"
    job_cfg = ReconstructionJobConfig(workspace_dir=ws_dir, binary_path=dummy_binary)

    def fake_no_mesh_popen(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("Finished without error\n", "")
        mock_proc.returncode = 0
        return mock_proc

    with patch("subprocess.Popen", side_effect=fake_no_mesh_popen):
        result = adapter.reconstruct(dummy_frames, job_cfg)

    assert result.success is False
    assert result.mesh_path is None
    assert result.error_message is not None
    assert "no non-empty 3d mesh" in result.error_message.lower()


def test_reconstruction_runner_unsupported_backend() -> None:
    """Verify ReconstructionRunner raises descriptive ValueError for unsupported backend."""
    with pytest.raises(ValueError, match="Unknown reconstruction backend 'gaussian_splatting'"):
        ReconstructionRunner.get_engine("gaussian_splatting")


def test_partial_reconstruction_mocked(
    tmp_path: Path, dummy_frames: list[Path], dummy_binary: Path
) -> None:
    """Verify that when point cloud and SFM are generated but mesh is missing, status is PARTIAL."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    ws_dir = tmp_path / "recon_partial"
    job_cfg = ReconstructionJobConfig(workspace_dir=ws_dir, binary_path=dummy_binary)

    def fake_partial_popen(*args, **kwargs):
        out_dir = ws_dir / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        # Point cloud and SFM exist, but texturedMesh.obj does NOT
        (out_dir / "cloud_and_poses.ply").write_text("ply format ascii\n")
        sfm_content = {
            "views": [{"viewId": "1"}, {"viewId": "2"}, {"viewId": "3"}],
            "poses": [{"poseId": "1"}, {"poseId": "2"}],
        }
        (out_dir / "cameras.sfm").write_text(json.dumps(sfm_content))

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("[AliceVision] SfM succeeded, Meshing aborted\n", "")
        mock_proc.returncode = 0
        return mock_proc

    with patch("subprocess.Popen", side_effect=fake_partial_popen):
        result = adapter.reconstruct(dummy_frames, job_cfg)

    assert result.success is False
    assert result.status == ReconstructionStatus.PARTIAL
    assert result.mesh_path is None
    assert result.point_cloud_path is not None
    assert result.sparse_reconstruction_path is not None
    assert result.camera_poses_path is not None
    assert result.registered_cameras_count == 2
    assert result.registration_ratio == pytest.approx(2 / 3, abs=0.01)
    assert result.log_path is not None
    assert result.log_path.is_file()
    assert "SfM succeeded" in result.log_path.read_text()


def test_artifact_missing_reconstruction_mocked(
    tmp_path: Path, dummy_frames: list[Path], dummy_binary: Path
) -> None:
    """Verify that when process succeeds but zero artifacts are produced, status is ARTIFACT_MISSING."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    ws_dir = tmp_path / "recon_empty"
    job_cfg = ReconstructionJobConfig(workspace_dir=ws_dir, binary_path=dummy_binary)

    def fake_empty_popen(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("No outputs produced\n", "")
        mock_proc.returncode = 0
        return mock_proc

    with patch("subprocess.Popen", side_effect=fake_empty_popen):
        result = adapter.reconstruct(dummy_frames, job_cfg)

    assert result.success is False
    assert result.status == ReconstructionStatus.ARTIFACT_MISSING
    assert result.mesh_path is None
    assert result.point_cloud_path is None
    assert result.sparse_reconstruction_path is None
    assert result.dense_point_cloud_path is None


def test_subprocess_timeout_raises_timeout_error_type(
    tmp_path: Path, dummy_frames: list[Path], dummy_binary: Path
) -> None:
    """Verify that subprocess timeout raises ReconstructionTimeoutError (subclass of ReconstructionExecutionError)."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    ws_dir = tmp_path / "recon_timeout_subclass"
    job_cfg = ReconstructionJobConfig(workspace_dir=ws_dir, binary_path=dummy_binary, timeout_seconds=1)

    def fake_timeout(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd=["meshroom_batch"], timeout=1)
        mock_proc.kill.return_value = None
        return mock_proc

    with patch("subprocess.Popen", side_effect=fake_timeout):
        with pytest.raises(ReconstructionTimeoutError) as exc_info:
            adapter.reconstruct(dummy_frames, job_cfg)
        assert isinstance(exc_info.value, ReconstructionExecutionError)
        assert "timed out after 1 seconds" in str(exc_info.value)


def test_invalid_input_error_types(tmp_path: Path, dummy_binary: Path) -> None:
    """Verify that ReconstructionInvalidInputError is raised for invalid frame lists."""
    adapter = MeshroomAdapter(binary_path=dummy_binary)
    job_cfg = ReconstructionJobConfig(workspace_dir=tmp_path / "ws", binary_path=dummy_binary)

    with pytest.raises(ReconstructionInvalidInputError) as exc_info:
        adapter.reconstruct([], job_cfg)
    assert isinstance(exc_info.value, ValueError)
    assert "empty list of frames" in str(exc_info.value)

    fake_file = tmp_path / "missing_frame.jpg"
    with pytest.raises(ReconstructionInvalidInputError) as exc_info2:
        adapter.reconstruct([fake_file], job_cfg)
    assert isinstance(exc_info2.value, FileNotFoundError)


def test_discovered_artifacts_model_properties(tmp_path: Path) -> None:
    """Verify DiscoveredArtifacts sequence unpacking, dictionary indexing, and dense/sparse separation."""
    out_dir = tmp_path / "artifacts_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    mesh_file = out_dir / "texturedMesh.obj"
    mesh_file.write_text("v 0 0 0\n")
    dense_pc = out_dir / "densePointCloud.ply"
    dense_pc.write_text("ply\n")
    sparse_pc = out_dir / "cloud_and_poses.ply"
    sparse_pc.write_text("ply\n")
    sfm_file = out_dir / "cameras.sfm"
    sfm_file.write_text("{}")

    discovered = MeshroomAdapter.discover_output_artifacts(out_dir)

    # 1. Backward-compatible 3-tuple unpacking
    mesh, pc, sfm = discovered
    assert mesh == mesh_file.resolve()
    assert pc == dense_pc.resolve()  # dense takes priority for primary point_cloud_path
    assert sfm == sfm_file.resolve()

    # 2. Explicit dense and sparse paths
    assert discovered.dense_point_cloud_path == dense_pc.resolve()
    assert discovered.sparse_reconstruction_path == sparse_pc.resolve()
    assert discovered.mesh_path == mesh_file.resolve()
    assert discovered.camera_poses_path == sfm_file.resolve()

    # 3. Index and key access
    assert discovered[0] == mesh_file.resolve()
    assert discovered["mesh_path"] == mesh_file.resolve()
    assert discovered["dense_point_cloud_path"] == dense_pc.resolve()


def test_reconstruction_stage_sequence() -> None:
    """Verify conceptual ReconstructionStage progression is properly ordered."""
    stages = list(ReconstructionStage)
    assert len(stages) == 8
    assert stages[0] == ReconstructionStage.STAGE_0_INPUT_VALIDATION
    assert stages[1] == ReconstructionStage.STAGE_1_CAMERA_INIT
    assert stages[2] == ReconstructionStage.STAGE_2_CAMERA_REGISTRATION
    assert stages[3] == ReconstructionStage.STAGE_3_SPARSE_RECONSTRUCTION
    assert stages[4] == ReconstructionStage.STAGE_4_DENSE_RECONSTRUCTION
    assert stages[5] == ReconstructionStage.STAGE_5_MESH_GENERATION
    assert stages[6] == ReconstructionStage.STAGE_6_ARTIFACT_DISCOVERY
    assert stages[7] == ReconstructionStage.STAGE_7_DIAGNOSTICS


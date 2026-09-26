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
)
from loom.reconstruction.meshroom import MeshroomAdapter
from loom.reconstruction.models import ReconstructionJobConfig
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

"""Tests for the COLMAP command-line adapter without requiring COLMAP itself."""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from loom.pipeline.runner import run_phase1_pipeline
from loom.config.models import LoomConfig
from loom.reconstruction.colmap import ColmapAdapter
from loom.reconstruction.exceptions import (
    ReconstructionArtifactNotFoundError,
    ReconstructionBinaryNotFoundError,
    ReconstructionExecutionError,
    ReconstructionInvalidInputError,
)
from loom.reconstruction.models import ReconstructionJobConfig, ReconstructionStatus


@pytest.fixture
def frames(tmp_path: Path) -> list[Path]:
    paths = []
    for index in range(3):
        path = tmp_path / f"frame_{index}.jpg"
        path.write_bytes(b"image-placeholder")
        paths.append(path)
    return paths


@pytest.fixture
def executable(tmp_path: Path) -> Path:
    path = tmp_path / "colmap.exe"
    path.write_text("placeholder")
    return path


def test_resolve_binary_accepts_explicit_executable(tmp_path: Path, executable: Path) -> None:
    adapter = ColmapAdapter()
    assert adapter.resolve_binary(executable) == executable.resolve()
    assert adapter.resolve_binary(tmp_path / "missing-colmap.exe") is None


def test_resolve_binary_accepts_bin_subdirectory(tmp_path: Path) -> None:
    install_dir = tmp_path / "COLMAP_Install"
    bin_dir = install_dir / "bin"
    bin_dir.mkdir(parents=True)
    exe = bin_dir / "colmap.exe"
    exe.write_text("dummy")

    adapter = ColmapAdapter(install_dir)
    resolved = adapter.resolve_binary(install_dir)
    assert resolved == exe.resolve()


def test_discover_qt_plugin_path(tmp_path: Path) -> None:
    install_dir = tmp_path / "COLMAP"
    bin_dir = install_dir / "bin"
    bin_dir.mkdir(parents=True)
    exe = bin_dir / "colmap.exe"
    exe.write_text("dummy")

    plugins_dir = install_dir / "plugins" / "platforms"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "qwindows.dll").write_text("fake-plugin")

    discovered = ColmapAdapter.discover_qt_plugin_path(exe)
    assert discovered == plugins_dir.resolve()

    adapter = ColmapAdapter(exe)
    with patch.dict(os.environ, {}, clear=True):
        env = adapter.get_subprocess_env(exe)
        assert env.get("QT_QPA_PLATFORM_PLUGIN_PATH") == str(plugins_dir.resolve())

    # Verify user-supplied QT_QPA_PLATFORM_PLUGIN_PATH is respected
    custom_qt = tmp_path / "custom_qt"
    custom_qt.mkdir()
    with patch.dict(os.environ, {"QT_QPA_PLATFORM_PLUGIN_PATH": str(custom_qt)}):
        env = adapter.get_subprocess_env(exe)
        assert env.get("QT_QPA_PLATFORM_PLUGIN_PATH") == str(custom_qt)


def test_reconstruct_rejects_empty_or_invalid_frames(tmp_path: Path, executable: Path) -> None:
    adapter = ColmapAdapter(executable)
    cfg = ReconstructionJobConfig(workspace_dir=tmp_path / "run", binary_path=executable)
    with pytest.raises(ReconstructionInvalidInputError, match="empty list"):
        adapter.reconstruct([], cfg)
    invalid = tmp_path / "not-an-image.txt"
    invalid.write_text("x")
    with pytest.raises(ReconstructionInvalidInputError, match="Unsupported image format"):
        adapter.reconstruct([invalid], cfg)


def test_missing_binary_is_reported(tmp_path: Path, frames: list[Path]) -> None:
    adapter = ColmapAdapter(tmp_path / "missing-colmap.exe")
    cfg = ReconstructionJobConfig(workspace_dir=tmp_path / "run")
    with pytest.raises(ReconstructionBinaryNotFoundError, match="COLMAP executable"):
        adapter.reconstruct(frames, cfg)


def test_successful_dense_pipeline_discovers_real_artifact_paths(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=True)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable, timeout_seconds=60)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[1] == "mapper":
            model = workspace / "sparse" / "0"
            model.mkdir(parents=True, exist_ok=True)
            (model / "cameras.bin").write_bytes(b"camera")
            (model / "images.bin").write_bytes(b"images")
            (model / "points3D.bin").write_bytes(b"points")
        elif command[1] == "image_undistorter":
            (workspace / "dense" / "images").mkdir(parents=True, exist_ok=True)
        elif command[1] == "stereo_fusion":
            (workspace / "dense" / "fused.ply").write_text("ply\nend_header\n")
        elif command[1] == "poisson_mesher":
            (workspace / "dense" / "meshed-poisson.ply").write_text("ply\nend_header\n")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        result = adapter.reconstruct(frames, cfg)

    assert result.success is True
    assert result.status == ReconstructionStatus.SUCCESS
    assert result.backend_name == "colmap"
    assert result.input_frames_count == 3
    assert result.mesh_path == (workspace / "dense" / "meshed-poisson.ply").resolve()
    assert result.dense_point_cloud_path == (workspace / "dense" / "fused.ply").resolve()
    assert len(commands) == 7
    assert (workspace / "logs" / "reconstruction.log").is_file()


def test_successful_cpu_pipeline_discovers_sparse_artifacts(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable, timeout_seconds=60)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[1] == "mapper":
            model = workspace / "sparse" / "0"
            model.mkdir(parents=True, exist_ok=True)
            (model / "cameras.bin").write_bytes(b"camera")
            (model / "images.bin").write_bytes(b"images")
            (model / "points3D.bin").write_bytes(b"points")
        elif command[1] == "model_converter":
            (workspace / "sparse" / "points.ply").write_text(
                "ply\nformat ascii 1.0\nelement vertex 42\nproperty float x\nproperty float y\nproperty float z\nend_header\n"
            )
        elif command[1] == "delaunay_mesher":
            (workspace / "sparse" / "mesh.ply").write_text(
                "ply\nformat ascii 1.0\nelement vertex 42\nproperty float x\nproperty float y\nproperty float z\nelement face 80\nproperty list uchar int vertex_index\nend_header\n"
            )
        return subprocess.CompletedProcess(command, 0, stdout="Reconstruction with 3 images and 42 points", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        result = adapter.reconstruct(frames, cfg)

    assert result.success is True
    assert result.status == ReconstructionStatus.SUCCESS
    assert result.backend_name == "colmap"
    assert result.input_frames_count == 3
    assert result.dense_point_cloud_path is None
    assert result.point_cloud_path == (workspace / "sparse" / "points.ply").resolve()
    assert result.mesh_path == (workspace / "sparse" / "mesh.ply").resolve()
    assert result.point_count == 42
    assert result.registered_cameras_count == 3
    assert result.registration_ratio == 1.0
    # Expected stages: feature_extractor, exhaustive_matcher, mapper, model_converter, delaunay_mesher
    assert len(commands) == 5
    assert "--FeatureExtraction.use_gpu" in commands[0]
    assert "--FeatureMatching.use_gpu" in commands[1]


def test_dense_mvs_failure_falls_back_to_sparse(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=True)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable, timeout_seconds=60)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[1] == "mapper":
            model = workspace / "sparse" / "0"
            model.mkdir(parents=True, exist_ok=True)
            (model / "cameras.bin").write_bytes(b"camera")
            (model / "images.bin").write_bytes(b"images")
            (model / "points3D.bin").write_bytes(b"points")
        elif command[1] == "patch_match_stereo":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="CUDA out of memory")
        elif command[1] == "model_converter":
            (workspace / "sparse" / "points.ply").write_text("ply\nelement vertex 10\nend_header\n")
        elif command[1] == "delaunay_mesher":
            (workspace / "sparse" / "mesh.ply").write_text(
                "ply\nelement vertex 10\nelement face 15\nend_header\n"
            )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        result = adapter.reconstruct(frames, cfg)

    assert result.success is True
    assert result.status == ReconstructionStatus.PARTIAL
    assert result.dense_point_cloud_path is None
    assert result.mesh_path == (workspace / "sparse" / "mesh.ply").resolve()
    assert result.point_cloud_path == (workspace / "sparse" / "points.ply").resolve()
    assert "CUDA out of memory" in (result.error_message or "")


def test_matcher_silent_failure_retries_with_cpu(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=True)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[1] == "exhaustive_matcher" and "--FeatureMatching.use_gpu" not in command:
            # GPU matcher exits 0 but prints error in stderr
            return subprocess.CompletedProcess(
                command, 0, stdout="", stderr="E1028 sift.cc:1392] Not enough GPU memory to match features."
            )
        elif command[1] == "mapper":
            model = workspace / "sparse" / "0"
            model.mkdir(parents=True, exist_ok=True)
            (model / "cameras.bin").write_bytes(b"c")
            (model / "images.bin").write_bytes(b"i")
            (model / "points3D.bin").write_bytes(b"p")
        elif command[1] == "model_converter":
            (workspace / "sparse" / "points.ply").write_text("ply\nelement vertex 5\nend_header\n")
        elif command[1] == "delaunay_mesher":
            (workspace / "sparse" / "mesh.ply").write_text("ply\nelement vertex 5\nelement face 8\nend_header\n")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    # Force CPU fallback in dense by making can_run_dense False on adapter
    adapter._capabilities["can_run_dense"] = False
    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        result = adapter.reconstruct(frames, cfg)

    # Check that retry command was executed with CPU flag
    matcher_calls = [c for c in commands if c[1] == "exhaustive_matcher"]
    assert len(matcher_calls) == 2
    assert "--FeatureMatching.use_gpu" in matcher_calls[1]
    assert matcher_calls[1][matcher_calls[1].index("--FeatureMatching.use_gpu") + 1] == "0"


def test_matcher_zero_matches_in_database_raises_error(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable)

    # Pre-create an empty SQLite database with a matches table having 0 rows
    db_path = workspace / "database.db"
    workspace.mkdir(parents=True, exist_ok=True)

    def fake_run(command, **kwargs):
        if command[1] == "exhaustive_matcher":
            # Create the database.db with empty matches table
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE matches (pair_id INTEGER, rows INTEGER, cols INTEGER, data BLOB)")
                conn.execute("CREATE TABLE two_view_geometries (pair_id INTEGER, rows INTEGER, cols INTEGER, data BLOB)")
                conn.commit()
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        with pytest.raises(ReconstructionExecutionError, match="0 usable matches"):
            adapter.reconstruct(frames, cfg)


def test_invalid_ply_mesh_rejected(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable)

    def fake_run(command, **kwargs):
        if command[1] == "mapper":
            model = workspace / "sparse" / "0"
            model.mkdir(parents=True, exist_ok=True)
            (model / "cameras.bin").write_bytes(b"c")
            (model / "images.bin").write_bytes(b"i")
            (model / "points3D.bin").write_bytes(b"p")
        elif command[1] == "model_converter":
            (workspace / "sparse" / "points.ply").write_text("ply\nelement vertex 5\nend_header\n")
        elif command[1] == "delaunay_mesher":
            # Invalid PLY without vertices
            (workspace / "sparse" / "mesh.ply").write_text("ply\nelement vertex 0\nelement face 0\nend_header\n")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        with pytest.raises(ReconstructionArtifactNotFoundError, match="invalid or has no vertices"):
            adapter.reconstruct(frames, cfg)


def test_nonzero_stage_exit_fails_with_context(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    cfg = ReconstructionJobConfig(workspace_dir=tmp_path / "run", binary_path=executable)
    failure = subprocess.CompletedProcess([str(executable), "feature_extractor"], 2, stdout="", stderr="no GPU")
    with patch("loom.reconstruction.colmap.subprocess.run", return_value=failure):
        with pytest.raises(ReconstructionExecutionError, match="feature_extractor.*exit code 2"):
            adapter.reconstruct(frames, cfg)


def test_successful_commands_without_sparse_model_are_rejected(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        with pytest.raises(ReconstructionArtifactNotFoundError, match="without producing a sparse model"):
            adapter.reconstruct(frames, cfg)


def test_resolve_binary_accepts_directory_containing_colmap_exe(tmp_path: Path) -> None:
    install_dir = tmp_path / "COLMAP_Direct"
    install_dir.mkdir(parents=True)
    exe = install_dir / "colmap.exe"
    exe.write_text("dummy")

    adapter = ColmapAdapter(install_dir)
    resolved = adapter.resolve_binary(install_dir)
    assert resolved == exe.resolve()


def test_resolve_binary_resolves_via_path(tmp_path: Path) -> None:
    target_exe = tmp_path / "colmap.exe"
    target_exe.write_text("dummy")

    adapter = ColmapAdapter("colmap")
    with patch("loom.reconstruction.colmap.shutil.which", return_value=str(target_exe)):
        resolved = adapter.resolve_binary("colmap")
        assert resolved == target_exe.resolve()


def test_dense_mvs_failure_raises_when_fallback_disabled(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=True, allow_fallback=False)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable)

    def fake_run(command, **kwargs):
        if command[1] == "mapper":
            model = workspace / "sparse" / "0"
            model.mkdir(parents=True, exist_ok=True)
            (model / "cameras.bin").write_bytes(b"c")
            (model / "images.bin").write_bytes(b"i")
            (model / "points3D.bin").write_bytes(b"p")
        elif command[1] == "patch_match_stereo":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="CUDA out of memory")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        with pytest.raises(ReconstructionExecutionError, match="fallback is disabled"):
            adapter.reconstruct(frames, cfg)


def test_probe_capabilities_detects_cpu_only_build(executable: Path) -> None:
    adapter = ColmapAdapter(executable)
    proc = subprocess.CompletedProcess(
        [str(executable), "version"], 0, stdout="COLMAP 4.2.1 (Commit bd1fcf6 on 2026-09-29 without GPU support)", stderr=""
    )
    with patch("loom.reconstruction.colmap.subprocess.run", return_value=proc):
        caps = adapter.probe_capabilities(executable)
        assert caps["has_gpu"] is False
        assert caps["can_run_dense"] is False


def test_probe_capabilities_detects_cuda_build(executable: Path) -> None:
    adapter = ColmapAdapter(executable)
    proc = subprocess.CompletedProcess(
        [str(executable), "version"], 0, stdout="COLMAP 4.2.1 (Commit bd1fcf6 with CUDA)", stderr=""
    )
    with patch("loom.reconstruction.colmap.subprocess.run", return_value=proc):
        caps = adapter.probe_capabilities(executable)
        assert caps["has_gpu"] is True
        assert caps["can_run_dense"] is True


def test_mapper_empty_model_dir_rejected(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable)

    def fake_run(command, **kwargs):
        if command[1] == "mapper":
            # Create sparse/0 as an empty directory (no .bin or .txt files)
            model = workspace / "sparse" / "0"
            model.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        with pytest.raises(ReconstructionArtifactNotFoundError, match="without producing a sparse model"):
            adapter.reconstruct(frames, cfg)


def test_colmap_additional_args_routing(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(
        workspace_dir=workspace,
        binary_path=executable,
        additional_args=[
            "--FeatureExtraction.max_num_features", "4096",
            "--FeatureMatching.max_ratio", "0.7",
            "--Mapper.min_num_matches", "15",
            "--DelaunayMeshing.max_proj_dist", "20",
        ],
    )

    recorded_commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        recorded_commands.append(command)
        subcmd = command[1]
        if subcmd == "exhaustive_matcher":
            db = workspace / "database.db"
            with sqlite3.connect(str(db)) as conn:
                conn.execute("CREATE TABLE two_view_geometries (pair_id INTEGER, rows INTEGER)")
                conn.execute("INSERT INTO two_view_geometries VALUES (1, 10)")
                conn.commit()
        elif subcmd == "mapper":
            model = workspace / "sparse" / "0"
            model.mkdir(parents=True, exist_ok=True)
            (model / "cameras.bin").write_bytes(b"c")
            (model / "images.bin").write_bytes(b"i")
            (model / "points3D.bin").write_bytes(b"p")
        elif subcmd == "model_converter":
            (workspace / "sparse" / "points.ply").write_text("ply\nelement vertex 5\nend_header\n")
        elif subcmd == "delaunay_mesher":
            (workspace / "sparse" / "mesh.ply").write_text("ply\nelement vertex 3\nelement face 1\nend_header\n")
        return subprocess.CompletedProcess(command, 0, stdout="Reconstruction with 3 images and 5 points", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        res = adapter.reconstruct(frames, cfg)
        assert res.success is True

    fe_cmd = next(c for c in recorded_commands if c[1] == "feature_extractor")
    fm_cmd = next(c for c in recorded_commands if c[1] == "exhaustive_matcher")
    map_cmd = next(c for c in recorded_commands if c[1] == "mapper")
    dm_cmd = next(c for c in recorded_commands if c[1] == "delaunay_mesher")

    assert "--FeatureExtraction.max_num_features" in fe_cmd
    assert "4096" in fe_cmd
    assert "--Mapper.min_num_matches" not in fe_cmd

    assert "--FeatureMatching.max_ratio" in fm_cmd
    assert "0.7" in fm_cmd
    assert "--FeatureExtraction.max_num_features" not in fm_cmd

    assert "--Mapper.min_num_matches" in map_cmd
    assert "15" in map_cmd
    assert "--FeatureExtraction.max_num_features" not in map_cmd

    assert "--DelaunayMeshing.max_proj_dist" in dm_cmd
    assert "20" in dm_cmd


def test_colmap_keep_workspace_false(
    tmp_path: Path, frames: list[Path], executable: Path
) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    workspace = tmp_path / "run"
    cfg = ReconstructionJobConfig(
        workspace_dir=workspace,
        binary_path=executable,
        keep_workspace=False,
    )

    def fake_run(command, **kwargs):
        subcmd = command[1]
        if subcmd == "exhaustive_matcher":
            db = workspace / "database.db"
            with sqlite3.connect(str(db)) as conn:
                conn.execute("CREATE TABLE two_view_geometries (pair_id INTEGER, rows INTEGER)")
                conn.execute("INSERT INTO two_view_geometries VALUES (1, 10)")
                conn.commit()
        elif subcmd == "mapper":
            model = workspace / "sparse" / "0"
            model.mkdir(parents=True, exist_ok=True)
            (model / "cameras.bin").write_bytes(b"c")
            (model / "images.bin").write_bytes(b"i")
            (model / "points3D.bin").write_bytes(b"p")
        elif subcmd == "model_converter":
            (workspace / "sparse" / "points.ply").write_text("ply\nelement vertex 5\nend_header\n")
        elif subcmd == "delaunay_mesher":
            (workspace / "sparse" / "mesh.ply").write_text("ply\nelement vertex 3\nelement face 1\nend_header\n")
        return subprocess.CompletedProcess(command, 0, stdout="Reconstruction with 3 images and 5 points", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        res = adapter.reconstruct(frames, cfg)
        assert res.success is True

    assert not (workspace / "images").exists()
    assert not (workspace / "database.db").exists()
    assert res.mesh_path.is_file()
    assert res.point_cloud_path.is_file()
    assert res.log_path.is_file()


def test_select_best_model_prefers_larger_model(tmp_path: Path, executable: Path) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    workspace = tmp_path / "run"
    frames = [tmp_path / f"frame_{i}.jpg" for i in range(10)]
    for f in frames:
        f.write_bytes(b"dummy")

    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable)

    def fake_run(command, **kwargs):
        subcmd = command[1]
        if subcmd == "mapper":
            # Model 0: small preliminary model with 2 images
            m0 = workspace / "sparse" / "0"
            m0.mkdir(parents=True, exist_ok=True)
            (m0 / "cameras.bin").write_bytes(b"cam")
            (m0 / "images.bin").write_bytes(b"\x02\x00\x00\x00\x00\x00\x00\x00")
            (m0 / "points3D.bin").write_bytes(b"\x0a\x00\x00\x00\x00\x00\x00\x00")

            # Model 1: primary model with 8 images and 150 points
            m1 = workspace / "sparse" / "1"
            m1.mkdir(parents=True, exist_ok=True)
            (m1 / "cameras.bin").write_bytes(b"cam")
            (m1 / "images.bin").write_bytes(b"\x08\x00\x00\x00\x00\x00\x00\x00")
            (m1 / "points3D.bin").write_bytes(b"\x96\x00\x00\x00\x00\x00\x00\x00")
        elif subcmd == "model_converter":
            (workspace / "sparse" / "points.ply").write_text("ply\nelement vertex 150\nend_header\n")
        elif subcmd == "delaunay_mesher":
            (workspace / "sparse" / "mesh.ply").write_text("ply\nelement vertex 50\nelement face 80\nend_header\n")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        res = adapter.reconstruct(frames, cfg)

    assert res.success is True
    assert res.sparse_reconstruction_path == (workspace / "sparse" / "1").resolve()
    assert res.registered_cameras_count == 8
    assert res.point_count == 150
    assert res.status == ReconstructionStatus.SUCCESS


def test_fragmented_reconstruction_marked_partial(tmp_path: Path, executable: Path) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    workspace = tmp_path / "run"
    frames = [tmp_path / f"frame_{i}.jpg" for i in range(20)]
    for f in frames:
        f.write_bytes(b"dummy")

    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable)

    def fake_run(command, **kwargs):
        subcmd = command[1]
        if subcmd == "mapper":
            # Only 4 of 20 images registered (20% < 35% threshold)
            m0 = workspace / "sparse" / "0"
            m0.mkdir(parents=True, exist_ok=True)
            (m0 / "cameras.bin").write_bytes(b"cam")
            (m0 / "images.bin").write_bytes(b"\x04\x00\x00\x00\x00\x00\x00\x00")
            (m0 / "points3D.bin").write_bytes(b"\x32\x00\x00\x00\x00\x00\x00\x00")
        elif subcmd == "model_converter":
            (workspace / "sparse" / "points.ply").write_text("ply\nelement vertex 50\nend_header\n")
        elif subcmd == "delaunay_mesher":
            (workspace / "sparse" / "mesh.ply").write_text("ply\nelement vertex 20\nelement face 30\nend_header\n")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        res = adapter.reconstruct(frames, cfg)

    assert res.success is True
    assert res.status == ReconstructionStatus.PARTIAL
    assert res.registered_cameras_count == 4
    assert res.registration_ratio == 0.2
    assert "fragmented" in (res.error_message or "").lower()


def test_insufficient_registered_cameras_raises_error(tmp_path: Path, executable: Path) -> None:
    adapter = ColmapAdapter(executable, has_gpu_support=False)
    workspace = tmp_path / "run"
    frames = [tmp_path / f"frame_{i}.jpg" for i in range(5)]
    for f in frames:
        f.write_bytes(b"dummy")

    cfg = ReconstructionJobConfig(workspace_dir=workspace, binary_path=executable)

    def fake_run(command, **kwargs):
        subcmd = command[1]
        if subcmd == "mapper":
            # Only 2 registered cameras (insufficient for 3D SfM)
            m0 = workspace / "sparse" / "0"
            m0.mkdir(parents=True, exist_ok=True)
            (m0 / "cameras.bin").write_bytes(b"cam")
            (m0 / "images.bin").write_bytes(b"\x02\x00\x00\x00\x00\x00\x00\x00")
            (m0 / "points3D.bin").write_bytes(b"\x0a\x00\x00\x00\x00\x00\x00\x00")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with patch("loom.reconstruction.colmap.subprocess.run", side_effect=fake_run):
        with pytest.raises(ReconstructionExecutionError, match="insufficient"):
            adapter.reconstruct(frames, cfg)

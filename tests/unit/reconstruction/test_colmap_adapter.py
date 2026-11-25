"""Unit tests for COLMAP reconstruction adapter and demo workflow contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from loom.pipeline.artifacts import ReconstructionArtifact
from loom.reconstruction.colmap import (
    ColmapAdapter,
    ColmapDenseArtifact,
    ColmapSparseArtifact,
)
from loom.reconstruction.exceptions import (
    ReconstructionArtifactNotFoundError,
    ReconstructionBinaryNotFoundError,
    ReconstructionError,
    ReconstructionExecutionError,
    ReconstructionInvalidInputError,
    ReconstructionTimeoutError,
)
from scripts.demo import run_demo


@pytest.fixture
def dummy_binary(tmp_path: Path) -> Path:
    """Create a dummy colmap executable."""
    bin_path = tmp_path / "colmap"
    bin_path.write_text("#!/bin/sh\nexit 0\n")
    bin_path.chmod(0o755)
    return bin_path


@pytest.fixture
def mock_dataset(tmp_path: Path) -> tuple[Path, Path]:
    """Create dummy images and sparse model directory."""
    img_dir = tmp_path / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (img_dir / f"frame_{i:04d}.png").write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")

    sparse_dir = tmp_path / "sparse" / "0"
    sparse_dir.mkdir(parents=True, exist_ok=True)
    (sparse_dir / "cameras.bin").write_bytes(b"fake_cameras")
    (sparse_dir / "images.bin").write_bytes(b"fake_images")
    (sparse_dir / "points3D.bin").write_bytes(b"fake_points")

    return img_dir, tmp_path / "sparse"


# -----------------------------------------------------------------------------
# Adapter Initialization & Availability
# -----------------------------------------------------------------------------


def test_colmap_adapter_init(dummy_binary: Path) -> None:
    """Verify ColmapAdapter initialization and naming."""
    adapter = ColmapAdapter(binary_path=dummy_binary)
    assert adapter.backend_name == "colmap"
    assert adapter.binary_path == dummy_binary.resolve()


def test_colmap_is_available(dummy_binary: Path, tmp_path: Path) -> None:
    """Verify .is_available() logic."""
    adapter_valid = ColmapAdapter(binary_path=dummy_binary)
    assert adapter_valid.is_available() is True

    adapter_invalid = ColmapAdapter(binary_path=tmp_path / "non_existent_binary")
    assert adapter_invalid.is_available() is False


# -----------------------------------------------------------------------------
# Dense Stereo Argument Builder & CUDA Flags
# -----------------------------------------------------------------------------


def test_dense_stereo_cuda_flags(dummy_binary: Path, tmp_path: Path) -> None:
    """Verify PatchMatchStereo argument builder enforces exact CUDA stereo flags."""
    workspace = tmp_path / "dense"
    args = ColmapAdapter.build_patch_match_stereo_args(
        binary_path=dummy_binary,
        workspace_path=workspace,
        gpu_index=0,
        max_image_size=1600,
        window_radius=5,
        num_iterations=5,
        geom_consistency=True,
        geom_consistency_max_cost=2.5,
    )

    # Check that required arguments and their flags are present
    assert "patch_match_stereo" in args
    assert "--PatchMatchStereo.gpu_index" in args
    idx_gpu = args.index("--PatchMatchStereo.gpu_index")
    assert args[idx_gpu + 1] == "0"

    assert "--PatchMatchStereo.max_image_size" in args
    idx_size = args.index("--PatchMatchStereo.max_image_size")
    assert args[idx_size + 1] == "1600"

    assert "--PatchMatchStereo.window_radius" in args
    idx_rad = args.index("--PatchMatchStereo.window_radius")
    assert args[idx_rad + 1] == "5"

    assert "--PatchMatchStereo.num_iterations" in args
    idx_iter = args.index("--PatchMatchStereo.num_iterations")
    assert args[idx_iter + 1] == "5"

    assert "--PatchMatchStereo.geom_consistency" in args
    idx_geom = args.index("--PatchMatchStereo.geom_consistency")
    assert args[idx_geom + 1] == "true"

    assert "--PatchMatchStereo.geom_consistency_max_cost" in args
    idx_cost = args.index("--PatchMatchStereo.geom_consistency_max_cost")
    assert args[idx_cost + 1] == "2.5"


def test_all_argument_builders(dummy_binary: Path, tmp_path: Path) -> None:
    """Verify argument builders for all 4 stages plus delaunay mesher."""
    img_dir = tmp_path / "images"
    sparse_dir = tmp_path / "sparse"
    dense_dir = tmp_path / "dense"
    fused_ply = dense_dir / "fused.ply"
    poisson_ply = dense_dir / "meshed-poisson.ply"
    delaunay_ply = dense_dir / "meshed-delaunay.ply"

    # 1. image_undistorter
    undistort_args = ColmapAdapter.build_image_undistorter_args(
        dummy_binary, img_dir, sparse_dir, dense_dir
    )
    assert undistort_args[1] == "image_undistorter"
    assert "--image_path" in undistort_args
    assert "--input_path" in undistort_args
    assert "--output_path" in undistort_args

    # 2. stereo_fusion
    fusion_args = ColmapAdapter.build_stereo_fusion_args(
        dummy_binary, dense_dir, fused_ply
    )
    assert fusion_args[1] == "stereo_fusion"
    assert "--workspace_path" in fusion_args
    assert "--output_path" in fusion_args
    assert "--StereoFusion.min_num_pixels" in fusion_args
    assert fusion_args[fusion_args.index("--StereoFusion.min_num_pixels") + 1] == "2"
    assert "--StereoFusion.max_image_size" in fusion_args
    assert fusion_args[fusion_args.index("--StereoFusion.max_image_size") + 1] == "1600"

    # 3. poisson_mesher
    poisson_args = ColmapAdapter.build_poisson_mesher_args(
        dummy_binary, fused_ply, poisson_ply
    )
    assert poisson_args[1] == "poisson_mesher"
    assert "--input_path" in poisson_args
    assert "--output_path" in poisson_args
    assert "--PoissonMeshing.depth" in poisson_args
    assert poisson_args[poisson_args.index("--PoissonMeshing.depth") + 1] == "10"
    assert "--PoissonMeshing.trim" in poisson_args
    assert poisson_args[poisson_args.index("--PoissonMeshing.trim") + 1] == "0"
    assert "--PoissonMeshing.point_weight" in poisson_args
    assert poisson_args[poisson_args.index("--PoissonMeshing.point_weight") + 1] == "1.0"

    # 4. delaunay_mesher
    delaunay_args = ColmapAdapter.build_delaunay_mesher_args(
        dummy_binary, sparse_dir, delaunay_ply, input_type="sparse"
    )
    assert delaunay_args[1] == "delaunay_mesher"
    assert "--input_type" in delaunay_args
    assert delaunay_args[delaunay_args.index("--input_type") + 1] == "sparse"


# -----------------------------------------------------------------------------
# Dense Reconstruction Pipeline Execution
# -----------------------------------------------------------------------------


def test_reconstruct_dense_executes_sequential_pipeline(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Ensure reconstruct_dense() executes image_undistorter -> patch_match_stereo ->
    stereo_fusion -> poisson_mesher in exact sequence and returns typed artifact."""
    img_dir, sparse_dir = mock_dataset
    dense_dir = tmp_path / "output_dense"

    executed_stages: list[str] = []

    def mock_subprocess(cmd, **kwargs):
        step = cmd[1]
        executed_stages.append(step)
        # Create output files when the relevant steps are executed
        if step == "stereo_fusion":
            (dense_dir / "fused.ply").write_bytes(b"ply\nformat ascii 1.0\nelement vertex 500\nend_header\n")
        elif step == "poisson_mesher":
            (dense_dir / "meshed-poisson.ply").write_bytes(b"ply\nformat ascii 1.0\nelement vertex 200\nend_header\n")
        proc = MagicMock()
        proc.returncode = 0
        return proc

    adapter = ColmapAdapter(binary_path=dummy_binary)
    with patch("loom.reconstruction.colmap.run_subprocess", side_effect=mock_subprocess):
        artifact = adapter.reconstruct_dense(
            image_dir=img_dir,
            sparse_dir=sparse_dir,
            output_dir=dense_dir,
            gpu_index=0,
            max_image_size=1600,
        )

    # Verify sequential pipeline
    assert executed_stages == [
        "image_undistorter",
        "patch_match_stereo",
        "stereo_fusion",
        "poisson_mesher",
    ]

    # Verify typed artifact pointing directly to meshed-poisson.ply
    assert isinstance(artifact, ReconstructionArtifact)
    assert isinstance(artifact, ColmapDenseArtifact)
    assert artifact.mesh_path == (dense_dir / "meshed-poisson.ply").resolve()
    assert artifact.poisson_mesh_path == (dense_dir / "meshed-poisson.ply").resolve()
    assert artifact.dense_point_cloud_path == (dense_dir / "fused.ply").resolve()
    assert artifact.backend_name == "colmap"
    assert artifact.stage_name == "dense_reconstruction"


def test_reconstruct_dense_missing_binary(mock_dataset: tuple[Path, Path], tmp_path: Path) -> None:
    """Verify ReconstructionBinaryNotFoundError is raised if colmap binary is absent."""
    img_dir, sparse_dir = mock_dataset
    adapter = ColmapAdapter(binary_path=tmp_path / "non_existent_colmap")
    with pytest.raises(ReconstructionBinaryNotFoundError, match="COLMAP executable .* not found"):
        adapter.reconstruct_dense(
            image_dir=img_dir,
            sparse_dir=sparse_dir,
            output_dir=tmp_path / "dense",
        )


def test_reconstruct_dense_invalid_input(dummy_binary: Path, tmp_path: Path) -> None:
    """Verify ReconstructionInvalidInputError is raised if inputs are missing."""
    adapter = ColmapAdapter(binary_path=dummy_binary)
    fake_dir = tmp_path / "ghost_dir"
    valid_dir = tmp_path / "valid_dir"
    valid_dir.mkdir()

    with pytest.raises(ReconstructionInvalidInputError, match="Image directory does not exist"):
        adapter.reconstruct_dense(image_dir=fake_dir, sparse_dir=valid_dir)

    with pytest.raises(ReconstructionInvalidInputError, match="Sparse reconstruction directory does not exist"):
        adapter.reconstruct_dense(image_dir=valid_dir, sparse_dir=fake_dir)


def test_reconstruct_dense_step_failure(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify ReconstructionExecutionError is raised if any sequential step fails."""
    img_dir, sparse_dir = mock_dataset
    adapter = ColmapAdapter(binary_path=dummy_binary)

    def failing_subprocess(cmd, **kwargs):
        if cmd[1] == "patch_match_stereo":
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr="CUDA out of memory error")
        return MagicMock(returncode=0)

    with patch("loom.reconstruction.colmap.run_subprocess", side_effect=failing_subprocess):
        with pytest.raises(ReconstructionExecutionError, match="patch_match_stereo.*failed with exit code 1"):
            adapter.reconstruct_dense(
                image_dir=img_dir,
                sparse_dir=sparse_dir,
                output_dir=tmp_path / "dense",
            )


def test_reconstruct_dense_timeout(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify ReconstructionTimeoutError is raised if a step exceeds timeout."""
    img_dir, sparse_dir = mock_dataset
    adapter = ColmapAdapter(binary_path=dummy_binary)

    def timing_out_subprocess(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

    with patch("loom.reconstruction.colmap.run_subprocess", side_effect=timing_out_subprocess):
        with pytest.raises(ReconstructionTimeoutError, match="timed out after"):
            adapter.reconstruct_dense(
                image_dir=img_dir,
                sparse_dir=sparse_dir,
                output_dir=tmp_path / "dense",
            )


def test_reconstruct_dense_missing_mesh_artifact(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify ReconstructionArtifactNotFoundError is raised if meshed-poisson.ply is not generated."""
    img_dir, sparse_dir = mock_dataset
    dense_dir = tmp_path / "dense"
    adapter = ColmapAdapter(binary_path=dummy_binary)

    # Commands succeed but fail to create meshed-poisson.ply
    with patch("loom.reconstruction.colmap.run_subprocess", return_value=MagicMock(returncode=0)):
        with pytest.raises(ReconstructionArtifactNotFoundError, match="meshed-poisson.ply.*was not created"):
            adapter.reconstruct_dense(
                image_dir=img_dir,
                sparse_dir=sparse_dir,
                output_dir=dense_dir,
            )


def test_reconstruct_dense_empty_poisson_triggers_delaunay_fallback(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify that when Poisson mesher generates 0 vertices, dense Delaunay fallback is invoked."""
    img_dir, sparse_dir = mock_dataset
    dense_dir = tmp_path / "dense_fallback"

    executed_stages: list[str] = []

    def mock_subprocess(cmd, **kwargs):
        step = cmd[1]
        executed_stages.append(step)
        if step == "stereo_fusion":
            (dense_dir / "fused.ply").write_bytes(b"ply\nformat ascii 1.0\nelement vertex 250\nend_header\n")
        elif step == "poisson_mesher":
            # Poisson generates empty mesh (0 vertices)
            (dense_dir / "meshed-poisson.ply").write_bytes(
                b"ply\nformat ascii 1.0\ncomment Created by COLMAP\nelement vertex 0\nend_header\n"
            )
        elif step == "delaunay_mesher":
            # Dense Delaunay fallback generates non-empty mesh
            (dense_dir / "meshed-delaunay.ply").write_bytes(
                b"ply\nformat ascii 1.0\nelement vertex 120\nend_header\n"
            )
        return MagicMock(returncode=0)

    adapter = ColmapAdapter(binary_path=dummy_binary)
    with patch("loom.reconstruction.colmap.run_subprocess", side_effect=mock_subprocess):
        artifact = adapter.reconstruct_dense(
            image_dir=img_dir,
            sparse_dir=sparse_dir,
            output_dir=dense_dir,
            min_num_pixels=2,
            poisson_depth=10,
            poisson_trim=0,
        )

    assert executed_stages == [
        "image_undistorter",
        "patch_match_stereo",
        "stereo_fusion",
        "poisson_mesher",
        "delaunay_mesher",
    ]
    assert artifact.mesh_path == (dense_dir / "meshed-delaunay.ply").resolve()
    assert artifact.delaunay_mesh_path == (dense_dir / "meshed-delaunay.ply").resolve()
    assert artifact.metadata["used_fallback"] is True


def test_reconstruct_dense_poisson_error_triggers_delaunay_fallback(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify that when Poisson mesher raises an error, dense Delaunay fallback is invoked."""
    img_dir, sparse_dir = mock_dataset
    dense_dir = tmp_path / "dense_err_fallback"

    executed_stages: list[str] = []

    def mock_subprocess(cmd, **kwargs):
        step = cmd[1]
        executed_stages.append(step)
        if step == "stereo_fusion":
            (dense_dir / "fused.ply").write_bytes(b"ply\nformat ascii 1.0\nelement vertex 250\nend_header\n")
        elif step == "poisson_mesher":
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr="Poisson mesher crashed")
        elif step == "delaunay_mesher":
            (dense_dir / "meshed-delaunay.ply").write_bytes(
                b"ply\nformat ascii 1.0\nelement vertex 140\nend_header\n"
            )
        return MagicMock(returncode=0)

    adapter = ColmapAdapter(binary_path=dummy_binary)
    with patch("loom.reconstruction.colmap.run_subprocess", side_effect=mock_subprocess):
        artifact = adapter.reconstruct_dense(
            image_dir=img_dir,
            sparse_dir=sparse_dir,
            output_dir=dense_dir,
        )

    assert "delaunay_mesher" in executed_stages
    assert artifact.mesh_path == (dense_dir / "meshed-delaunay.ply").resolve()
    assert artifact.metadata["used_fallback"] is True


def test_colmap_direct_stage_runners(dummy_binary: Path, tmp_path: Path) -> None:
    """Verify run_stereo_fusion, run_poisson_mesher, and run_delaunay_mesher helper methods."""
    dense_dir = tmp_path / "dense"
    fused_ply = dense_dir / "fused.ply"
    poisson_ply = dense_dir / "meshed-poisson.ply"
    delaunay_ply = dense_dir / "meshed-delaunay.ply"

    captured_cmds: list[list[str]] = []

    def mock_subprocess(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        return MagicMock(returncode=0)

    adapter = ColmapAdapter(binary_path=dummy_binary)
    with patch("loom.reconstruction.colmap.run_subprocess", side_effect=mock_subprocess):
        # Test run_stereo_fusion
        adapter.run_stereo_fusion(
            workspace_path=dense_dir,
            output_path=fused_ply,
            min_num_pixels=3,
            max_image_size=1200,
        )
        assert captured_cmds[-1][1] == "stereo_fusion"
        assert "--StereoFusion.min_num_pixels" in captured_cmds[-1]
        assert captured_cmds[-1][captured_cmds[-1].index("--StereoFusion.min_num_pixels") + 1] == "3"
        assert "--StereoFusion.max_image_size" in captured_cmds[-1]
        assert captured_cmds[-1][captured_cmds[-1].index("--StereoFusion.max_image_size") + 1] == "1200"

        # Test run_poisson_mesher
        adapter.run_poisson_mesher(
            input_path=fused_ply,
            output_path=poisson_ply,
            depth=11,
            trim=0,
            point_weight=1.0,
        )
        assert captured_cmds[-1][1] == "poisson_mesher"
        assert "--PoissonMeshing.depth" in captured_cmds[-1]
        assert captured_cmds[-1][captured_cmds[-1].index("--PoissonMeshing.depth") + 1] == "11"
        assert "--PoissonMeshing.trim" in captured_cmds[-1]
        assert captured_cmds[-1][captured_cmds[-1].index("--PoissonMeshing.trim") + 1] == "0"
        assert "--PoissonMeshing.point_weight" in captured_cmds[-1]
        assert captured_cmds[-1][captured_cmds[-1].index("--PoissonMeshing.point_weight") + 1] == "1.0"

        # Test run_delaunay_mesher
        adapter.run_delaunay_mesher(
            input_path=dense_dir,
            output_path=delaunay_ply,
            input_type="dense",
        )
        assert captured_cmds[-1][1] == "delaunay_mesher"
        assert "--input_type" in captured_cmds[-1]
        assert captured_cmds[-1][captured_cmds[-1].index("--input_type") + 1] == "dense"


# -----------------------------------------------------------------------------
# Sparse Delaunay Meshing (Diagnostic Preview)
# -----------------------------------------------------------------------------


def test_reconstruct_sparse_mesh_preview(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify reconstruct_sparse_mesh executes delaunay_mesher and returns typed artifact."""
    _, sparse_dir = mock_dataset
    out_mesh = tmp_path / "output" / "meshed-delaunay.ply"

    def mock_subprocess(cmd, **kwargs):
        out_mesh.parent.mkdir(parents=True, exist_ok=True)
        out_mesh.write_bytes(b"ply\nfake_delaunay_mesh")
        return MagicMock(returncode=0)

    adapter = ColmapAdapter(binary_path=dummy_binary)
    with patch("loom.reconstruction.colmap.run_subprocess", side_effect=mock_subprocess):
        artifact = adapter.reconstruct_sparse_mesh(
            sparse_dir=sparse_dir,
            output_path=out_mesh,
        )

    assert isinstance(artifact, ColmapSparseArtifact)
    assert artifact.mesh_path == out_mesh.resolve()
    assert artifact.stage_name == "sparse_mesh_preview"


# -----------------------------------------------------------------------------
# scripts/demo.py Workflow Contracts
# -----------------------------------------------------------------------------


def test_demo_dense_flag_invokes_reconstruct_dense(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify scripts/demo.py with --dense invokes adapter.reconstruct_dense()."""
    img_dir, sparse_dir = mock_dataset
    mock_artifact = ColmapDenseArtifact(
        stage_name="dense_reconstruction",
        mesh_path=tmp_path / "meshed-poisson.ply",
    )

    with patch.object(ColmapAdapter, "reconstruct_dense", return_value=mock_artifact) as mock_dense:
        summary = run_demo(
            dense=True,
            images_dir=img_dir,
            sparse_dir=sparse_dir,
            output_dir=tmp_path / "demo_out",
            colmap_path=dummy_binary,
        )

    assert mock_dense.called
    assert summary["mode"] == "dense"
    assert summary["mesh_path"] == tmp_path / "meshed-poisson.ply"


def test_demo_dense_failure_does_not_silently_fallback(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify scripts/demo.py raises ReconstructionError on dense failure and does NOT fallback to sparse."""
    img_dir, sparse_dir = mock_dataset

    with patch.object(
        ColmapAdapter,
        "reconstruct_dense",
        side_effect=ReconstructionExecutionError("CUDA PatchMatch failure"),
    ):
        with patch.object(ColmapAdapter, "reconstruct_sparse_mesh") as mock_sparse:
            with pytest.raises(ReconstructionError, match="Dense reconstruction failed"):
                run_demo(
                    dense=True,
                    allow_sparse_fallback=True,  # Even with fallback permitted, dense failure must not fallback
                    images_dir=img_dir,
                    sparse_dir=sparse_dir,
                    output_dir=tmp_path / "demo_out",
                    colmap_path=dummy_binary,
                )

            # Assert sparse mesher was NEVER invoked as a silent fallback
            assert not mock_sparse.called


def test_demo_omitted_dense_requires_sparse_fallback_flag(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify scripts/demo.py raises ReconstructionError if --dense is omitted without --allow-sparse-fallback."""
    img_dir, sparse_dir = mock_dataset

    with pytest.raises(ReconstructionError, match="Dense reconstruction was omitted .*--allow-sparse-fallback"):
        run_demo(
            dense=False,
            allow_sparse_fallback=False,
            images_dir=img_dir,
            sparse_dir=sparse_dir,
            output_dir=tmp_path / "demo_out",
            colmap_path=dummy_binary,
        )


def test_demo_omitted_dense_with_allow_sparse_fallback_runs_preview(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify scripts/demo.py runs sparse preview when --dense is omitted and --allow-sparse-fallback is set."""
    img_dir, sparse_dir = mock_dataset
    mock_sparse_art = ColmapSparseArtifact(
        stage_name="sparse_mesh_preview",
        mesh_path=tmp_path / "meshed-delaunay.ply",
    )

    with patch.object(ColmapAdapter, "reconstruct_sparse_mesh", return_value=mock_sparse_art) as mock_sparse:
        summary = run_demo(
            dense=False,
            allow_sparse_fallback=True,
            images_dir=img_dir,
            sparse_dir=sparse_dir,
            output_dir=tmp_path / "demo_out",
            colmap_path=dummy_binary,
        )

    assert mock_sparse.called
    assert summary["mode"] == "sparse_diagnostic_preview"
    assert summary["mesh_path"] == tmp_path / "meshed-delaunay.ply"


# -----------------------------------------------------------------------------
# Sequential Matching & Thread Scaling Tests
# -----------------------------------------------------------------------------


def test_sequential_matcher_args(dummy_binary: Path, tmp_path: Path) -> None:
    """Verify build_sequential_matcher_args enforces video matching parameters."""
    db_path = tmp_path / "database.db"
    args = ColmapAdapter.build_sequential_matcher_args(
        binary_path=dummy_binary,
        database_path=db_path,
        overlap=10,
        quadratic_overlap=1,
        loop_detection=1,
        use_gpu=1,
        gpu_index=0,
    )

    assert args[1] == "sequential_matcher"
    assert "--database_path" in args
    assert str(db_path.resolve()) in args

    assert "--SequentialMatching.overlap" in args
    assert args[args.index("--SequentialMatching.overlap") + 1] == "10"

    assert "--SequentialMatching.quadratic_overlap" in args
    assert args[args.index("--SequentialMatching.quadratic_overlap") + 1] == "1"

    assert "--SequentialMatching.loop_detection" in args
    assert args[args.index("--SequentialMatching.loop_detection") + 1] == "1"

    assert "--FeatureMatching.use_gpu" in args
    assert args[args.index("--FeatureMatching.use_gpu") + 1] == "1"

    assert "--FeatureMatching.gpu_index" in args
    assert args[args.index("--FeatureMatching.gpu_index") + 1] == "0"


def test_mapper_args_thread_scaling(dummy_binary: Path, tmp_path: Path) -> None:
    """Verify build_mapper_args enforces 16 threads, 20 global BA iterations, and 15 local BA iterations."""
    db_path = tmp_path / "database.db"
    img_dir = tmp_path / "images"
    sparse_dir = tmp_path / "sparse"

    args = ColmapAdapter.build_mapper_args(
        binary_path=dummy_binary,
        database_path=db_path,
        image_path=img_dir,
        output_path=sparse_dir,
        num_threads=16,
        ba_global_max_num_iterations=20,
        ba_local_max_num_iterations=15,
    )

    assert args[1] == "mapper"
    assert "--database_path" in args
    assert "--image_path" in args
    assert "--output_path" in args

    assert "--Mapper.num_threads" in args
    assert args[args.index("--Mapper.num_threads") + 1] == "16"

    assert "--Mapper.ba_global_max_num_iterations" in args
    assert args[args.index("--Mapper.ba_global_max_num_iterations") + 1] == "20"

    assert "--Mapper.ba_local_max_num_iterations" in args
    assert args[args.index("--Mapper.ba_local_max_num_iterations") + 1] == "15"


def test_run_matching_invokes_correct_matcher(dummy_binary: Path, tmp_path: Path) -> None:
    """Verify run_matching invokes sequential_matcher when sequential=True or matching_mode='sequential', and exhaustive when False."""
    db_path = tmp_path / "database.db"
    adapter = ColmapAdapter(binary_path=dummy_binary)

    executed_cmds: list[list[str]] = []

    def mock_subprocess(cmd, **kwargs):
        executed_cmds.append(cmd)
        return MagicMock(returncode=0)

    with patch("loom.reconstruction.colmap.run_subprocess", side_effect=mock_subprocess):
        # 1. Sequential matching via sequential=True
        adapter.run_matching(database_path=db_path, sequential=True)
        assert executed_cmds[-1][1] == "sequential_matcher"
        assert "--SequentialMatching.overlap" in executed_cmds[-1]
        assert "--SequentialMatching.quadratic_overlap" in executed_cmds[-1]
        assert "--SequentialMatching.loop_detection" in executed_cmds[-1]
        assert "--FeatureMatching.use_gpu" in executed_cmds[-1]
        assert "--FeatureMatching.gpu_index" in executed_cmds[-1]

        # 2. Sequential matching via matching_mode="sequential"
        adapter.run_matching(database_path=db_path, matching_mode="sequential")
        assert executed_cmds[-1][1] == "sequential_matcher"

        # 3. Exhaustive matching
        adapter.run_matching(database_path=db_path, sequential=False)
        assert executed_cmds[-1][1] == "exhaustive_matcher"
        assert "--database_path" in executed_cmds[-1]


def test_run_mapper_invokes_colmap_mapper(dummy_binary: Path, tmp_path: Path) -> None:
    """Verify run_mapper invokes mapper with thread scaling and BA iterations."""
    db_path = tmp_path / "database.db"
    img_dir = tmp_path / "images"
    sparse_dir = tmp_path / "sparse"
    adapter = ColmapAdapter(binary_path=dummy_binary)

    executed_cmds: list[list[str]] = []

    def mock_subprocess(cmd, **kwargs):
        executed_cmds.append(cmd)
        return MagicMock(returncode=0)

    with patch("loom.reconstruction.colmap.run_subprocess", side_effect=mock_subprocess):
        adapter.run_mapper(
            database_path=db_path,
            image_path=img_dir,
            output_path=sparse_dir,
            num_threads=16,
            ba_global_max_num_iterations=20,
            ba_local_max_num_iterations=15,
        )

    assert len(executed_cmds) == 1
    cmd = executed_cmds[0]
    assert cmd[1] == "mapper"
    assert "--Mapper.num_threads" in cmd
    assert cmd[cmd.index("--Mapper.num_threads") + 1] == "16"
    assert "--Mapper.ba_global_max_num_iterations" in cmd
    assert cmd[cmd.index("--Mapper.ba_global_max_num_iterations") + 1] == "20"
    assert "--Mapper.ba_local_max_num_iterations" in cmd
    assert cmd[cmd.index("--Mapper.ba_local_max_num_iterations") + 1] == "15"


def test_reconstruct_uses_sequential_matching_when_flagged(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify reconstruct() routes <=120 frames to exhaustive_matcher and >120 frames to sequential_matcher."""
    from loom.reconstruction.models import ReconstructionJobConfig

    img_dir, _ = mock_dataset
    frames = sorted(img_dir.glob("*.png"))  # 3 frames (<= 120)
    workspace = tmp_path / "sfm_ws"

    adapter = ColmapAdapter(binary_path=dummy_binary)

    with patch.object(adapter, "run_matching") as mock_match, patch.object(adapter, "run_mapper") as mock_map, patch.object(adapter, "reconstruct_sparse_mesh") as mock_sparse:
        mock_sparse.return_value = ColmapSparseArtifact(stage_name="sparse", mesh_path=tmp_path / "mesh.ply")
        (workspace / "sparse" / "0").mkdir(parents=True, exist_ok=True)
        (workspace / "sparse" / "0" / "cameras.bin").write_bytes(b"data")

        job_cfg = ReconstructionJobConfig(
            workspace_dir=workspace,
            binary_path=dummy_binary,
            sequential=True,
        )
        adapter.reconstruct(frames, job_cfg)

        assert mock_match.called
        assert mock_match.call_args.kwargs["num_images"] == 3
        assert mock_match.call_args.kwargs["sequential"] is False
        assert mock_map.called
        assert mock_map.call_args.kwargs["num_threads"] == 16
        assert mock_map.call_args.kwargs["ba_global_max_num_iterations"] == 20


def test_feature_extractor_optical_lock_and_adaptive_matching_routing(
    dummy_binary: Path,
    tmp_path: Path,
) -> None:
    """Verify single_camera=1, SIMPLE_RADIAL, peak_threshold=0.002, edge_threshold=16, guided_matching=1, max_ratio=0.85, and <=150 exhaustive vs >150 sequential."""
    db_path = tmp_path / "database.db"
    img_dir = tmp_path / "images"
    img_dir.mkdir()

    fe_args = ColmapAdapter.build_feature_extractor_args(
        binary_path=dummy_binary,
        database_path=db_path,
        image_path=img_dir,
        gpu_index=0,
    )
    assert fe_args[1] == "feature_extractor"
    assert fe_args[fe_args.index("--ImageReader.camera_model") + 1] == "SIMPLE_RADIAL"
    assert fe_args[fe_args.index("--ImageReader.single_camera") + 1] == "1"
    assert fe_args[fe_args.index("--SiftExtraction.peak_threshold") + 1] == "0.002"
    assert fe_args[fe_args.index("--SiftExtraction.edge_threshold") + 1] == "16"
    assert fe_args[fe_args.index("--SiftExtraction.max_num_features") + 1] == "8192"
    assert fe_args[fe_args.index("--FeatureExtraction.use_gpu") + 1] == "1"
    assert fe_args[fe_args.index("--FeatureExtraction.gpu_index") + 1] == "0"

    adapter = ColmapAdapter(binary_path=dummy_binary)
    executed: list[list[str]] = []

    def _capture(cmd, **kwargs):
        executed.append(list(cmd))
        return MagicMock(returncode=0)

    with patch("loom.reconstruction.colmap.run_subprocess", side_effect=_capture):
        # <= 150 images (including 130 and 150) -> GPU exhaustive_matcher with guided_matching=1 & max_ratio=0.85
        adapter.run_matching(database_path=db_path, num_images=150, gpu_index=0)
        assert executed[-1][1] == "exhaustive_matcher"
        assert executed[-1][executed[-1].index("--FeatureMatching.use_gpu") + 1] == "1"
        assert executed[-1][executed[-1].index("--FeatureMatching.gpu_index") + 1] == "0"
        assert executed[-1][executed[-1].index("--FeatureMatching.guided_matching") + 1] == "1"
        assert executed[-1][executed[-1].index("--SiftMatching.max_ratio") + 1] == "0.85"

        # > 150 images -> sequential_matcher fallback (overlap=10, quadratic_overlap=1, loop_detection=1)
        adapter.run_matching(database_path=db_path, num_images=180, gpu_index=0)
        assert executed[-1][1] == "sequential_matcher"
        assert executed[-1][executed[-1].index("--SequentialMatching.overlap") + 1] == "10"
        assert executed[-1][executed[-1].index("--SequentialMatching.quadratic_overlap") + 1] == "1"
        assert executed[-1][executed[-1].index("--SequentialMatching.loop_detection") + 1] == "1"
        assert executed[-1][executed[-1].index("--FeatureMatching.guided_matching") + 1] == "1"
        assert executed[-1][executed[-1].index("--SiftMatching.max_ratio") + 1] == "0.85"


def test_select_largest_sparse_model_picks_max_registered_views(tmp_path: Path) -> None:
    """Verify select_largest_sparse_model scans sparse/0, sparse/1, sparse/2 and selects max views."""
    import struct

    sparse_root = tmp_path / "sparse"
    for idx, (reg, cams, pts) in {0: (14, 1, 2000), 1: (66, 1, 14500), 2: (9, 2, 800)}.items():
        d = sparse_root / str(idx)
        d.mkdir(parents=True)
        (d / "images.bin").write_bytes(struct.pack("<Q", reg))
        (d / "cameras.bin").write_bytes(struct.pack("<Q", cams))
        (d / "points3D.bin").write_bytes(struct.pack("<Q", pts))

    winner = ColmapAdapter.select_largest_sparse_model(sparse_root)
    assert winner.model_dir == (sparse_root / "1").resolve()
    assert winner.registered_views == 66
    assert winner.num_cameras == 1
    assert winner.sparse_points == 14500
    assert ColmapAdapter.resolve_sparse_model_dir(sparse_root) == (sparse_root / "1").resolve()


def test_demo_video_passes_sequential_matching(
    dummy_binary: Path,
    tmp_path: Path,
) -> None:
    """Verify scripts/demo.py invokes adaptive GPU matching (exhaustive for <=120 frames) and writes manifest."""
    from loom.video.frames import FrameSetArtifact, FrameExtractor
    from loom.reconstruction.models import ReconstructionJobConfig

    fake_video = tmp_path / "test.mp4"
    fake_video.write_bytes(b"dummy_video_stream")

    extracted_dir = tmp_path / "frames"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    frame1 = extracted_dir / "frame_0000.png"
    frame1.write_bytes(b"\x89PNGfake")

    mock_artifact = FrameSetArtifact(
        stage_name="frame_extraction",
        frames_dir=extracted_dir,
        frame_paths=[frame1],
        total_extracted=1,
    )

    with patch.object(FrameExtractor, "extract", return_value=mock_artifact), patch.object(ColmapAdapter, "reconstruct") as mock_recon, patch.object(ColmapAdapter, "reconstruct_sparse_mesh"):
        run_demo(
            dense=False,
            allow_sparse_fallback=True,
            video_path=fake_video,
            output_dir=tmp_path / "demo_out",
            colmap_path=dummy_binary,
            max_frames=75,
        )

        assert mock_recon.called
        passed_job_cfg: ReconstructionJobConfig = mock_recon.call_args[0][1]
        assert passed_job_cfg.sequential is False
        assert passed_job_cfg.extra_params["matching_mode"] == "exhaustive"
        assert (tmp_path / "demo_out" / "pipeline_manifest.json").is_file()


def test_demo_mesh_only_bypasses_colmap_and_runs_downstream(tmp_path: Path) -> None:
    """Verify scripts/demo.py --mesh-only bypasses COLMAP and executes cleanup and export directly."""
    import trimesh
    from scripts.demo import run_demo, main

    dummy_mesh = trimesh.creation.box(extents=[10.0, 10.0, 10.0])
    mesh_path = tmp_path / "input_mesh.ply"
    dummy_mesh.export(str(mesh_path))

    out_dir = tmp_path / "demo_mesh_only_output"

    result = run_demo(
        mesh_only=mesh_path,
        output_dir=out_dir,
        clean_mesh=True,
        export_stl=True,
    )

    assert result["success"] is True
    assert result["mesh_path"].is_file()
    assert (out_dir / "cleaned_input_mesh.ply").is_file()
    assert result["exported_stl_path"] is not None
    assert result["exported_stl_path"].is_file()


def test_demo_main_mesh_only_cli_argument(tmp_path: Path, monkeypatch) -> None:
    """Verify scripts/demo.py main() parses and executes --mesh-only CLI argument."""
    import trimesh
    from scripts.demo import main

    dummy_mesh = trimesh.creation.box(extents=[5.0, 5.0, 5.0])
    mesh_path = tmp_path / "cli_input_mesh.ply"
    dummy_mesh.export(str(mesh_path))

    out_dir = tmp_path / "cli_out"
    exit_code = main(["--mesh-only", str(mesh_path), "--output-dir", str(out_dir)])
    assert exit_code == 0
    assert (out_dir / "cleaned_cli_input_mesh.ply").is_file()


def test_demo_target_length_scaling(tmp_path: Path) -> None:
    """Verify scripts/demo.py --target-length applies uniform metric scaling prior to STL export."""
    import json
    import numpy as np
    import trimesh
    from scripts.demo import main

    dummy_mesh = trimesh.creation.box(extents=[2.0, 4.0, 1.0])
    mesh_path = tmp_path / "small_box.ply"
    dummy_mesh.export(str(mesh_path))

    out_dir = tmp_path / "demo_scaled_out"
    stl_dir = tmp_path / "stl_out"

    exit_code = main([
        "--mesh-only", str(mesh_path),
        "--output-dir", str(out_dir),
        "--stl-dir", str(stl_dir),
        "--target-length", "200.0",
    ])
    assert exit_code == 0

    exported_stl = stl_dir / "cleaned_small_box_metric.stl"
    manifest_file = stl_dir / "cleaned_small_box_metric_manifest.json"

    assert exported_stl.is_file()
    assert manifest_file.is_file()

    manifest_data = json.loads(manifest_file.read_text())
    assert manifest_data["scale_factor_applied"] == 50.0  # 200.0 / 4.0
    assert manifest_data["metadata"]["printability_gate_passed"] is True

    # Check scaled mesh on disk
    scaled_mesh = trimesh.load(str(out_dir / "scaled_cleaned_small_box.ply"), process=False)
    assert np.isclose(max(scaled_mesh.extents), 200.0)


def test_demo_align_support_cli(tmp_path: Path) -> None:
    """Verify scripts/demo.py --align-support applies canonical alignment."""
    import trimesh
    from scripts.demo import main

    # Synthetic box tilted
    box = trimesh.creation.box(extents=[10.0, 10.0, 1.0])
    rot = trimesh.transformations.rotation_matrix(0.3, [1.0, 0.0, 0.0])
    box.apply_transform(rot)

    mesh_path = tmp_path / "tilted_box.ply"
    box.export(str(mesh_path))

    out_dir = tmp_path / "align_out"
    exit_code = main([
        "--mesh-only", str(mesh_path),
        "--output-dir", str(out_dir),
        "--align-support",
        "--clean-mesh",
    ])
    assert exit_code == 0
    aligned_files = list(out_dir.glob("aligned_*.ply"))
    assert len(aligned_files) >= 1


def test_demo_base_z_cli(tmp_path: Path) -> None:
    """Verify scripts/demo.py --base-z explicitly sets planar cut elevation."""
    import numpy as np
    import trimesh
    from scripts.demo import main

    box = trimesh.creation.box(extents=[10.0, 10.0, 4.0])  # Z in [-2, 2]
    mesh_path = tmp_path / "tall_box.ply"
    box.export(str(mesh_path))

    out_dir = tmp_path / "base_z_out"
    exit_code = main([
        "--mesh-only", str(mesh_path),
        "--output-dir", str(out_dir),
        "--cap-base",
        "--base-z", "0.5",
    ])
    assert exit_code == 0
    capped_files = list(out_dir.glob("cleaned_*.ply"))
    assert len(capped_files) >= 1
    loaded = trimesh.load(str(capped_files[0]), process=False)
    assert np.isclose(loaded.bounds[0][2], 0.5, atol=1e-2)


def test_colmap_adapter_turbo_flags(dummy_binary: Path, tmp_path: Path) -> None:
    """Verify turbo mode flags for matching, mapper, and stereo fusion."""
    adapter = ColmapAdapter(binary_path=dummy_binary)

    # 1. Matching in turbo mode
    with patch.object(adapter, "_execute_step") as mock_exec:
        db = tmp_path / "database.db"
        db.touch()
        adapter.run_matching(database_path=db, turbo=True)
        assert mock_exec.called
        step, cmd = mock_exec.call_args[0][0], mock_exec.call_args[0][1]
        assert step == "sequential_matcher"
        assert "--SequentialMatching.overlap" in cmd
        assert cmd[cmd.index("--SequentialMatching.overlap") + 1] == "10"
        assert cmd[cmd.index("--SequentialMatching.quadratic_overlap") + 1] == "1"
        assert cmd[cmd.index("--SequentialMatching.loop_detection") + 1] == "1"

    # 2. Mapper in turbo mode
    with patch.object(adapter, "_execute_step") as mock_exec:
        img_dir = tmp_path / "images"
        img_dir.mkdir(exist_ok=True)
        out_sparse = tmp_path / "sparse"
        adapter.run_mapper(
            database_path=db,
            image_path=img_dir,
            output_path=out_sparse,
            turbo=True,
        )
        assert mock_exec.called
        step, cmd = mock_exec.call_args[0][0], mock_exec.call_args[0][1]
        assert step == "mapper"
        assert cmd[cmd.index("--Mapper.ba_global_max_num_iterations") + 1] == "15"
        assert cmd[cmd.index("--Mapper.ba_local_max_num_iterations") + 1] == "12"
        assert cmd[cmd.index("--Mapper.min_num_matches") + 1] == "10"
        assert cmd[cmd.index("--Mapper.init_min_num_inliers") + 1] == "50"

    # 3. Stereo fusion in turbo mode
    with patch.object(adapter, "_execute_step") as mock_exec:
        ws = tmp_path / "dense"
        fused = ws / "fused.ply"
        adapter.run_stereo_fusion(
            workspace_path=ws,
            output_path=fused,
            turbo=True,
        )
        assert mock_exec.called
        step, cmd = mock_exec.call_args[0][0], mock_exec.call_args[0][1]
        assert step == "stereo_fusion"
        assert cmd[cmd.index("--input_type") + 1] == "photometric"
        assert cmd[cmd.index("--StereoFusion.max_image_size") + 1] == "960"


def test_demo_turbo_cli(tmp_path: Path) -> None:
    """Verify demo.py --turbo CLI flag executes end-to-end with mesh-only shortcut."""
    import trimesh
    from scripts.demo import main

    box = trimesh.creation.box(extents=[10.0, 10.0, 4.0])
    mesh_path = tmp_path / "turbo_box.ply"
    box.export(str(mesh_path))

    out_dir = tmp_path / "turbo_cli_out"
    exit_code = main([
        "--mesh-only", str(mesh_path),
        "--output-dir", str(out_dir),
        "--turbo",
        "--target-length", "280.0",
        "--export-stl",
    ])
    assert exit_code == 0
    stl_files = list(Path("outputs/stl").glob("*_metric.stl"))
    assert len(stl_files) >= 1


def test_reconstruct_sfm_circuit_breaker(
    dummy_binary: Path,
    mock_dataset: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Verify reconstruct() raises RuntimeError when registered views fall below 75%."""
    import struct
    from loom.reconstruction.models import ReconstructionJobConfig

    img_dir, _ = mock_dataset
    frames = sorted(img_dir.glob("*.png"))  # 3 frames in mock_dataset
    workspace = tmp_path / "sfm_cb_ws"

    adapter = ColmapAdapter(binary_path=dummy_binary)

    sparse_dir = workspace / "sparse" / "0"
    sparse_dir.mkdir(parents=True, exist_ok=True)
    images_bin = sparse_dir / "images.bin"

    # Case 1: Only 1 view registered out of 3 (33.3% < 75%) -> abort
    with open(images_bin, "wb") as f:
        f.write(struct.pack("<Q", 1))

    with patch.object(adapter, "run_matching"), patch.object(adapter, "run_mapper"):
        job_cfg = ReconstructionJobConfig(
            workspace_dir=workspace,
            binary_path=dummy_binary,
            sequential=True,
        )
        with pytest.raises(RuntimeError, match="SfM tracking lost: insufficient overlap or texture"):
            adapter.reconstruct(frames, job_cfg)

    # Case 2: 3 views registered out of 3 (100% >= 75%) -> passes
    with open(images_bin, "wb") as f:
        f.write(struct.pack("<Q", 3))

    with patch.object(adapter, "run_matching"), patch.object(adapter, "run_mapper"), patch.object(adapter, "reconstruct_sparse_mesh") as mock_sparse:
        mock_sparse.return_value = ColmapSparseArtifact(stage_name="sparse", mesh_path=tmp_path / "mesh.ply")
        res = adapter.reconstruct(frames, job_cfg)
        assert res is not None








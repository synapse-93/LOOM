"""COLMAP Structure-from-Motion and Multi-View Stereo photogrammetry engine adapter."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from loom.pipeline.artifacts import (
    ReconstructionArtifact,
    compute_ply_density,
    read_ply_vertex_count,
)
from loom.reconstruction.base import ReconstructionEngine
from loom.reconstruction.exceptions import (
    ReconstructionArtifactNotFoundError,
    ReconstructionBinaryNotFoundError,
    ReconstructionError,
    ReconstructionExecutionError,
    ReconstructionInvalidInputError,
    ReconstructionTimeoutError,
)
from loom.reconstruction.models import (
    ReconstructionJobConfig,
    ReconstructionResult,
    ReconstructionStatus,
)
from loom.utils.paths import ensure_directory
from loom.utils.subprocess import run_subprocess

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ColmapDenseArtifact(ReconstructionArtifact):
    """Typed artifact representing dense COLMAP reconstruction output."""

    fused_point_cloud_path: Optional[Path] = None
    poisson_mesh_path: Optional[Path] = None
    delaunay_mesh_path: Optional[Path] = None
    isolated_point_cloud_path: Optional[Path] = None


@dataclass(frozen=True)
class ColmapSparseArtifact(ReconstructionArtifact):
    """Typed artifact representing sparse COLMAP reconstruction / preview output."""

    delaunay_mesh_path: Optional[Path] = None


class ColmapAdapter(ReconstructionEngine):
    """Adapter for COLMAP CLI photogrammetry pipeline.

    Supports sparse Structure-from-Motion (SfM), sequential dense Multi-View Stereo (MVS)
    reconstruction (undistortion -> PatchMatch stereo -> fusion -> Poisson meshing),
    and sparse Delaunay meshing diagnostic previews.
    """

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    max_frames: int = 65

    def __init__(self, binary_path: str | Path | None = None, max_frames: int = 65) -> None:
        """Initialize ColmapAdapter.

        Args:
            binary_path: Optional explicit path to colmap binary.
                         If None, searches PATH, 'COLMAP_PATH', 'COLMAP_BIN',
                         or default '/usr/bin/colmap'.
            max_frames: Maximum keyframes to ingest across a 360-degree orbit (default: 65).
        """
        self.max_frames = max_frames
        if binary_path is not None:
            self._binary_path: Optional[str] = str(binary_path)
        elif "COLMAP_PATH" in os.environ:
            self._binary_path = os.environ["COLMAP_PATH"]
        elif "COLMAP_BIN" in os.environ:
            self._binary_path = os.environ["COLMAP_BIN"]
        else:
            self._binary_path = None

    @property
    def backend_name(self) -> str:
        return "colmap"

    @property
    def binary_path(self) -> Optional[Path]:
        """Configured path to colmap executable, if resolved."""
        resolved = self.resolve_binary()
        return resolved if resolved else (Path(self._binary_path) if self._binary_path else None)

    def resolve_binary(self, override_path: str | Path | None = None) -> Optional[Path]:
        """Resolve COLMAP executable path checking overrides, PATH, and standard system paths.

        Args:
            override_path: Optional per-job binary override.

        Returns:
            Resolved Path to executable if found, else None.
        """
        raw_target = override_path if override_path is not None else self._binary_path

        if raw_target is not None:
            target_str = str(raw_target)
            p = Path(target_str)
            if p.is_file():
                return p.resolve()
            if p.is_dir():
                for c in (p / "colmap", p / "colmap.exe"):
                    if c.is_file():
                        return c.resolve()
            # If explicit path containing directory separators was provided and not found
            if "/" in target_str or "\\" in target_str:
                return None
            which_path = shutil.which(target_str)
            if which_path is not None:
                return Path(which_path).resolve()
            return None

        # If no explicit path was provided, check PATH and standard locations
        which_path = shutil.which("colmap")
        if which_path is not None:
            return Path(which_path).resolve()

        for candidate in (Path("/usr/bin/colmap"), Path("/usr/local/bin/colmap")):
            if candidate.is_file():
                return candidate.resolve()

        return None

    def is_available(self, override_path: str | Path | None = None) -> bool:
        """Check if colmap executable is available on the host system."""
        return self.resolve_binary(override_path) is not None

    @staticmethod
    def resolve_sparse_model_dir(sparse_dir: Path) -> Path:
        """Locate directory containing COLMAP model files (cameras.bin/.txt, etc.).

        If sparse_dir contains a '0' subfolder with model files, resolves to sparse_dir / '0'.
        Otherwise returns sparse_dir.
        """
        p = Path(sparse_dir)
        sub_zero = p / "0"
        if sub_zero.is_dir() and any(sub_zero.glob("cameras.*")):
            return sub_zero.resolve()
        return p.resolve()

    # -------------------------------------------------------------------------
    # Argument Builders
    # -------------------------------------------------------------------------

    @staticmethod
    def build_image_undistorter_args(
        binary_path: Path | str,
        image_path: Path | str,
        input_path: Path | str,
        output_path: Path | str,
        output_type: str = "COLMAP",
        additional_args: Sequence[str] | None = None,
    ) -> list[str]:
        """Build command arguments for `colmap image_undistorter`."""
        cmd = [
            str(binary_path),
            "image_undistorter",
            "--image_path",
            str(Path(image_path).resolve()),
            "--input_path",
            str(Path(input_path).resolve()),
            "--output_path",
            str(Path(output_path).resolve()),
            "--output_type",
            output_type,
        ]
        if additional_args:
            cmd.extend(additional_args)
        return cmd

    @staticmethod
    def build_patch_match_stereo_args(
        binary_path: Path | str,
        workspace_path: Path | str,
        gpu_index: int = 0,
        max_image_size: int = 1600,
        window_radius: int = 5,
        num_iterations: int = 5,
        geom_consistency: bool = True,
        workspace_format: str = "COLMAP",
        geom_consistency_max_cost: float | None = None,
        additional_args: Sequence[str] | None = None,
    ) -> list[str]:
        """Build command arguments for `colmap patch_match_stereo` with CUDA stereo flags.

        Enforces hardware safety flags:
            --PatchMatchStereo.gpu_index 0
            --PatchMatchStereo.max_image_size 1600 (safeguards 8 GB VRAM buffer)
            --PatchMatchStereo.window_radius 5
            --PatchMatchStereo.num_iterations 5
            --PatchMatchStereo.geom_consistency true
        """
        cmd = [
            str(binary_path),
            "patch_match_stereo",
            "--workspace_path",
            str(Path(workspace_path).resolve()),
            "--workspace_format",
            workspace_format,
            "--PatchMatchStereo.gpu_index",
            str(gpu_index),
            "--PatchMatchStereo.max_image_size",
            str(max_image_size),
            "--PatchMatchStereo.window_radius",
            str(window_radius),
            "--PatchMatchStereo.num_iterations",
            str(num_iterations),
            "--PatchMatchStereo.geom_consistency",
            "true" if geom_consistency else "false",
        ]
        if geom_consistency_max_cost is not None:
            cmd.extend([
                "--PatchMatchStereo.geom_consistency_max_cost",
                str(geom_consistency_max_cost),
            ])
        if additional_args:
            cmd.extend(additional_args)
        return cmd

    @staticmethod
    def build_stereo_fusion_args(
        binary_path: Path | str,
        workspace_path: Path | str,
        output_path: Path | str,
        workspace_format: str = "COLMAP",
        input_type: str = "geometric",
        min_num_pixels: int = 2,
        max_image_size: int = 1600,
        additional_args: Sequence[str] | None = None,
    ) -> list[str]:
        """Build command arguments for `colmap stereo_fusion`."""
        cmd = [
            str(binary_path),
            "stereo_fusion",
            "--workspace_path",
            str(Path(workspace_path).resolve()),
            "--workspace_format",
            workspace_format,
            "--input_type",
            input_type,
            "--output_path",
            str(Path(output_path).resolve()),
            "--StereoFusion.min_num_pixels",
            str(min_num_pixels),
            "--StereoFusion.max_image_size",
            str(max_image_size),
        ]
        if additional_args:
            cmd.extend(additional_args)
        return cmd

    @staticmethod
    def build_poisson_mesher_args(
        binary_path: Path | str,
        input_path: Path | str,
        output_path: Path | str,
        depth: int = 10,
        trim: int = 0,
        point_weight: float = 1.0,
        additional_args: Sequence[str] | None = None,
    ) -> list[str]:
        """Build command arguments for `colmap poisson_mesher`."""
        cmd = [
            str(binary_path),
            "poisson_mesher",
            "--input_path",
            str(Path(input_path).resolve()),
            "--output_path",
            str(Path(output_path).resolve()),
            "--PoissonMeshing.depth",
            str(depth),
            "--PoissonMeshing.trim",
            str(trim),
            "--PoissonMeshing.point_weight",
            f"{point_weight:.1f}" if isinstance(point_weight, float) else str(point_weight),
        ]
        if additional_args:
            cmd.extend(additional_args)
        return cmd

    @staticmethod
    def build_delaunay_mesher_args(
        binary_path: Path | str,
        input_path: Path | str,
        output_path: Path | str,
        input_type: str = "sparse",
        additional_args: Sequence[str] | None = None,
    ) -> list[str]:
        """Build command arguments for `colmap delaunay_mesher`."""
        cmd = [
            str(binary_path),
            "delaunay_mesher",
            "--input_path",
            str(Path(input_path).resolve()),
            "--input_type",
            input_type,
            "--output_path",
            str(Path(output_path).resolve()),
        ]
        if additional_args:
            cmd.extend(additional_args)
        return cmd

    @staticmethod
    def build_feature_extractor_args(
        binary_path: Path | str,
        database_path: Path | str,
        image_path: Path | str,
        additional_args: Sequence[str] | None = None,
    ) -> list[str]:
        """Build command arguments for `colmap feature_extractor`."""
        cmd = [
            str(binary_path),
            "feature_extractor",
            "--database_path",
            str(Path(database_path).resolve()),
            "--image_path",
            str(Path(image_path).resolve()),
        ]
        if additional_args:
            cmd.extend(additional_args)
        return cmd

    @staticmethod
    def build_exhaustive_matcher_args(
        binary_path: Path | str,
        database_path: Path | str,
        additional_args: Sequence[str] | None = None,
    ) -> list[str]:
        """Build command arguments for `colmap exhaustive_matcher`."""
        cmd = [
            str(binary_path),
            "exhaustive_matcher",
            "--database_path",
            str(Path(database_path).resolve()),
        ]
        if additional_args:
            cmd.extend(additional_args)
        return cmd

    @staticmethod
    def build_sequential_matcher_args(
        binary_path: Path | str,
        database_path: Path | str,
        overlap: int = 10,
        quadratic_overlap: int = 1,
        loop_detection: int = 1,
        use_gpu: int = 1,
        gpu_index: int = 0,
        additional_args: Sequence[str] | None = None,
    ) -> list[str]:
        """Build command arguments for `colmap sequential_matcher`.

        Configured with video matching optimization:
            colmap sequential_matcher \
                --database_path <db> \
                --SequentialMatching.overlap 10 \
                --SequentialMatching.quadratic_overlap 1 \
                --SequentialMatching.loop_detection 1 \
                --FeatureMatching.use_gpu 1 \
                --FeatureMatching.gpu_index 0
        """
        cmd = [
            str(binary_path),
            "sequential_matcher",
            "--database_path",
            str(Path(database_path).resolve()),
            "--SequentialMatching.overlap",
            str(overlap),
            "--SequentialMatching.quadratic_overlap",
            str(quadratic_overlap),
            "--SequentialMatching.loop_detection",
            str(loop_detection),
            "--FeatureMatching.use_gpu",
            str(use_gpu),
            "--FeatureMatching.gpu_index",
            str(gpu_index),
        ]
        if additional_args:
            cmd.extend(additional_args)
        return cmd

    @staticmethod
    def build_mapper_args(
        binary_path: Path | str,
        database_path: Path | str,
        image_path: Path | str,
        output_path: Path | str,
        num_threads: int = 16,
        ba_global_max_num_iterations: int = 20,
        ba_local_max_num_iterations: int = 15,
        min_num_matches: int = 15,
        additional_args: Sequence[str] | None = None,
    ) -> list[str]:
        """Build command arguments for `colmap mapper` with 16-thread scaling, BA limits, and match bounds.

        Enforces CPU mapping flags:
            colmap mapper \
                --database_path <db> \
                --image_path <images> \
                --output_path <sparse> \
                --Mapper.num_threads 16 \
                --Mapper.ba_global_max_num_iterations 20 \
                --Mapper.ba_local_max_num_iterations 15 \
                --Mapper.min_num_matches 15
        """
        cmd = [
            str(binary_path),
            "mapper",
            "--database_path",
            str(Path(database_path).resolve()),
            "--image_path",
            str(Path(image_path).resolve()),
            "--output_path",
            str(Path(output_path).resolve()),
            "--Mapper.num_threads",
            str(num_threads),
            "--Mapper.ba_global_max_num_iterations",
            str(ba_global_max_num_iterations),
            "--Mapper.ba_local_max_num_iterations",
            str(ba_local_max_num_iterations),
            "--Mapper.min_num_matches",
            str(min_num_matches),
        ]
        if additional_args:
            cmd.extend(additional_args)
        return cmd

    # -------------------------------------------------------------------------
    # Sparse Pipeline Stages (Matching & Mapper)
    # -------------------------------------------------------------------------

    def run_matching(
        self,
        database_path: Path | str,
        sequential: bool = False,
        matching_mode: str | None = None,
        *,
        binary_path: Path | str | None = None,
        overlap: int | None = None,
        quadratic_overlap: int = 1,
        loop_detection: int = 1,
        use_gpu: int = 1,
        gpu_index: int = 0,
        timeout_seconds: int = 1800,
        turbo: bool = False,
        additional_args: Sequence[str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        """Execute feature matching stage using either sequential or exhaustive matcher.

        If input is from video (or matching_mode="sequential" or sequential=True),
        executes `colmap sequential_matcher`:
            colmap sequential_matcher \
                --database_path <db> \
                --SequentialMatching.overlap 10 \
                --SequentialMatching.quadratic_overlap 1 \
                --SequentialMatching.loop_detection 1 \
                --FeatureMatching.use_gpu 1 \
                --FeatureMatching.gpu_index 0
        Otherwise executes `colmap exhaustive_matcher`.

        Args:
            database_path: Path to COLMAP SQLite database.
            sequential: If True, uses sequential_matcher with video matching parameters;
                        otherwise uses exhaustive_matcher.
            matching_mode: Optional explicit matching mode ("sequential" or "exhaustive").
            binary_path: Optional COLMAP binary path override.
            overlap: Sequential matching window overlap (default: 10).
            quadratic_overlap: Sequential quadratic overlap flag (default: 1).
            loop_detection: Loop detection flag using vocabulary tree (default: 1).
            use_gpu: Enable GPU acceleration for feature matching (default: 1).
            gpu_index: GPU device index (default: 0).
            timeout_seconds: Subprocess timeout in seconds.
            additional_args: Optional additional arguments passed to command.
            cwd: Optional working directory.
        """
        bin_path = self.resolve_binary(binary_path)
        if bin_path is None:
            target_desc = str(binary_path or self._binary_path or "colmap")
            raise ReconstructionBinaryNotFoundError(
                f"COLMAP executable '{target_desc}' not found."
            )

        db_path = Path(database_path).resolve()
        work_dir = Path(cwd).resolve() if cwd is not None else db_path.parent

        use_sequential = False
        if turbo:
            use_sequential = True
            eff_overlap = overlap if overlap is not None else 10
            eff_quadratic = quadratic_overlap if quadratic_overlap is not None else 1
            use_gpu = 1
        elif matching_mode is not None:
            use_sequential = matching_mode.lower() == "sequential"
            eff_overlap = overlap if overlap is not None else 10
            eff_quadratic = quadratic_overlap
        else:
            use_sequential = bool(sequential)
            eff_overlap = overlap if overlap is not None else 10
            eff_quadratic = quadratic_overlap

        if use_sequential:
            cmd = self.build_sequential_matcher_args(
                binary_path=bin_path,
                database_path=db_path,
                overlap=eff_overlap,
                quadratic_overlap=eff_quadratic,
                loop_detection=loop_detection,
                use_gpu=use_gpu,
                gpu_index=gpu_index,
                additional_args=additional_args,
            )
            step_name = "sequential_matcher"
        else:
            cmd = self.build_exhaustive_matcher_args(
                binary_path=bin_path,
                database_path=db_path,
                additional_args=additional_args,
            )
            step_name = "exhaustive_matcher"

        self._execute_step(step_name, cmd, cwd=work_dir, timeout=timeout_seconds)

    def run_mapper(
        self,
        database_path: Path | str,
        image_path: Path | str,
        output_path: Path | str,
        *,
        binary_path: Path | str | None = None,
        num_threads: int = 16,
        ba_global_max_num_iterations: int = 20,
        ba_local_max_num_iterations: int = 15,
        min_num_matches: int = 15,
        timeout_seconds: int = 1800,
        turbo: bool = False,
        additional_args: Sequence[str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        """Execute sparse SfM mapper stage with thread scaling, BA limits, and match bounds:
            colmap mapper \
                --database_path <db> \
                --image_path <images> \
                --output_path <sparse> \
                --Mapper.num_threads 16 \
                --Mapper.ba_global_max_num_iterations 20 \
                --Mapper.ba_local_max_num_iterations 15 \
                --Mapper.min_num_matches 15

        Args:
            database_path: Path to COLMAP SQLite database.
            image_path: Path to directory containing source images/frames.
            output_path: Directory where sparse models are saved.
            binary_path: Optional COLMAP binary path override.
            num_threads: Number of CPU threads (default: 16).
            ba_global_max_num_iterations: Max global bundle adjustment iterations (default: 20).
            ba_local_max_num_iterations: Max local bundle adjustment iterations (default: 15).
            min_num_matches: Minimum number of matches for registration (default: 15).
            timeout_seconds: Subprocess timeout in seconds.
            additional_args: Optional additional arguments passed to command.
            cwd: Optional working directory.
        """
        bin_path = self.resolve_binary(binary_path)
        if bin_path is None:
            target_desc = str(binary_path or self._binary_path or "colmap")
            raise ReconstructionBinaryNotFoundError(
                f"COLMAP executable '{target_desc}' not found."
            )

        db_path = Path(database_path).resolve()
        img_path = Path(image_path).resolve()
        out_path = Path(output_path).resolve()
        work_dir = Path(cwd).resolve() if cwd is not None else out_path.parent

        if turbo:
            num_threads = 16
            ba_global_max_num_iterations = 15
            ba_local_max_num_iterations = 12

        cmd = self.build_mapper_args(
            binary_path=bin_path,
            database_path=db_path,
            image_path=img_path,
            output_path=out_path,
            num_threads=num_threads,
            ba_global_max_num_iterations=ba_global_max_num_iterations,
            ba_local_max_num_iterations=ba_local_max_num_iterations,
            min_num_matches=min_num_matches,
            additional_args=additional_args,
        )
        self._execute_step("mapper", cmd, cwd=work_dir, timeout=timeout_seconds)

    # -------------------------------------------------------------------------
    # Dense Pipeline Execution (Stereo Fusion, Poisson & Delaunay Meshing)
    # -------------------------------------------------------------------------

    def run_stereo_fusion(
        self,
        workspace_path: Path | str,
        output_path: Path | str,
        *,
        binary_path: Path | str | None = None,
        workspace_format: str = "COLMAP",
        input_type: str | None = None,
        min_num_pixels: int | None = None,
        max_image_size: int | None = None,
        timeout_seconds: int = 1800,
        turbo: bool = False,
        additional_args: Sequence[str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        """Execute COLMAP stereo fusion stage:
            colmap stereo_fusion \
                --workspace_path <workspace> \
                --workspace_format <format> \
                --input_type <type> \
                --output_path <fused.ply> \
                --StereoFusion.min_num_pixels 2 \
                --StereoFusion.max_image_size 1600

        Args:
            workspace_path: Path to dense workspace directory.
            output_path: Path to output fused point cloud (.ply).
            binary_path: Optional COLMAP binary path override.
            workspace_format: Workspace format (default: "COLMAP").
            input_type: Stereo input type ("geometric" or "photometric", default: "geometric").
            min_num_pixels: Minimum number of pixels/views per point (default: 2).
            max_image_size: Max image dimension limit (default: 1600).
            timeout_seconds: Subprocess timeout in seconds.
            additional_args: Optional additional arguments passed to command.
            cwd: Optional working directory.
        """
        bin_path = self.resolve_binary(binary_path)
        if bin_path is None:
            target_desc = str(binary_path or self._binary_path or "colmap")
            raise ReconstructionBinaryNotFoundError(
                f"COLMAP executable '{target_desc}' not found."
            )

        ws_path = Path(workspace_path).resolve()
        out_path = Path(output_path).resolve()
        work_dir = Path(cwd).resolve() if cwd is not None else ws_path

        eff_input_type = input_type if input_type is not None else ("photometric" if turbo else "geometric")
        eff_max_size = max_image_size if max_image_size is not None else (960 if turbo else 1600)
        eff_min_pixels = min_num_pixels if min_num_pixels is not None else (3 if turbo else 2)

        cmd = self.build_stereo_fusion_args(
            binary_path=bin_path,
            workspace_path=ws_path,
            output_path=out_path,
            workspace_format=workspace_format,
            input_type=eff_input_type,
            min_num_pixels=eff_min_pixels,
            max_image_size=eff_max_size,
            additional_args=additional_args,
        )
        self._execute_step("stereo_fusion", cmd, cwd=work_dir, timeout=timeout_seconds)

    def run_poisson_mesher(
        self,
        input_path: Path | str,
        output_path: Path | str,
        *,
        binary_path: Path | str | None = None,
        depth: int = 10,
        trim: int = 0,
        point_weight: float = 1.0,
        timeout_seconds: int = 1800,
        additional_args: Sequence[str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        """Execute COLMAP Poisson mesher stage:
            colmap poisson_mesher \
                --input_path <fused.ply> \
                --output_path <meshed-poisson.ply> \
                --PoissonMeshing.depth 10 \
                --PoissonMeshing.trim 0 \
                --PoissonMeshing.point_weight 1.0

        Args:
            input_path: Path to fused point cloud (.ply).
            output_path: Path to output Poisson mesh (.ply).
            binary_path: Optional COLMAP binary path override.
            depth: Octree maximum depth (default: 10).
            trim: Surface trimmer threshold (default: 0 to disable trimming).
            point_weight: Weight of point cloud constraints (default: 1.0).
            timeout_seconds: Subprocess timeout in seconds.
            additional_args: Optional additional arguments passed to command.
            cwd: Optional working directory.
        """
        bin_path = self.resolve_binary(binary_path)
        if bin_path is None:
            target_desc = str(binary_path or self._binary_path or "colmap")
            raise ReconstructionBinaryNotFoundError(
                f"COLMAP executable '{target_desc}' not found."
            )

        in_path = Path(input_path).resolve()
        out_path = Path(output_path).resolve()
        work_dir = Path(cwd).resolve() if cwd is not None else out_path.parent

        cmd = self.build_poisson_mesher_args(
            binary_path=bin_path,
            input_path=in_path,
            output_path=out_path,
            depth=depth,
            trim=trim,
            point_weight=point_weight,
            additional_args=additional_args,
        )
        self._execute_step("poisson_mesher", cmd, cwd=work_dir, timeout=timeout_seconds)

    def run_delaunay_mesher(
        self,
        input_path: Path | str,
        output_path: Path | str,
        *,
        input_type: str = "dense",
        binary_path: Path | str | None = None,
        timeout_seconds: int = 1800,
        additional_args: Sequence[str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        """Execute COLMAP Delaunay mesher stage:
            colmap delaunay_mesher \
                --input_path <input_path> \
                --input_type <dense|sparse> \
                --output_path <output_path>

        Args:
            input_path: Path to sparse reconstruction directory or dense workspace.
            output_path: Path to output Delaunay mesh (.ply).
            input_type: Mesh type ("dense" or "sparse", default: "dense").
            binary_path: Optional COLMAP binary path override.
            timeout_seconds: Subprocess timeout in seconds.
            additional_args: Optional additional arguments passed to command.
            cwd: Optional working directory.
        """
        bin_path = self.resolve_binary(binary_path)
        if bin_path is None:
            target_desc = str(binary_path or self._binary_path or "colmap")
            raise ReconstructionBinaryNotFoundError(
                f"COLMAP executable '{target_desc}' not found."
            )

        in_path = Path(input_path).resolve()
        out_path = Path(output_path).resolve()
        work_dir = Path(cwd).resolve() if cwd is not None else out_path.parent

        cmd = self.build_delaunay_mesher_args(
            binary_path=bin_path,
            input_path=in_path,
            output_path=out_path,
            input_type=input_type,
            additional_args=additional_args,
        )
        self._execute_step("delaunay_mesher", cmd, cwd=work_dir, timeout=timeout_seconds)

    def reconstruct_dense(
        self,
        image_dir: Path | str,
        sparse_dir: Path | str,
        output_dir: Path | str | None = None,
        *,
        binary_path: Path | str | None = None,
        gpu_index: int = 0,
        max_image_size: int = 1600,
        window_radius: int = 5,
        num_iterations: int = 5,
        geom_consistency: bool = True,
        min_num_pixels: int = 2,
        poisson_depth: int = 10,
        poisson_trim: int = 0,
        poisson_point_weight: float = 1.0,
        timeout_seconds: int = 1800,
        turbo: bool = False,
        additional_args: Sequence[str] | None = None,
    ) -> ColmapDenseArtifact:
        """Execute the sequential COLMAP dense MVS reconstruction pipeline:
            image_undistorter -> patch_match_stereo -> stereo_fusion -> poisson_mesher
            (with automatic dense Delaunay mesher fallback if Poisson meshing produces 0 vertices).

        Args:
            image_dir: Path to directory containing source RGB frames.
            sparse_dir: Path to sparse SfM model directory (or sparse/0).
            output_dir: Target dense workspace directory (defaults to sibling 'dense').
            binary_path: Optional COLMAP binary path override.
            gpu_index: GPU index for CUDA stereo computation (default: 0).
            max_image_size: Max image dimension limit to safeguard VRAM (default: 1600).
            window_radius: Stereo window radius (default: 5).
            num_iterations: Stereo iterations (default: 5).
            geom_consistency: Whether to enforce photometric and geometric consistency (default: True).
            min_num_pixels: Minimum number of pixel/view observations for stereo fusion (default: 2).
            poisson_depth: Octree depth for Poisson reconstruction (default: 10).
            poisson_trim: SurfaceTrimmer trimming parameter (default: 0 to avoid trimming geometry).
            poisson_point_weight: Weight of point cloud constraints (default: 1.0).
            timeout_seconds: Subprocess timeout per stage in seconds.
            additional_args: Optional additional arguments passed to commands.

        Returns:
            ColmapDenseArtifact pointing directly to the generated mesh (poisson or delaunay fallback).

        Raises:
            ReconstructionBinaryNotFoundError: If COLMAP binary is missing.
            ReconstructionInvalidInputError: If image_dir or sparse_dir does not exist.
            ReconstructionTimeoutError: If any pipeline stage times out.
            ReconstructionExecutionError: If any stage exits with a non-zero returncode.
            ReconstructionArtifactNotFoundError: If neither Poisson nor dense Delaunay mesh is generated.
        """
        bin_path = self.resolve_binary(binary_path)
        if bin_path is None:
            target_desc = str(binary_path or self._binary_path or "colmap")
            raise ReconstructionBinaryNotFoundError(
                f"COLMAP executable '{target_desc}' not found. "
                "Ensure COLMAP is installed at /usr/bin/colmap or in system PATH."
            )

        resolved_images = Path(image_dir).resolve()
        if not resolved_images.is_dir():
            raise ReconstructionInvalidInputError(
                f"Image directory does not exist: {resolved_images}"
            )

        resolved_sparse = Path(sparse_dir).resolve()
        if not resolved_sparse.is_dir():
            raise ReconstructionInvalidInputError(
                f"Sparse reconstruction directory does not exist: {resolved_sparse}"
            )

        model_sparse_dir = self.resolve_sparse_model_dir(resolved_sparse)

        if output_dir is not None:
            dense_workspace = ensure_directory(Path(output_dir).resolve())
        else:
            dense_workspace = ensure_directory(resolved_sparse.parent / "dense")

        geom_consistency_max_cost = 2.5 if (turbo and geom_consistency) else None
        if turbo:
            max_image_size = min(max_image_size, 960)
            window_radius = 4
            num_iterations = 3
            geom_consistency = False
            min_num_pixels = 3
            poisson_depth = 10
            poisson_trim = 0
            poisson_point_weight = 1.0

        fused_ply = dense_workspace / "fused.ply"
        poisson_ply = dense_workspace / "meshed-poisson.ply"
        delaunay_dense_ply = dense_workspace / "meshed-delaunay.ply"

        logger.info(
            "Starting COLMAP sequential dense reconstruction pipeline:\n"
            "  Binary:         %s\n"
            "  Images:         %s\n"
            "  Sparse:         %s\n"
            "  Dense:          %s\n"
            "  GPU Index:      %d (max_image_size=%d, window_radius=%d, iterations=%d, geom_consistency=%s)\n"
            "  Stereo Fusion:  min_num_pixels=%d\n"
            "  Poisson Mesher: depth=%d, trim=%d, point_weight=%.1f",
            bin_path,
            resolved_images,
            model_sparse_dir,
            dense_workspace,
            gpu_index,
            max_image_size,
            window_radius,
            num_iterations,
            geom_consistency,
            min_num_pixels,
            poisson_depth,
            poisson_trim,
            poisson_point_weight,
        )

        start_time = time.time()

        # Step 1: image_undistorter
        cmd_undistort = self.build_image_undistorter_args(
            binary_path=bin_path,
            image_path=resolved_images,
            input_path=model_sparse_dir,
            output_path=dense_workspace,
            output_type="COLMAP",
            additional_args=additional_args,
        )
        self._execute_step("image_undistorter", cmd_undistort, cwd=dense_workspace, timeout=timeout_seconds)

        # Step 2: patch_match_stereo
        cmd_stereo = self.build_patch_match_stereo_args(
            binary_path=bin_path,
            workspace_path=dense_workspace,
            gpu_index=gpu_index,
            max_image_size=max_image_size,
            window_radius=window_radius,
            num_iterations=num_iterations,
            geom_consistency=geom_consistency,
            workspace_format="COLMAP",
            geom_consistency_max_cost=geom_consistency_max_cost,
            additional_args=additional_args,
        )
        self._execute_step("patch_match_stereo", cmd_stereo, cwd=dense_workspace, timeout=timeout_seconds)

        # Step 3: stereo_fusion
        self.run_stereo_fusion(
            workspace_path=dense_workspace,
            output_path=fused_ply,
            binary_path=bin_path,
            workspace_format="COLMAP",
            input_type="geometric" if geom_consistency else ("photometric" if turbo else "geometric"),
            min_num_pixels=min_num_pixels,
            max_image_size=max_image_size,
            timeout_seconds=timeout_seconds,
            turbo=turbo,
            additional_args=additional_args,
            cwd=dense_workspace,
        )

        # Diagnostic check after stereo fusion:
        # Read vertex count of fused.ply, log total points and density.
        # If points < 50,000, log high-severity warning that parallax/coverage was insufficient.
        point_count = 0
        point_density = 0.0
        insufficient_coverage_warning = False
        if fused_ply.is_file():
            point_count = read_ply_vertex_count(fused_ply)
            point_density = compute_ply_density(fused_ply, point_count)
            logger.info(
                "Stereo fusion point cloud diagnostic: total_points=%d, density=%.2f pts/unit³",
                point_count,
                point_density,
            )
            if point_count < 50000:
                insufficient_coverage_warning = True
                logger.warning(
                    "HIGH SEVERITY WARNING: Fused point cloud has insufficient points (%d < 50,000 threshold). "
                    "Parallax or coverage was insufficient during capture, risking incomplete surface reconstruction.",
                    point_count,
                )

        # Step 3.5: Support plane alignment & foreground segmentation (Turbo mode)
        isolated_ply: Optional[Path] = None
        if turbo and fused_ply.is_file() and fused_ply.stat().st_size > 0:
            try:
                from loom.geometry.alignment import CoordinateNormalizer, extract_colmap_camera_centers
                from loom.geometry.segmentation import ForegroundSegmenter

                cam_centers = extract_colmap_camera_centers(model_sparse_dir)
                normalizer = CoordinateNormalizer()
                norm_cloud, norm_result = normalizer.normalize(
                    fused_ply, camera_centers=cam_centers, center_elevated=True
                )
                logger.info(
                    "Support plane alignment normalized point cloud: inliers=%d",
                    norm_result.inlier_count,
                )

                candidate_isolated = dense_workspace / "fused_isolated.ply"
                segmenter = ForegroundSegmenter(
                    z_min_cutoff=-0.005,
                    radial_multiplier=1.30,
                    z_elevated_cutoff=0.015,
                )
                isolated_cloud, seg_result = segmenter.segment(
                    norm_cloud, output_path=candidate_isolated, normals=norm_result.aligned_normals
                )
                if candidate_isolated.is_file() and candidate_isolated.stat().st_size > 0:
                    isolated_ply = candidate_isolated
                    logger.info(
                        "Foreground segmentation produced %s with %d points (radius=%.4f)",
                        isolated_ply,
                        seg_result.points_after,
                        seg_result.object_radius,
                    )
            except Exception as exc:
                logger.warning(
                    "Turbo support plane alignment / foreground segmentation failed: %s. "
                    "Proceeding with raw fused point cloud.",
                    exc,
                )

        # Step 4: poisson_mesher (with automatic dense Delaunay fallback)
        # Note: COLMAP poisson_mesher strictly requires normal vectors (nx, ny, nz)
        # present natively in fused.ply or fused_isolated.ply produced by stereo_fusion & segmentation.
        poisson_success = False
        selected_mesh_path: Optional[Path] = None
        mesh_input_ply = isolated_ply if (turbo and isolated_ply is not None) else fused_ply

        try:
            self.run_poisson_mesher(
                input_path=mesh_input_ply,
                output_path=poisson_ply,
                binary_path=bin_path,
                depth=poisson_depth,
                trim=poisson_trim,
                point_weight=poisson_point_weight,
                timeout_seconds=timeout_seconds,
                additional_args=additional_args,
                cwd=dense_workspace,
            )
            if poisson_ply.is_file() and poisson_ply.stat().st_size > 0:
                v_count = read_ply_vertex_count(poisson_ply)
                if v_count > 0:
                    poisson_success = True
                    selected_mesh_path = poisson_ply
                    logger.info("Poisson meshing succeeded with %d vertices.", v_count)
                else:
                    logger.warning(
                        "Poisson mesher generated a mesh file with 0 vertices (%d bytes). "
                        "Triggering dense Delaunay mesher fallback.",
                        poisson_ply.stat().st_size,
                    )
            else:
                logger.warning(
                    "Poisson mesher did not produce an output file. "
                    "Triggering dense Delaunay mesher fallback."
                )
        except Exception as exc:
            logger.warning(
                "Poisson mesher failed with error: %s. "
                "Triggering dense Delaunay mesher fallback.",
                exc,
            )

        delaunay_mesh_created = False
        if not poisson_success:
            logger.info(
                "Running dense Delaunay mesher fallback:\n"
                "  Workspace: %s\n"
                "  Output:    %s",
                dense_workspace,
                delaunay_dense_ply,
            )
            self.run_delaunay_mesher(
                input_path=dense_workspace,
                output_path=delaunay_dense_ply,
                input_type="dense",
                binary_path=bin_path,
                timeout_seconds=timeout_seconds,
                additional_args=additional_args,
                cwd=dense_workspace,
            )

            if not delaunay_dense_ply.is_file() or delaunay_dense_ply.stat().st_size == 0:
                raise ReconstructionArtifactNotFoundError(
                    f"COLMAP dense reconstruction pipeline finished, but expected Poisson mesh "
                    f"artifact '{poisson_ply}' was not created (or had 0 vertices), and dense Delaunay "
                    f"mesher fallback '{delaunay_dense_ply}' was not created."
                )

            d_vcount = read_ply_vertex_count(delaunay_dense_ply)
            if d_vcount == 0:
                raise ReconstructionArtifactNotFoundError(
                    f"COLMAP dense reconstruction pipeline failed: Dense Delaunay mesh '{delaunay_dense_ply}' "
                    f"contains 0 vertices."
                )

            selected_mesh_path = delaunay_dense_ply
            delaunay_mesh_created = True
            logger.info(
                "Dense Delaunay mesher fallback succeeded: %s (%d vertices, %d bytes)",
                delaunay_dense_ply,
                d_vcount,
                delaunay_dense_ply.stat().st_size,
            )

        elapsed_time = round(time.time() - start_time, 2)

        logger.info(
            "COLMAP dense reconstruction finished in %.2fs. Mesh generated: %s (%d bytes)",
            elapsed_time,
            selected_mesh_path,
            selected_mesh_path.stat().st_size,
        )

        return ColmapDenseArtifact(
            stage_name="dense_reconstruction",
            mesh_path=selected_mesh_path.resolve(),
            poisson_mesh_path=poisson_ply.resolve() if poisson_ply.is_file() and poisson_success else None,
            delaunay_mesh_path=delaunay_dense_ply.resolve() if delaunay_mesh_created and delaunay_dense_ply.is_file() else None,
            dense_point_cloud_path=fused_ply.resolve() if fused_ply.exists() else None,
            fused_point_cloud_path=fused_ply.resolve() if fused_ply.exists() else None,
            point_cloud_path=fused_ply.resolve() if fused_ply.exists() else None,
            isolated_point_cloud_path=isolated_ply.resolve() if isolated_ply and isolated_ply.exists() else None,
            sparse_reconstruction_path=model_sparse_dir,
            backend_name=self.backend_name,
            execution_time_seconds=elapsed_time,
            point_count=point_count,
            point_density=point_density,
            insufficient_coverage_warning=insufficient_coverage_warning,
            metadata={
                "gpu_index": gpu_index,
                "max_image_size": max_image_size,
                "window_radius": window_radius,
                "num_iterations": num_iterations,
                "geom_consistency": geom_consistency,
                "min_num_pixels": min_num_pixels,
                "poisson_depth": poisson_depth,
                "poisson_trim": poisson_trim,
                "poisson_point_weight": poisson_point_weight,
                "used_fallback": not poisson_success,
                "point_count": point_count,
                "point_density": point_density,
                "insufficient_coverage_warning": insufficient_coverage_warning,
                "turbo": turbo,
                "isolated_point_cloud": str(isolated_ply) if isolated_ply else None,
            },
        )

    # -------------------------------------------------------------------------
    # Sparse Delaunay Meshing (Diagnostic Preview)
    # -------------------------------------------------------------------------

    def reconstruct_sparse_mesh(
        self,
        sparse_dir: Path | str,
        output_path: Path | str | None = None,
        *,
        binary_path: Path | str | None = None,
        timeout_seconds: int = 600,
        additional_args: Sequence[str] | None = None,
    ) -> ColmapSparseArtifact:
        """Execute `colmap delaunay_mesher --input_type sparse` as a diagnostic preview.

        Args:
            sparse_dir: Path to sparse SfM model directory.
            output_path: Path to write the output Delaunay mesh (.ply).
            binary_path: Optional COLMAP binary path override.
            timeout_seconds: Subprocess timeout in seconds.
            additional_args: Optional additional arguments passed to command.

        Returns:
            ColmapSparseArtifact pointing directly to the generated `meshed-delaunay.ply`.

        Raises:
            ReconstructionBinaryNotFoundError: If COLMAP binary is missing.
            ReconstructionInvalidInputError: If sparse_dir does not exist.
            ReconstructionTimeoutError: If execution exceeds timeout.
            ReconstructionExecutionError: If command fails.
            ReconstructionArtifactNotFoundError: If output mesh is missing or empty.
        """
        bin_path = self.resolve_binary(binary_path)
        if bin_path is None:
            target_desc = str(binary_path or self._binary_path or "colmap")
            raise ReconstructionBinaryNotFoundError(
                f"COLMAP executable '{target_desc}' not found."
            )

        resolved_sparse = Path(sparse_dir).resolve()
        if not resolved_sparse.is_dir():
            raise ReconstructionInvalidInputError(
                f"Sparse reconstruction directory does not exist: {resolved_sparse}"
            )

        model_sparse_dir = self.resolve_sparse_model_dir(resolved_sparse)

        if output_path is not None:
            dest_mesh = Path(output_path).resolve()
            ensure_directory(dest_mesh.parent)
        else:
            dest_mesh = resolved_sparse.parent / "meshed-delaunay.ply"

        logger.info(
            "[DIAGNOSTIC PREVIEW] Executing sparse Delaunay mesher:\n"
            "  Sparse dir: %s\n"
            "  Output:     %s",
            model_sparse_dir,
            dest_mesh,
        )

        start_time = time.time()
        self.run_delaunay_mesher(
            input_path=model_sparse_dir,
            output_path=dest_mesh,
            input_type="sparse",
            binary_path=bin_path,
            timeout_seconds=timeout_seconds,
            additional_args=additional_args,
            cwd=dest_mesh.parent,
        )
        elapsed_time = round(time.time() - start_time, 2)

        if not dest_mesh.is_file() or dest_mesh.stat().st_size == 0:
            raise ReconstructionArtifactNotFoundError(
                f"Sparse Delaunay mesher finished, but expected mesh artifact '{dest_mesh}' was not created."
            )

        logger.info(
            "[DIAGNOSTIC PREVIEW] Sparse Delaunay mesh generated in %.2fs: %s (%d bytes)",
            elapsed_time,
            dest_mesh,
            dest_mesh.stat().st_size,
        )

        return ColmapSparseArtifact(
            stage_name="sparse_mesh_preview",
            mesh_path=dest_mesh.resolve(),
            delaunay_mesh_path=dest_mesh.resolve(),
            sparse_reconstruction_path=model_sparse_dir,
            backend_name=self.backend_name,
            execution_time_seconds=elapsed_time,
            metadata={"preview_mode": "sparse_delaunay"},
        )

    # -------------------------------------------------------------------------
    # Helper Execution Method
    # -------------------------------------------------------------------------

    def _execute_step(
        self,
        step_name: str,
        cmd: list[str],
        cwd: Path,
        timeout: int,
    ) -> None:
        """Run a single COLMAP subprocess command with standard error mapping."""
        logger.info("Executing COLMAP stage '%s': %s", step_name, " ".join(cmd))
        try:
            run_subprocess(cmd, cwd=cwd, timeout=timeout, check=True)
        except subprocess.TimeoutExpired as exc:
            msg = f"COLMAP stage '{step_name}' timed out after {timeout}s: {' '.join(cmd)}"
            logger.error(msg)
            raise ReconstructionTimeoutError(msg) from exc
        except subprocess.CalledProcessError as exc:
            stderr_snippet = exc.stderr[:500] if exc.stderr else ""
            msg = (
                f"COLMAP stage '{step_name}' failed with exit code {exc.returncode}.\n"
                f"Command: {' '.join(cmd)}\n"
                f"Stderr: {stderr_snippet}"
            )
            logger.error(msg)
            raise ReconstructionExecutionError(msg) from exc
        except Exception as exc:
            msg = f"COLMAP stage '{step_name}' encountered unexpected failure: {exc}"
            logger.error(msg)
            raise ReconstructionExecutionError(msg) from exc

    # -------------------------------------------------------------------------
    # Full Engine Interface Implementation
    # -------------------------------------------------------------------------

    def reconstruct(
        self,
        frame_paths: Sequence[Path],
        config: ReconstructionJobConfig,
        sequential: bool | None = None,
    ) -> ReconstructionResult:
        """Execute COLMAP reconstruction workflow on input keyframes.

        Args:
            frame_paths: Sequence of keyframe image paths to process.
            config: Job configuration settings.
            sequential: If True, enforces sequential matching (optimized for video).
                        If None, resolves from config.sequential or config.extra_params.

        Returns:
            ReconstructionResult with paths to artifacts and execution status.
        """
        if not frame_paths:
            raise ReconstructionInvalidInputError("Cannot reconstruct from an empty list of frames.")

        valid_frames: list[Path] = []
        for p in frame_paths:
            resolved = Path(p).resolve()
            if not resolved.is_file():
                raise ReconstructionInvalidInputError(f"Input frame does not exist: {p}")
            valid_frames.append(resolved)

        bin_path = self.resolve_binary(config.binary_path)
        if bin_path is None:
            raise ReconstructionBinaryNotFoundError(
                f"COLMAP binary not found for reconstruction job."
            )

        workspace_dir = ensure_directory(config.workspace_dir)
        images_dir = ensure_directory(workspace_dir / "images")
        sparse_dir = ensure_directory(workspace_dir / "sparse")
        database_path = workspace_dir / "database.db"

        # Determine if turbo mode is enabled
        is_turbo = (
            getattr(config, "turbo", False)
            or str(config.extra_params.get("turbo", "false")).lower() in {"true", "1", "yes"}
        )

        # Determine if sequential matching is requested
        is_sequential = False
        matching_mode = config.extra_params.get("matching_mode")
        if is_turbo:
            is_sequential = True
        elif matching_mode is not None:
            is_sequential = matching_mode.lower() == "sequential"
        elif sequential is not None:
            is_sequential = bool(sequential)
        elif getattr(config, "sequential", False):
            is_sequential = True
        elif str(config.extra_params.get("sequential", "false")).lower() in {"true", "1", "yes"}:
            is_sequential = True

        mode_str = "sequential" if is_sequential else "exhaustive"

        # Copy frames into workspace/images
        for frame in valid_frames:
            dest = images_dir / frame.name
            if not dest.exists():
                shutil.copy2(frame, dest)

        start_time = time.time()
        timeout = config.timeout_seconds

        # 1. Feature extraction
        cmd_extract = self.build_feature_extractor_args(
            binary_path=bin_path,
            database_path=database_path,
            image_path=images_dir,
            additional_args=config.additional_args or None,
        )
        self._execute_step("feature_extractor", cmd_extract, cwd=workspace_dir, timeout=timeout)

        overlap_param = int(config.extra_params["overlap"]) if "overlap" in config.extra_params else None

        # 2. Feature Matching (Sequential for video; Exhaustive otherwise)
        self.run_matching(
            database_path=database_path,
            sequential=is_sequential,
            matching_mode=mode_str,
            binary_path=bin_path,
            overlap=overlap_param,
            timeout_seconds=timeout,
            turbo=is_turbo,
            cwd=workspace_dir,
            additional_args=config.additional_args or None,
        )

        # 3. Mapper (SfM with 16 threads, 20 global BA iterations, 15 local BA iterations; 12/10 in turbo)
        self.run_mapper(
            database_path=database_path,
            image_path=images_dir,
            output_path=sparse_dir,
            binary_path=bin_path,
            num_threads=16,
            ba_global_max_num_iterations=15 if is_turbo else 20,
            ba_local_max_num_iterations=12 if is_turbo else 15,
            timeout_seconds=timeout,
            turbo=is_turbo,
            cwd=workspace_dir,
            additional_args=config.additional_args or None,
        )

        model_sparse = self.resolve_sparse_model_dir(sparse_dir)

        # SfM Circuit Breaker: inspect images.bin / images.txt for registered camera tracking count
        candidates = [model_sparse, sparse_dir, sparse_dir / "0"]
        img_bin = None
        img_txt = None
        for cand in candidates:
            if (cand / "images.bin").is_file():
                img_bin = cand / "images.bin"
                break
            elif (cand / "images.txt").is_file():
                img_txt = cand / "images.txt"
                break

        reg_count = 0
        checked_sfm = False
        if img_bin is not None and img_bin.is_file():
            checked_sfm = True
            try:
                import struct
                with open(img_bin, "rb") as f:
                    reg_count = struct.unpack("<Q", f.read(8))[0]
            except Exception as e:
                logger.warning("Could not read registered image count from %s: %s", img_bin, e)
        elif img_txt is not None and img_txt.is_file():
            checked_sfm = True
            try:
                with open(img_txt, "r", encoding="utf-8", errors="ignore") as f:
                    reg_count = sum(1 for line in f if line.strip() and not line.startswith("#")) // 2
            except Exception as e:
                logger.warning("Could not read registered image count from %s: %s", img_txt, e)

        if checked_sfm:
            total_frames = len(valid_frames)
            logger.info("SfM registered %d / %d views (%.1f%%)", reg_count, total_frames, (reg_count / total_frames * 100) if total_frames > 0 else 0)
            if total_frames > 0 and (reg_count / total_frames) < 0.75:
                raise RuntimeError("SfM tracking lost: insufficient overlap or texture. Aborting to prevent invalid geometry.")

        # Check if sparse_only or dense was requested in extra_params
        sparse_only = str(config.extra_params.get("sparse_only", "false")).lower() in {"true", "1", "yes"}
        is_dense = str(config.extra_params.get("dense", "false")).lower() in {"true", "1", "yes"}

        if sparse_only:
            mesh_path = None
            point_cloud = None
        elif is_dense:
            dense_artifact = self.reconstruct_dense(
                image_dir=images_dir,
                sparse_dir=model_sparse,
                output_dir=workspace_dir / "dense",
                binary_path=bin_path,
                timeout_seconds=timeout,
                turbo=is_turbo,
            )
            mesh_path = dense_artifact.mesh_path
            point_cloud = dense_artifact.isolated_point_cloud_path or dense_artifact.dense_point_cloud_path
        else:
            sparse_artifact = self.reconstruct_sparse_mesh(
                sparse_dir=model_sparse,
                output_path=workspace_dir / "meshed-delaunay.ply",
                binary_path=bin_path,
                timeout_seconds=timeout,
            )
            mesh_path = sparse_artifact.mesh_path
            point_cloud = None

        elapsed_time = round(time.time() - start_time, 2)
        success = (mesh_path is not None and mesh_path.is_file()) or (
            sparse_only and (model_sparse.is_dir() and (any(model_sparse.glob("*.bin")) or any(model_sparse.glob("*.txt"))))
        )

        return ReconstructionResult(
            success=success,
            status=ReconstructionStatus.SUCCESS if success else ReconstructionStatus.PROCESS_FAILED,
            backend_name=self.backend_name,
            mesh_path=mesh_path,
            point_cloud_path=point_cloud,
            sparse_reconstruction_path=model_sparse,
            dense_point_cloud_path=point_cloud if is_dense else None,
            execution_time_seconds=elapsed_time,
            input_frames_count=len(valid_frames),
            workspace_dir=workspace_dir,
        )

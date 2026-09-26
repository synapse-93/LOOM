"""Production-quality Meshroom / AliceVision photogrammetry engine adapter."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Sequence

from loom.reconstruction.base import ReconstructionEngine
from loom.reconstruction.exceptions import (
    ReconstructionArtifactNotFoundError,
    ReconstructionBinaryNotFoundError,
    ReconstructionExecutionError,
)
from loom.reconstruction.models import ReconstructionJobConfig, ReconstructionResult
from loom.utils.paths import ensure_directory

logger = logging.getLogger(__name__)


class MeshroomAdapter(ReconstructionEngine):
    """Adapter for Meshroom / AliceVision CLI photogrammetry pipeline.

    Manages subprocess execution of `meshroom_batch`, workspace layout,
    safe timeout handling, stdout/stderr logging, and controlled discovery of
    output 3D meshes, dense point clouds, and registered camera poses.
    """

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

    def __init__(self, binary_path: str | Path | None = None) -> None:
        """Initialize MeshroomAdapter.

        Args:
            binary_path: Optional explicit path to meshroom_batch executable.
                         If None, searches PATH or 'MESHROOM_PATH' env var.
        """
        if binary_path is not None:
            self._binary_path: Optional[str] = str(binary_path)
        elif "MESHROOM_PATH" in os.environ:
            self._binary_path = os.environ["MESHROOM_PATH"]
        elif "MESHROOM_BIN" in os.environ:
            self._binary_path = os.environ["MESHROOM_BIN"]
        else:
            self._binary_path = None

    @property
    def backend_name(self) -> str:
        return "meshroom"

    @property
    def binary_path(self) -> Optional[Path]:
        """Configured path to meshroom_batch executable, if any."""
        return Path(self._binary_path) if self._binary_path is not None else None

    def resolve_binary(self, override_path: Path | None = None) -> Optional[Path]:
        """Resolve executable path, checking overrides, local paths, and PATH.

        Args:
            override_path: Optional per-job binary override.

        Returns:
            Resolved Path to executable if found, else None.
        """
        target = str(override_path) if override_path else (self._binary_path if self._binary_path else "meshroom_batch")

        # Direct absolute/relative file path check
        p = Path(target)
        if p.is_file():
            return p.resolve()

        # Check if target is a directory containing meshroom_batch
        if p.is_dir():
            candidates = [p / "meshroom_batch.exe", p / "meshroom_batch"]
            for c in candidates:
                if c.is_file():
                    return c.resolve()

        # Check system PATH
        which_path = shutil.which(target)
        if which_path is not None:
            return Path(which_path).resolve()

        return None

    def is_available(self, override_path: Path | None = None) -> bool:
        """Check if meshroom_batch executable is available on the host system."""
        return self.resolve_binary(override_path) is not None

    def build_command(
        self,
        binary_path: Path,
        input_dir: Path,
        output_dir: Path,
        cache_dir: Path | None = None,
        config: ReconstructionJobConfig | None = None,
    ) -> list[str]:
        """Construct the CLI command for meshroom_batch with explicit argument list.

        Args:
            binary_path: Resolved path to meshroom_batch.
            input_dir: Path to directory containing input frames.
            output_dir: Path to directory where output artifacts will be written.
            cache_dir: Optional path to node computation cache directory.
            config: Job configuration settings.

        Returns:
            List of command-line arguments suitable for subprocess.run(..., shell=False).
        """
        cmd: list[str] = [
            str(binary_path),
            "--input",
            str(input_dir.resolve()),
            "--output",
            str(output_dir.resolve()),
        ]

        if cache_dir is not None:
            cmd.extend(["--cache", str(cache_dir.resolve())])

        if config is not None:
            # Append additional positional or flag arguments
            if config.additional_args:
                cmd.extend(config.additional_args)

            # Append custom extra parameter overrides (--paramName value)
            if config.extra_params:
                for k, v in config.extra_params.items():
                    flag = k if k.startswith("-") else f"--{k}"
                    cmd.extend([flag, str(v)])

        return cmd

    @staticmethod
    def parse_camera_sfm(sfm_path: Path) -> tuple[Optional[int], Optional[float]]:
        """Extract camera registration count and ratio from AliceVision cameras.sfm.

        Args:
            sfm_path: Path to cameras.sfm (JSON format).

        Returns:
            Tuple of (registered_cameras_count, registration_ratio), or (None, None) if unreadable.
        """
        if not sfm_path.is_file():
            return None, None

        try:
            with open(sfm_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            views = data.get("views", [])
            poses = data.get("poses", [])

            view_count = len(views)
            pose_count = len(poses)

            if view_count > 0:
                ratio = round(pose_count / view_count, 3)
                return pose_count, ratio
            return pose_count, None
        except Exception as e:
            logger.warning("Failed to parse camera registration from %s: %s", sfm_path, e)
            return None, None

    @staticmethod
    def discover_output_artifacts(
        output_dir: Path,
        cache_dir: Path | None = None,
    ) -> tuple[Optional[Path], Optional[Path], Optional[Path]]:
        """Search output and cache directories for generated mesh, point cloud, and camera poses.

        Discovery order for 3D Mesh:
            1. Textured mesh in output directory (`texturedMesh.obj` / `.ply`)
            2. Top-level mesh (`mesh.obj` / `.ply`)
            3. Texturing node output in cache/output (`Texturing/**/texturedMesh.obj`)
            4. MeshFiltering / Meshing node output (`MeshFiltering/**/mesh.obj`, `Meshing/**/mesh.obj`)

        Returns:
            Tuple of (mesh_path, point_cloud_path, camera_poses_path).
        """
        mesh_path: Optional[Path] = None
        point_cloud_path: Optional[Path] = None
        camera_poses_path: Optional[Path] = None

        search_dirs: list[Path] = [output_dir]
        if cache_dir and cache_dir.is_dir():
            search_dirs.append(cache_dir)

        # 1. Search for reconstructed 3D mesh
        direct_mesh_names = [
            "texturedMesh.obj",
            "texturedMesh.ply",
            "mesh.obj",
            "mesh.ply",
        ]
        for sdir in search_dirs:
            for name in direct_mesh_names:
                candidate = sdir / name
                if candidate.is_file() and candidate.stat().st_size > 0:
                    mesh_path = candidate.resolve()
                    break
            if mesh_path:
                break

        # If not found directly, perform recursive search within search directories
        if mesh_path is None:
            candidate_meshes: list[Path] = []
            for sdir in search_dirs:
                if sdir.is_dir():
                    for ext in ("*.obj", "*.ply"):
                        for f in sdir.rglob(ext):
                            # Ignore camera/pointcloud files
                            if (
                                f.is_file()
                                and f.stat().st_size > 0
                                and "cloud" not in f.name.lower()
                                and "pose" not in f.name.lower()
                            ):
                                candidate_meshes.append(f)

            if candidate_meshes:
                # Prefer textured meshes first, then filtered meshes, then deepest/latest
                textured = [m for m in candidate_meshes if "textured" in m.name.lower()]
                if textured:
                    mesh_path = textured[0].resolve()
                else:
                    filtered = [m for m in candidate_meshes if "filter" in str(m).lower()]
                    if filtered:
                        mesh_path = filtered[0].resolve()
                    else:
                        mesh_path = candidate_meshes[0].resolve()

        # 2. Search for dense/sparse point cloud
        pc_names = [
            "cloud_and_poses.ply",
            "densePointCloud.ply",
            "pointCloud.ply",
            "pointcloud.ply",
        ]
        for sdir in search_dirs:
            for name in pc_names:
                candidate = sdir / name
                if candidate.is_file() and candidate.stat().st_size > 0:
                    point_cloud_path = candidate.resolve()
                    break
            if point_cloud_path:
                break

        if point_cloud_path is None:
            for sdir in search_dirs:
                if sdir.is_dir():
                    for f in sdir.rglob("*.ply"):
                        if (
                            f.is_file()
                            and f.stat().st_size > 0
                            and ("cloud" in f.name.lower() or "sfm" in str(f).lower())
                        ):
                            point_cloud_path = f.resolve()
                            break
                if point_cloud_path:
                    break

        # 3. Search for camera trajectory / poses
        pose_names = ["cameras.sfm", "sfm.abc", "sfm.json"]
        for sdir in search_dirs:
            for name in pose_names:
                candidate = sdir / name
                if candidate.is_file() and candidate.stat().st_size > 0:
                    camera_poses_path = candidate.resolve()
                    break
            if camera_poses_path:
                break

        if camera_poses_path is None:
            for sdir in search_dirs:
                if sdir.is_dir():
                    for f in sdir.rglob("cameras.sfm"):
                        if f.is_file() and f.stat().st_size > 0:
                            camera_poses_path = f.resolve()
                            break
                if camera_poses_path:
                    break

        return mesh_path, point_cloud_path, camera_poses_path

    def reconstruct(
        self,
        frame_paths: Sequence[Path],
        config: ReconstructionJobConfig,
    ) -> ReconstructionResult:
        """Execute Meshroom reconstruction on input keyframes.

        Args:
            frame_paths: Sequence of keyframe image paths to process.
            config: Job configuration settings.

        Returns:
            ReconstructionResult with paths to artifacts and execution metrics.

        Raises:
            ReconstructionBinaryNotFoundError: If meshroom_batch executable is missing.
            ValueError: If input frame list is empty or frames are unreadable.
            ReconstructionExecutionError: If subprocess fails with non-zero exit code.
            TimeoutError: If execution exceeds configured timeout.
        """
        # 1. Check input frames
        if not frame_paths:
            raise ValueError("Cannot reconstruct 3D scene from an empty list of frames.")

        valid_frames: list[Path] = []
        for p in frame_paths:
            resolved = Path(p).resolve()
            if not resolved.is_file():
                raise FileNotFoundError(f"Input frame does not exist: {p}")
            if resolved.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                raise ValueError(f"Unsupported image format for reconstruction: {resolved.suffix}")
            valid_frames.append(resolved)

        # 2. Check binary availability
        bin_path = self.resolve_binary(config.binary_path)
        if bin_path is None:
            target_desc = str(config.binary_path) if config.binary_path else (str(self._binary_path) if self._binary_path else "meshroom_batch")
            raise ReconstructionBinaryNotFoundError(
                f"Meshroom executable '{target_desc}' not found. "
                "Ensure Meshroom is installed and 'meshroom_batch' is in PATH, "
                "or specify 'binary_path' in ReconstructionConfig."
            )

        # 3. Setup workspace directory layout
        workspace_dir = ensure_directory(config.workspace_dir)
        input_dir = ensure_directory(workspace_dir / "input")
        output_dir = ensure_directory(workspace_dir / "output")
        cache_dir = ensure_directory(workspace_dir / "cache")
        logs_dir = ensure_directory(workspace_dir / "logs")
        log_file = logs_dir / "reconstruction.log"

        # Copy or symlink valid frames into workspace/input
        for src_frame in valid_frames:
            dest_frame = input_dir / src_frame.name
            if not dest_frame.exists():
                try:
                    shutil.copy2(src_frame, dest_frame)
                except Exception:
                    # Fallback to copy if symlink unsupported
                    shutil.copy2(src_frame, dest_frame)

        # 4. Construct command
        cmd = self.build_command(
            binary_path=bin_path,
            input_dir=input_dir,
            output_dir=output_dir,
            cache_dir=cache_dir,
            config=config,
        )

        logger.info(
            "Starting Meshroom 3D reconstruction (%d input frames, quality=%s, timeout=%ds)",
            len(valid_frames),
            config.quality_preset,
            config.timeout_seconds,
        )
        logger.info("Reconstruction command: %s", " ".join(cmd))

        start_time = time.time()
        log_lines: list[str] = []

        # 5. Execute subprocess with streaming log capture
        try:
            with open(log_file, "w", encoding="utf-8") as lf:
                lf.write(f"=== Meshroom Reconstruction Invocation ===\n")
                lf.write(f"Command: {' '.join(cmd)}\n")
                lf.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                lf.flush()

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    shell=False,
                    cwd=str(workspace_dir),
                )

                try:
                    stdout_data, _ = proc.communicate(timeout=config.timeout_seconds)
                    if stdout_data:
                        for line in stdout_data.splitlines(keepends=True):
                            log_lines.append(line)
                            lf.write(line)
                            striped = line.strip()
                            if striped.startswith("[") and "]" in striped:
                                logger.info("Meshroom progress: %s", striped[:120])
                            elif "error" in striped.lower() or "fail" in striped.lower():
                                logger.warning("Meshroom warning/error: %s", striped[:120])
                        lf.flush()
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        out, _ = proc.communicate(timeout=5)
                        if out:
                            for line in out.splitlines(keepends=True):
                                log_lines.append(line)
                                lf.write(line)
                            lf.flush()
                    except Exception:
                        pass
                    err_msg = (
                        f"Meshroom reconstruction timed out after {config.timeout_seconds} seconds."
                    )
                    logger.error(err_msg)
                    raise ReconstructionExecutionError(err_msg)

            elapsed_time = round(time.time() - start_time, 2)

            if proc.returncode != 0:
                recent_logs = "".join(log_lines[-20:])
                err_msg = (
                    f"Meshroom exited with non-zero return code {proc.returncode}. "
                    f"Last log output:\n{recent_logs}"
                )
                logger.error(err_msg)
                raise ReconstructionExecutionError(err_msg)

        except ReconstructionExecutionError:
            raise
        except Exception as e:
            elapsed_time = round(time.time() - start_time, 2)
            err_msg = f"Unexpected error during Meshroom execution: {e}"
            logger.error(err_msg)
            return ReconstructionResult(
                mesh_path=None,
                point_cloud_path=None,
                camera_poses_path=None,
                success=False,
                backend_name=self.backend_name,
                execution_time_seconds=elapsed_time,
                log_output="".join(log_lines[-100:]),
                error_message=err_msg,
                input_frames_count=len(valid_frames),
            )

        # 6. Discover and validate output artifacts
        mesh_path, point_cloud_path, camera_poses_path = self.discover_output_artifacts(
            output_dir=output_dir,
            cache_dir=cache_dir,
        )

        # Extract camera registration stats if poses are available
        registered_count: Optional[int] = None
        reg_ratio: Optional[float] = None
        if camera_poses_path and camera_poses_path.suffix.lower() == ".sfm":
            registered_count, reg_ratio = self.parse_camera_sfm(camera_poses_path)

        success = mesh_path is not None and mesh_path.is_file() and mesh_path.stat().st_size > 0

        error_message: Optional[str] = None
        if not success:
            error_message = (
                "Meshroom execution completed, but no non-empty 3D mesh artifact "
                f"was found in {output_dir}."
            )
            logger.error(error_message)

        logger.info(
            "Meshroom reconstruction finished in %.2fs (success=%s, mesh=%s, cameras=%s/%s)",
            elapsed_time,
            success,
            mesh_path.name if mesh_path else "None",
            registered_count,
            len(valid_frames),
        )

        return ReconstructionResult(
            mesh_path=mesh_path,
            point_cloud_path=point_cloud_path,
            camera_poses_path=camera_poses_path,
            success=success,
            backend_name=self.backend_name,
            execution_time_seconds=elapsed_time,
            log_output="".join(log_lines[-100:]),
            error_message=error_message,
            input_frames_count=len(valid_frames),
            registered_cameras_count=registered_count,
            registration_ratio=reg_ratio,
        )

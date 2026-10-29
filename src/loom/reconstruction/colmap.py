"""COLMAP Structure-from-Motion and Multi-View Stereo adapter.

The adapter deliberately uses COLMAP's command-line interface instead of
``pycolmap`` so the core project does not acquire platform-specific bindings.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import time
from pathlib import Path
from typing import Sequence

from loom.reconstruction.base import ReconstructionEngine
from loom.reconstruction.exceptions import (
    ReconstructionArtifactNotFoundError,
    ReconstructionBinaryNotFoundError,
    ReconstructionExecutionError,
    ReconstructionInvalidInputError,
    ReconstructionTimeoutError,
)
from loom.reconstruction.models import ReconstructionJobConfig, ReconstructionResult, ReconstructionStatus
from loom.utils.paths import ensure_directory

logger = logging.getLogger(__name__)


class ColmapAdapter(ReconstructionEngine):
    """Run COLMAP feature extraction, SfM, MVS, and Poisson / Delaunay meshing."""

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

    SUBCOMMAND_OPTION_PREFIXES = {
        "feature_extractor": ("--FeatureExtraction.", "--ImageReader.", "--SiftExtraction."),
        "exhaustive_matcher": ("--FeatureMatching.", "--ExhaustiveMatching.", "--SiftMatching."),
        "mapper": ("--Mapper.", "--IncrementalMapper."),
        "patch_match_stereo": ("--PatchMatchStereo."),
        "stereo_fusion": ("--StereoFusion."),
        "poisson_mesher": ("--PoissonMeshing."),
        "delaunay_mesher": ("--DelaunayMeshing."),
    }

    @classmethod
    def _extract_subcommand_args(cls, subcommand: str, additional_args: Sequence[str]) -> list[str]:
        """Extract and forward only additional arguments matching the target COLMAP subcommand."""
        if not additional_args:
            return []
        prefixes = cls.SUBCOMMAND_OPTION_PREFIXES.get(subcommand, ())
        subcmd_prefix = f"--{subcommand}."
        routed: list[str] = []
        i = 0
        n = len(additional_args)
        while i < n:
            token = str(additional_args[i])
            if token.startswith("--"):
                matches = False
                matched_token = token
                if token.startswith(subcmd_prefix):
                    matches = True
                    matched_token = "--" + token[len(subcmd_prefix):]
                elif any(token.startswith(p) for p in prefixes):
                    matches = True

                if matches:
                    routed.append(matched_token)
                    if i + 1 < n and not str(additional_args[i + 1]).startswith("--"):
                        i += 1
                        routed.append(str(additional_args[i]))
            i += 1
        return routed

    def __init__(
        self,
        binary_path: str | Path = "colmap",
        *,
        has_gpu_support: bool | None = None,
        can_run_dense: bool | None = None,
        allow_fallback: bool = True,
    ) -> None:
        self._binary_path = str(binary_path) if binary_path is not None else "colmap"
        self.allow_fallback = allow_fallback
        self._capabilities: dict[str, bool] | None = None
        if has_gpu_support is not None:
            dense = can_run_dense if can_run_dense is not None else has_gpu_support
            self._capabilities = {
                "has_gpu": has_gpu_support,
                "has_cuda": has_gpu_support,
                "can_run_dense": dense,
            }

    @property
    def backend_name(self) -> str:
        return "colmap"

    def resolve_binary(self, override_path: str | Path | None = None) -> Path | None:
        """Resolve an explicit COLMAP executable path, directory, or a PATH entry.

        Supports:
        - Direct executable path (e.g. ``C:\\Tools\\COLMAP\\bin\\colmap.exe``).
        - Directory containing ``colmap.exe`` or ``colmap``.
        - Installation directory containing ``bin/colmap.exe`` or ``bin/colmap``.
        - System ``PATH`` resolution.
        """
        target = str(override_path) if override_path is not None else self._binary_path
        if not target:
            target = "colmap"
        candidate = Path(target).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        if candidate.is_dir():
            names = ("colmap.exe", "colmap", "colmap.bat", "colmap.cmd")
            for name in names:
                executable = candidate / name
                if executable.is_file():
                    return executable.resolve()
            for name in names:
                executable = candidate / "bin" / name
                if executable.is_file():
                    return executable.resolve()
        found = shutil.which(target)
        return Path(found).resolve() if found else None

    def is_available(self) -> bool:
        """Return whether the configured COLMAP executable can be resolved."""
        return self.resolve_binary() is not None

    @staticmethod
    def discover_qt_plugin_path(binary: Path) -> Path | None:
        """Discover the Qt platform plugin directory relative to colmap executable."""
        candidates = [
            binary.parent.parent / "plugins" / "platforms",
            binary.parent / "plugins" / "platforms",
            binary.parent.parent / "platforms",
            binary.parent / "platforms",
        ]
        for candidate in candidates:
            if candidate.is_dir():
                if (candidate / "qwindows.dll").is_file() or any(candidate.glob("*.dll")) or any(candidate.glob("*.so")):
                    return candidate.resolve()
        return None

    def get_subprocess_env(self, binary: Path) -> dict[str, str]:
        """Construct subprocess environment, ensuring Qt platform plugins can be resolved on Windows.

        Preserves unrelated environment variables and respects any valid, user-supplied
        QT_QPA_PLATFORM_PLUGIN_PATH already in the environment.
        """
        env = os.environ.copy()
        existing = env.get("QT_QPA_PLATFORM_PLUGIN_PATH")
        if existing and Path(existing).is_dir():
            return env
        qt_path = self.discover_qt_plugin_path(binary)
        if qt_path is not None:
            env["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(qt_path)
        return env

    def probe_capabilities(self, binary: Path, env: dict[str, str] | None = None) -> dict[str, bool]:
        """Probe the COLMAP binary to detect GPU/CUDA and dense MVS capabilities."""
        if self._capabilities is not None:
            return self._capabilities

        has_gpu = False
        can_run_dense = False
        try:
            cmd_env = env or self.get_subprocess_env(binary)
            proc = subprocess.run(
                [str(binary), "version"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
                env=cmd_env,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            if not output:
                proc = subprocess.run(
                    [str(binary), "help"],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    check=False,
                    env=cmd_env,
                )
                output = (proc.stdout or "") + (proc.stderr or "")

            output_lower = output.lower()
            if "without gpu support" in output_lower or "without cuda" in output_lower:
                has_gpu = False
                can_run_dense = False
            else:
                has_gpu = True
                can_run_dense = True
        except Exception as exc:
            logger.debug("Failed to probe COLMAP binary capabilities: %s", exc)
            has_gpu = False
            can_run_dense = False

        self._capabilities = {
            "has_gpu": has_gpu,
            "has_cuda": has_gpu,
            "can_run_dense": can_run_dense,
        }
        return self._capabilities

    @staticmethod
    def _nonempty_file(path: Path | None) -> bool:
        return path is not None and path.is_file() and path.stat().st_size > 0

    @staticmethod
    def _validate_ply_mesh(path: Path) -> bool:
        """Validate that a generated PLY mesh exists, is non-empty, and has vertices and faces."""
        if not path.is_file() or path.stat().st_size == 0:
            return False
        try:
            with open(path, "rb") as f:
                header_bytes = f.read(65536)
            header_text = header_bytes.decode("ascii", errors="ignore")
            if not header_text.startswith("ply"):
                return False
            vertex_count = 0
            face_count = 0
            for line in header_text.splitlines():
                line_str = line.strip()
                if line_str.startswith("element vertex"):
                    parts = line_str.split()
                    if len(parts) >= 3:
                        vertex_count = int(parts[2])
                elif line_str.startswith("element face"):
                    parts = line_str.split()
                    if len(parts) >= 3:
                        face_count = int(parts[2])
                elif line_str == "end_header":
                    break
            return vertex_count > 0 and face_count > 0
        except Exception:
            return False

    @staticmethod
    def _parse_ply_point_count(path: Path) -> int:
        """Parse vertex count from PLY header."""
        if not path.is_file():
            return 0
        try:
            with open(path, "rb") as f:
                header_bytes = f.read(4096)
            header_text = header_bytes.decode("ascii", errors="ignore")
            for line in header_text.splitlines():
                line_str = line.strip()
                if line_str.startswith("element vertex"):
                    parts = line_str.split()
                    if len(parts) >= 3:
                        return int(parts[2])
                elif line_str == "end_header":
                    break
            return 0
        except Exception:
            return 0

    @staticmethod
    def _count_database_matches(database_path: Path) -> int:
        """Count verified image pair matches recorded in the COLMAP SQLite database."""
        if not database_path.is_file():
            return 0
        try:
            with sqlite3.connect(str(database_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {row[0] for row in cursor.fetchall()}
                count = 0
                if "two_view_geometries" in tables:
                    try:
                        cursor.execute("SELECT count(*) FROM two_view_geometries WHERE rows > 0")
                        count = cursor.fetchone()[0]
                    except sqlite3.OperationalError:
                        pass
                if count == 0 and "matches" in tables:
                    try:
                        cursor.execute("SELECT count(*) FROM matches WHERE rows > 0")
                        count = cursor.fetchone()[0]
                    except sqlite3.OperationalError:
                        pass
                return count
        except Exception:
            return 0

    @staticmethod
    def _get_model_stats(model_dir: Path) -> tuple[int, int]:
        """Return (num_registered_images, num_points) for a sparse model directory.

        Supports COLMAP binary models (.bin) and text models (.txt), with safe fallback
        for mock files or partial models.
        """
        if not model_dir.is_dir():
            return 0, 0

        num_images = 0
        num_points = 0

        img_bin = model_dir / "images.bin"
        pts_bin = model_dir / "points3D.bin"

        if img_bin.is_file() and img_bin.stat().st_size >= 8:
            try:
                with open(img_bin, "rb") as f:
                    num_images = struct.unpack("<Q", f.read(8))[0]
            except Exception:
                num_images = 0
        elif (model_dir / "images.txt").is_file():
            try:
                with open(model_dir / "images.txt", "r", errors="ignore") as f:
                    lines = [l for l in f if l.strip() and not l.startswith("#")]
                    num_images = len(lines) // 2
            except Exception:
                num_images = 0

        if pts_bin.is_file() and pts_bin.stat().st_size >= 8:
            try:
                with open(pts_bin, "rb") as f:
                    num_points = struct.unpack("<Q", f.read(8))[0]
            except Exception:
                num_points = 0
        elif (model_dir / "points3D.txt").is_file():
            try:
                with open(model_dir / "points3D.txt", "r", errors="ignore") as f:
                    num_points = sum(1 for l in f if l.strip() and not l.startswith("#"))
            except Exception:
                num_points = 0

        return num_images, num_points

    @staticmethod
    def _has_matcher_fatal_error(output: str) -> bool:
        """Detect fatal errors in matcher output that may exit with return code 0."""
        patterns = (
            "not enough gpu memory",
            "failed to create feature matcher",
            "failed to create sift gpu feature matcher",
            "cuda out of memory",
            "failed to initialize siftgpu",
            "siftgpu failed",
            "cuda error",
        )
        lower = output.lower()
        return any(p in lower for p in patterns)

    @staticmethod
    def _run_command(
        command: list[str],
        *,
        cwd: Path,
        log_file: Path,
        timeout_seconds: float,
        log_chunks: list[str],
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one COLMAP command, append combined output to the run log."""
        logger.info("COLMAP stage: %s", " ".join(command))
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
                timeout=max(0.1, timeout_seconds),
                shell=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            chunk = f"\n$ {' '.join(command)}\n{stdout}\n{stderr}\n[TIMEOUT]\n"
            log_chunks.append(chunk)
            log_file.write_text("".join(log_chunks), encoding="utf-8")
            raise ReconstructionTimeoutError(
                f"COLMAP command timed out after {timeout_seconds:.1f}s: {command[1] if len(command) > 1 else command[0]}"
            ) from exc

        chunk = (
            f"\n$ {' '.join(command)}\n"
            f"[return_code={completed.returncode}]\n"
            f"{completed.stdout or ''}\n{completed.stderr or ''}\n"
        )
        log_chunks.append(chunk)
        log_file.write_text("".join(log_chunks), encoding="utf-8")
        if completed.returncode != 0:
            tail = "".join(log_chunks)[-5000:]
            raise ReconstructionExecutionError(
                f"COLMAP command '{command[1] if len(command) > 1 else command[0]}' "
                f"failed with exit code {completed.returncode}. Log tail:\n{tail}"
            )
        return completed

    def reconstruct(
        self,
        frame_paths: Sequence[Path],
        config: ReconstructionJobConfig,
    ) -> ReconstructionResult:
        """Execute a complete COLMAP reconstruction and return discovered artifacts.

        Supports standard CPU-compatible pipeline (feature extraction -> matching ->
        mapper -> model_converter -> delaunay_mesher) and optional dense MVS (PatchMatch
        stereo -> fusion -> Poisson meshing) when the binary has CUDA/HIP capabilities.
        """
        started = time.monotonic()
        if not frame_paths:
            raise ReconstructionInvalidInputError("Cannot reconstruct 3D scene from an empty list of frames.")

        valid_frames: list[Path] = []
        for item in frame_paths:
            path = Path(item).expanduser().resolve()
            if not path.is_file():
                raise ReconstructionInvalidInputError(f"Input frame does not exist: {item}")
            if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                raise ReconstructionInvalidInputError(f"Unsupported image format for reconstruction: {path.suffix}")
            valid_frames.append(path)

        binary = self.resolve_binary(config.binary_path)
        if binary is None:
            target = config.binary_path or self._binary_path
            raise ReconstructionBinaryNotFoundError(
                f"COLMAP executable '{target}' not found. Install COLMAP and add it to PATH, "
                "or pass its executable path as the reconstruction binary path."
            )

        env = self.get_subprocess_env(binary)
        capabilities = self.probe_capabilities(binary, env=env)
        has_gpu = capabilities["has_gpu"]
        can_run_dense = capabilities["can_run_dense"]

        workspace = ensure_directory(Path(config.workspace_dir).resolve())
        images_dir = workspace / "images"
        sparse_dir = workspace / "sparse"
        dense_dir = workspace / "dense"
        database_path = workspace / "database.db"
        for generated_path in (images_dir, sparse_dir, dense_dir):
            if generated_path.is_dir():
                shutil.rmtree(generated_path)
            elif generated_path.exists():
                generated_path.unlink()
        if database_path.exists():
            database_path.unlink()
        ensure_directory(images_dir)
        ensure_directory(sparse_dir)
        logs_dir = ensure_directory(workspace / "logs")
        log_file = logs_dir / "reconstruction.log"
        log_chunks = [
            "=== COLMAP Reconstruction ===\n",
            f"Executable: {binary}\n",
            f"Input frames: {len(valid_frames)}\n",
            f"Workspace: {workspace}\n",
            f"Capabilities: GPU={has_gpu}, DenseMVS={can_run_dense}\n",
        ]

        seen: set[str] = set()
        for index, source in enumerate(valid_frames):
            name = source.name
            if name.casefold() in seen:
                name = f"{index:05d}_{name}"
            seen.add(name.casefold())
            destination = images_dir / name
            if source != destination.resolve():
                shutil.copy2(source, destination)

        image_reader_model = "SIMPLE_RADIAL" if config.camera_model.lower() in {"pinhole", "simple_radial"} else config.camera_model
        quality = config.quality_preset.lower()
        if quality not in {"low", "medium", "high"}:
            quality = "medium"
        max_image_size = {"low": "1600", "medium": "2400", "high": "3200"}[quality]

        def remaining_timeout() -> float:
            rem = config.timeout_seconds - (time.monotonic() - started)
            if rem <= 0:
                raise ReconstructionTimeoutError(
                    f"COLMAP reconstruction exceeded total timeout of {config.timeout_seconds}s."
                )
            return rem

        # Stage 1: Feature Extraction
        feature_cmd = [
            str(binary), "feature_extractor",
            "--database_path", str(database_path),
            "--image_path", str(images_dir),
            "--ImageReader.single_camera", "1",
            "--ImageReader.camera_model", image_reader_model,
        ]
        if not has_gpu:
            feature_cmd.extend(["--FeatureExtraction.use_gpu", "0"])
        feature_cmd.extend(self._extract_subcommand_args("feature_extractor", config.additional_args))

        self._run_command(
            feature_cmd,
            cwd=workspace,
            log_file=log_file,
            timeout_seconds=remaining_timeout(),
            log_chunks=log_chunks,
            env=env,
        )

        # Stage 2: Feature Matching (with GPU -> CPU fallback and silent-failure detection)
        matcher_cmd = [
            str(binary), "exhaustive_matcher",
            "--database_path", str(database_path),
        ]
        if not has_gpu:
            matcher_cmd.extend(["--FeatureMatching.use_gpu", "0"])
        matcher_cmd.extend(self._extract_subcommand_args("exhaustive_matcher", config.additional_args))

        matcher_res = self._run_command(
            matcher_cmd,
            cwd=workspace,
            log_file=log_file,
            timeout_seconds=remaining_timeout(),
            log_chunks=log_chunks,
            env=env,
        )

        matcher_output = (matcher_res.stdout or "") + (matcher_res.stderr or "")
        matcher_failed_silent = self._has_matcher_fatal_error(matcher_output)
        db_matches = self._count_database_matches(database_path) if database_path.is_file() else -1

        # If GPU matching attempted but failed (or produced 0 matches), retry with CPU matching
        if has_gpu and (matcher_failed_silent or db_matches == 0):
            logger.warning(
                "COLMAP GPU matching reported an error or 0 matches; retrying with CPU matching (--FeatureMatching.use_gpu 0)..."
            )
            cpu_matcher_cmd = [
                str(binary), "exhaustive_matcher",
                "--database_path", str(database_path),
                "--FeatureMatching.use_gpu", "0",
            ]
            cpu_matcher_cmd.extend(self._extract_subcommand_args("exhaustive_matcher", config.additional_args))
            cpu_res = self._run_command(
                cpu_matcher_cmd,
                cwd=workspace,
                log_file=log_file,
                timeout_seconds=remaining_timeout(),
                log_chunks=log_chunks,
                env=env,
            )
            matcher_output = (cpu_res.stdout or "") + (cpu_res.stderr or "")
            matcher_failed_silent = self._has_matcher_fatal_error(matcher_output)
            if database_path.is_file():
                db_matches = self._count_database_matches(database_path)

        if matcher_failed_silent:
            raise ReconstructionExecutionError(
                f"COLMAP feature matching encountered a fatal error: {matcher_output.strip()[-500:]}"
            )

        if database_path.is_file() and db_matches == 0:
            raise ReconstructionExecutionError(
                "COLMAP feature matching failed: 0 usable matches found in database. Check image overlap and quality."
            )

        # Stage 3: Mapper (Sparse SfM)
        mapper_cmd = [
            str(binary), "mapper",
            "--database_path", str(database_path),
            "--image_path", str(images_dir),
            "--output_path", str(sparse_dir),
        ]
        mapper_cmd.extend(self._extract_subcommand_args("mapper", config.additional_args))
        self._run_command(
            mapper_cmd,
            cwd=workspace,
            log_file=log_file,
            timeout_seconds=remaining_timeout(),
            log_chunks=log_chunks,
            env=env,
        )

        valid_models = [
            p for p in sorted(sparse_dir.iterdir())
            if p.is_dir() and (any(p.glob("*.bin")) or any(p.glob("*.txt")))
        ]
        if not valid_models:
            raise ReconstructionArtifactNotFoundError(
                "COLMAP mapper completed without producing a sparse model. Check the log for camera registration failures."
            )

        # Select the best model by registered cameras, then 3D points, then total files
        model_dir = max(
            valid_models,
            key=lambda m: (*self._get_model_stats(m), sum(1 for _ in m.glob("*.*"))),
        )
        stat_images, stat_points = self._get_model_stats(model_dir)
        logger.info(
            "COLMAP produced %d sparse model(s) in %s. Selected primary model '%s' "
            "(registered_images=%d, sparse_points=%d).",
            len(valid_models),
            sparse_dir,
            model_dir.name,
            stat_images,
            stat_points,
        )

        # Check registered images and point count from selected model, then mapper log
        log_text = "".join(log_chunks)
        registered_cameras: int | None = stat_images if stat_images > 0 else None
        reconstructed_points: int | None = stat_points if stat_points > 0 else None

        if registered_cameras is None:
            recon_match = re.search(r"Reconstruction with (\d+) images and (\d+) points", log_text)
            if recon_match:
                registered_cameras = int(recon_match.group(1))
                if reconstructed_points is None:
                    reconstructed_points = int(recon_match.group(2))

        if registered_cameras is not None and registered_cameras < 3:
            raise ReconstructionExecutionError(
                f"COLMAP reconstruction failed: only {registered_cameras} camera(s) registered, "
                "which is insufficient to reconstruct 3D surface geometry."
            )

        # Stage 4: Dense MVS Path (if can_run_dense is True) vs Sparse CPU Fallback
        dense_ply = dense_dir / "fused.ply"
        dense_mesh_ply = dense_dir / "meshed-poisson.ply"
        dense_succeeded = False
        dense_error_msg: str | None = None

        allow_fallback = self.allow_fallback
        if "allow_fallback" in config.extra_params:
            allow_fallback = config.extra_params["allow_fallback"].lower() not in {"0", "false", "no"}

        if can_run_dense:
            dense_commands = [
                [str(binary), "image_undistorter", "--image_path", str(images_dir), "--input_path", str(model_dir),
                 "--output_path", str(dense_dir), "--output_type", "COLMAP", "--max_image_size", max_image_size],
                [str(binary), "patch_match_stereo", "--workspace_path", str(dense_dir), "--workspace_format", "COLMAP",
                 "--PatchMatchStereo.geom_consistency", "true"],
                [str(binary), "stereo_fusion", "--workspace_path", str(dense_dir), "--workspace_format", "COLMAP",
                 "--input_type", "geometric", "--output_path", str(dense_ply)],
                [str(binary), "poisson_mesher", "--input_path", str(dense_ply), "--output_path", str(dense_mesh_ply)],
            ]
            try:
                for cmd in dense_commands:
                    self._run_command(
                        cmd,
                        cwd=workspace,
                        log_file=log_file,
                        timeout_seconds=remaining_timeout(),
                        log_chunks=log_chunks,
                        env=env,
                    )
                if self._nonempty_file(dense_ply) and self._nonempty_file(dense_mesh_ply):
                    dense_succeeded = True
            except (ReconstructionTimeoutError, ReconstructionExecutionError, ReconstructionArtifactNotFoundError) as exc:
                dense_error_msg = str(exc)
                logger.warning("COLMAP dense MVS failed: %s", exc)
                if not allow_fallback:
                    raise ReconstructionExecutionError(
                        f"COLMAP dense MVS failed and fallback is disabled: {exc}"
                    ) from exc
                logger.warning("Dense MVS fallback is enabled; preserving sparse point cloud and Delaunay mesh.")

        # Stage 5: Sparse Export & Delaunay Meshing (Generated as standard or fallback)
        sparse_points_ply = sparse_dir / "points.ply"
        sparse_mesh_ply = sparse_dir / "mesh.ply"

        if not dense_succeeded:
            # Export sparse point cloud via model_converter
            self._run_command(
                [str(binary), "model_converter", "--input_path", str(model_dir),
                 "--output_path", str(sparse_points_ply), "--output_type", "PLY"],
                cwd=workspace,
                log_file=log_file,
                timeout_seconds=remaining_timeout(),
                log_chunks=log_chunks,
                env=env,
            )
            # Generate surface mesh via delaunay_mesher
            dm_cmd = [str(binary), "delaunay_mesher", "--input_path", str(model_dir),
                      "--input_type", "sparse", "--output_path", str(sparse_mesh_ply)]
            dm_user_args = self._extract_subcommand_args("delaunay_mesher", config.additional_args)
            if not any("--DelaunayMeshing.max_side_length_factor" in arg for arg in dm_user_args):
                dm_cmd.extend(["--DelaunayMeshing.max_side_length_factor", "10"])
            dm_cmd.extend(dm_user_args)
            self._run_command(
                dm_cmd,
                cwd=workspace,
                log_file=log_file,
                timeout_seconds=remaining_timeout(),
                log_chunks=log_chunks,
                env=env,
            )

        if dense_succeeded:
            mesh_path = dense_mesh_ply.resolve()
            dense_point_cloud = dense_ply.resolve()
            point_cloud = dense_ply.resolve()
            status = ReconstructionStatus.SUCCESS
            out_dir = dense_dir
        else:
            if not self._nonempty_file(sparse_mesh_ply):
                raise ReconstructionArtifactNotFoundError(f"COLMAP sparse mesh was not generated: {sparse_mesh_ply}")
            if not self._nonempty_file(sparse_points_ply):
                raise ReconstructionArtifactNotFoundError(f"COLMAP sparse point cloud was not generated: {sparse_points_ply}")
            if not self._validate_ply_mesh(sparse_mesh_ply):
                raise ReconstructionArtifactNotFoundError(f"Generated sparse mesh is invalid or has no vertices: {sparse_mesh_ply}")

            mesh_path = sparse_mesh_ply.resolve()
            dense_point_cloud = None
            point_cloud = sparse_points_ply.resolve()
            out_dir = sparse_dir
            status = ReconstructionStatus.PARTIAL if dense_error_msg is not None else ReconstructionStatus.SUCCESS

        sparse_model = model_dir if model_dir.is_dir() else None
        point_count = reconstructed_points or self._parse_ply_point_count(point_cloud)
        reg_ratio = (
            round(registered_cameras / len(valid_frames), 4)
            if registered_cameras is not None and len(valid_frames) > 0
            else None
        )

        quality_warnings: list[str] = []
        is_fragmented = False

        if registered_cameras is not None:
            if len(valid_frames) >= 10 and (reg_ratio is not None and reg_ratio < 0.35):
                is_fragmented = True
                quality_warnings.append(
                    f"Reconstruction is fragmented: only {registered_cameras}/{len(valid_frames)} "
                    f"images registered ({reg_ratio*100:.1f}% coverage)."
                )

        if not dense_succeeded:
            if dense_error_msg is not None or is_fragmented:
                status = ReconstructionStatus.PARTIAL
            else:
                status = ReconstructionStatus.SUCCESS

        if not config.keep_workspace:
            if images_dir.is_dir():
                shutil.rmtree(images_dir, ignore_errors=True)
            if database_path.is_file():
                database_path.unlink(missing_ok=True)

        return ReconstructionResult(
            success=True,
            status=status,
            backend_name=self.backend_name,
            mesh_path=mesh_path,
            sparse_reconstruction_path=sparse_model.resolve() if sparse_model else None,
            dense_point_cloud_path=dense_point_cloud,
            point_cloud_path=point_cloud,
            execution_time_seconds=round(time.monotonic() - started, 2),
            input_frames_count=len(valid_frames),
            registered_cameras_count=registered_cameras,
            registration_ratio=reg_ratio,
            point_count=point_count,
            workspace_dir=workspace,
            output_dir=out_dir,
            log_path=log_file,
            log_output="".join(log_chunks),
            error_message=(
                f"Dense MVS fallback: {dense_error_msg}; {'; '.join(quality_warnings)}"
                if (dense_error_msg and quality_warnings)
                else (f"Dense MVS fallback: {dense_error_msg}" if dense_error_msg else ("; ".join(quality_warnings) if quality_warnings else None))
            ),
        )

"""End-to-end demonstration and diagnostic runner for VIDEO2PRINT using ColmapAdapter."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

# Ensure src/ is on sys.path for direct script execution
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from typing import Any

import numpy as np
import trimesh

from loom.pipeline.artifacts import export_reconstruction_checkpoints
from loom.reconstruction.colmap import ColmapAdapter
from loom.reconstruction.models import ReconstructionJobConfig
from loom.reconstruction.exceptions import (
    ReconstructionBinaryNotFoundError,
    ReconstructionError,
    ReconstructionExecutionError,
    ReconstructionInvalidInputError,
)
from loom.utils.logging import setup_logging
from loom.utils.paths import ensure_directory

logger = logging.getLogger("loom.demo")


def run_demo(
    dense: bool = False,
    allow_sparse_fallback: bool = False,
    sparse_dir: Path | None = None,
    images_dir: Path | None = None,
    video_path: Path | None = None,
    output_dir: Path = Path("outputs/demo"),
    colmap_path: Path | None = None,
    gpu_index: int = 0,
    max_image_size: int = 1600,
    timeout: int = 1800,
    clean_mesh: bool = False,
    remove_floor: bool = False,
    cap_base: bool = False,
    component_strategy: str = "centroid_proximity",
    scale: bool = False,
    reference_size: float = 50.0,
    marker_id: int = 0,
    export_stl: bool = False,
    stl_dir: Path | None = None,
    sample_interval: int = 1,
    max_frames: int = 75,
    target_fps: float | None = None,
    sequential: bool = False,
    min_num_pixels: int = 2,
    mesh_only: Path | None = None,
    point_cloud: Path | None = None,
    target_length: float | None = 200.0,
    align_support: bool = False,
    base_z: float | None = None,
    turbo: bool = False,
) -> dict[str, Any]:
    """Execute end-to-end reconstruction demo via ColmapAdapter.

    Args:
        dense: Flag to execute dense MVS pipeline (reconstruct_dense).
        allow_sparse_fallback: Explicit flag to allow sparse Delaunay meshing preview
                               when dense is omitted.
        sparse_dir: Path to directory containing sparse SfM model (e.g. cameras.bin).
        images_dir: Path to directory containing source RGB images.
        video_path: Path to optional input video for frame extraction.
        output_dir: Working directory for output artifacts.
        colmap_path: Explicit path to COLMAP binary.
        gpu_index: CUDA GPU device index for dense stereo.
        max_image_size: Image dimension limit for stereo (safeguards 8 GB VRAM buffer).
        timeout: Subprocess execution timeout in seconds.
        clean_mesh: Whether to run Phase 3 mesh cleaning on output.
        scale: Whether to run Phase 4 metric scaling on output.
        reference_size: Fiducial marker size in mm.
        marker_id: Expected ArUco marker ID.
        mesh_only: Optional path to existing .ply mesh to process directly through Phase 3/4/5.
        point_cloud: Optional path to dense point cloud .ply for distance culling.
        target_length: Optional target maximum dimension in mm for uniform scaling before STL export.
        align_support: Whether to apply Phase 4 canonical coordinate frame normalization.
        base_z: Optional explicit Z coordinate for planar base slicing.
        turbo: Enable Turbo Pipeline (<200s total runtime).

    Returns:
        Dictionary containing execution summary, artifact paths, and metrics.

    Raises:
        ReconstructionError: When dense reconstruction fails or when dense is omitted
                             without --allow-sparse-fallback.
        ReconstructionBinaryNotFoundError: When COLMAP executable is missing.
        ReconstructionInvalidInputError: When inputs are missing or invalid.
    """
    workspace = ensure_directory(output_dir)

    import time
    t0_total = time.time()
    stage_timings: dict[str, float] = {}

    active_images_dir: Path | None = images_dir
    active_sparse_dir: Path | None = sparse_dir
    resolved_sparse: Path | None = None
    reconstruction_artifact: Any = None
    dense_source: Path | None = None
    run_name = output_dir.name if output_dir.name != "outputs" else "demo"
    output_root = output_dir.parent if output_dir.name == "demo" else output_dir
    checkpoints: dict[str, Path] = {}

    if mesh_only is not None:
        mesh_only_path = Path(mesh_only).resolve()
        if not mesh_only_path.is_file():
            raise ReconstructionInvalidInputError(f"Mesh file does not exist: {mesh_only_path}")

        logger.info("[MESH-ONLY MODE] Direct processing on existing mesh: %s", mesh_only_path)
        raw_mesh_path = mesh_only_path
        final_mesh_path = raw_mesh_path

        if active_sparse_dir is not None:
            resolved_sparse = Path(active_sparse_dir).resolve()

        checkpoints = export_reconstruction_checkpoints(
            run_name=run_name,
            output_root=output_root,
            mesh_source=raw_mesh_path,
        )
    else:
        adapter = ColmapAdapter(binary_path=colmap_path)

        # 1. Binary availability check
        resolved_bin = adapter.resolve_binary(colmap_path)
        if resolved_bin is None:
            target = str(colmap_path or "/usr/bin/colmap")
            raise ReconstructionBinaryNotFoundError(
                f"COLMAP binary not found at '{target}'. Ensure COLMAP is installed and accessible."
            )

        # 2. Input validation and preparation
        if active_images_dir is None and video_path is not None:
            if not video_path.is_file():
                candidate = Path("data/raw") / video_path.name
                if candidate.is_file():
                    logger.warning("Input video '%s' not found. Resolved via data/raw: '%s'", video_path, candidate)
                    video_path = candidate
            if not video_path.is_file():
                raise ReconstructionInvalidInputError(f"Input video does not exist: {video_path}")
            from loom.video.frames import FrameExtractor
            from loom.config.models import VideoConfig
            extracted_dir = ensure_directory(workspace / "extracted_frames")
            effective_max_frames = max_frames
            if turbo and (max_frames is None or max_frames in (42, 75)):
                effective_max_frames = 65
            effective_max_dim = min(max_image_size, 1080) if turbo else 1080
            video_cfg = VideoConfig(
                sample_interval=sample_interval,
                max_frames=effective_max_frames,
                target_fps=target_fps,
                target_max_dimension=effective_max_dim,
                turbo=turbo,
            )
            extractor = FrameExtractor(video_cfg)
            t_ingest = time.time()
            frame_artifact = extractor.extract(video_path=video_path, output_dir=extracted_dir)
            stage_timings["Frame Extraction"] = round(time.time() - t_ingest, 2)
            active_images_dir = frame_artifact.frames_dir
            logger.info(
                "Extracted %d frames from '%s' into %s",
                frame_artifact.total_extracted,
                video_path.name,
                active_images_dir,
            )

        if active_sparse_dir is None and active_images_dir is not None:
            # Check if sparse model already exists in workspace
            candidate_sparse = workspace / "sparse"
            if (candidate_sparse / "0").is_dir() or (candidate_sparse / "cameras.bin").is_file() or (candidate_sparse / "cameras.txt").is_file():
                active_sparse_dir = candidate_sparse
            else:
                logger.info("No sparse model provided. Generating sparse SfM model via COLMAP mapper...")
                frame_files = sorted(
                    list(active_images_dir.glob("*.jpg"))
                    + list(active_images_dir.glob("*.jpeg"))
                    + list(active_images_dir.glob("*.png"))
                )
                if not frame_files:
                    raise ReconstructionInvalidInputError(f"No image frames found in {active_images_dir}")
                # Ensure workspace/images and workspace/database.db are cleanly isolated or purged per run
                db_file = workspace / "database.db"
                if db_file.exists():
                    logger.info("Purging stale COLMAP database: %s", db_file)
                    try:
                        db_file.unlink()
                    except OSError as err:
                        logger.warning("Could not delete stale database %s: %s", db_file, err)

                ws_images = workspace / "images"
                if ws_images.is_dir():
                    logger.info("Purging stale workspace images directory: %s", ws_images)
                    shutil.rmtree(ws_images, ignore_errors=True)

                is_seq = sequential or (video_path is not None) or turbo
                matching_mode = "sequential" if is_seq else "exhaustive"
                job_cfg = ReconstructionJobConfig(
                    workspace_dir=workspace,
                    binary_path=resolved_bin,
                    timeout_seconds=timeout,
                    sequential=is_seq,
                    turbo=turbo,
                    extra_params={
                        "matching_mode": matching_mode,
                        "turbo": str(turbo),
                        "sparse_only": "true",
                        "overlap": "10",
                    },
                )
                t_sfm = time.time()
                adapter.reconstruct(frame_files, job_cfg, sequential=is_seq)
                stage_timings["Sparse SfM"] = round(time.time() - t_sfm, 2)
                active_sparse_dir = workspace / "sparse"

        if active_sparse_dir is None:
            raise ReconstructionInvalidInputError(
                "Missing reconstruction inputs. Please specify --sparse-dir (and --images for dense)."
            )

        resolved_sparse = adapter.resolve_sparse_model_dir(active_sparse_dir)

        # 3. Reconstruction step execution via ColmapAdapter
        if dense:
            logger.info("Executing dense COLMAP reconstruction via ColmapAdapter...")
            if active_images_dir is None or not active_images_dir.is_dir():
                raise ReconstructionInvalidInputError(
                    "Dense reconstruction requires valid --images directory."
                )

            t_dense = time.time()
            try:
                reconstruction_artifact = adapter.reconstruct_dense(
                    image_dir=active_images_dir,
                    sparse_dir=resolved_sparse,
                    output_dir=workspace / "dense",
                    binary_path=resolved_bin,
                    gpu_index=gpu_index,
                    max_image_size=min(max_image_size, 960) if turbo else max_image_size,
                    min_num_pixels=min_num_pixels,
                    timeout_seconds=timeout,
                    turbo=turbo,
                )
                stage_timings["Dense MVS & Meshing"] = round(time.time() - t_dense, 2)
                logger.info("Dense reconstruction successful: %s", reconstruction_artifact.mesh_path)
            except Exception as exc:
                # Do NOT silently fall back to sparse Delaunay if dense fails!
                logger.error("Dense reconstruction failed: %s", exc)
                raise ReconstructionError(f"Dense reconstruction failed: {exc}") from exc
        else:
            # --dense is omitted
            if not allow_sparse_fallback:
                msg = (
                    "Dense reconstruction was omitted (--dense). "
                    "Sparse Delaunay meshing produces a broken wireframe mesh and requires explicit opt-in "
                    "via '--allow-sparse-fallback' as an explicitly labeled diagnostic preview."
                )
                logger.error(msg)
                raise ReconstructionError(msg)

            logger.warning(
                "[DIAGNOSTIC PREVIEW] Running sparse Delaunay meshing fallback. "
                "Note: This is an untextured sparse wireframe mesh for diagnostic preview only."
            )
            reconstruction_artifact = adapter.reconstruct_sparse_mesh(
                sparse_dir=resolved_sparse,
                output_path=workspace / "meshed-delaunay.ply",
                binary_path=resolved_bin,
                timeout_seconds=timeout,
            )
            logger.info("[DIAGNOSTIC PREVIEW] Sparse preview mesh generated: %s", reconstruction_artifact.mesh_path)

        raw_mesh_path = reconstruction_artifact.mesh_path
        final_mesh_path = raw_mesh_path

        # Export intermediate checkpoints to outputs/reconstructions/<run_name>/
        # Preserves: 01_sparse/points3D.ply, 02_dense/fused.ply, 03_raw_mesh/meshed-poisson.ply
        run_name = output_dir.name if output_dir.name != "outputs" else "demo"
        output_root = output_dir.parent if output_dir.name == "demo" else output_dir
        dense_source = (
            getattr(reconstruction_artifact, "isolated_point_cloud_path", None)
            or getattr(reconstruction_artifact, "dense_point_cloud_path", None)
            or (workspace / "dense" / "fused_isolated.ply" if (workspace / "dense" / "fused_isolated.ply").is_file() else None)
            or (workspace / "dense" / "fused.ply")
        )
        if point_cloud is None and dense_source and Path(dense_source).is_file():
            point_cloud = Path(dense_source)
        checkpoints = export_reconstruction_checkpoints(
            run_name=run_name,
            output_root=output_root,
            sparse_source=resolved_sparse,
            dense_source=dense_source if dense_source and Path(dense_source).is_file() else None,
            mesh_source=raw_mesh_path,
        )

    # 4. Optional Phase 4 Canonical Frame Normalization (align support plane prior to cleaning/slicing)
    if align_support and not turbo and raw_mesh_path and raw_mesh_path.is_file():
        logger.info("Applying Phase 4 canonical frame normalization on %s...", raw_mesh_path)
        from loom.geometry.alignment import AlignmentResult, CoordinateNormalizer, extract_colmap_camera_centers

        cam_centers = None
        if resolved_sparse:
            cam_centers = extract_colmap_camera_centers(resolved_sparse)

        normalizer = CoordinateNormalizer()
        loaded = trimesh.load(str(raw_mesh_path), process=False)

        pc_candidate = point_cloud or (dense_source if dense_source and Path(dense_source).is_file() else None)
        loaded_pc = None
        if pc_candidate and Path(pc_candidate).is_file():
            try:
                loaded_pc = trimesh.load(str(pc_candidate))
            except Exception as e:
                logger.warning("Could not load point cloud %s: %s", pc_candidate, e)

        if loaded_pc is not None and hasattr(loaded_pc, "vertices") and len(loaded_pc.vertices) >= 3:
            pts_for_plane = np.asarray(loaded_pc.vertices, dtype=np.float64)
            plane = normalizer.fit_support_plane_ransac(
                pts_for_plane,
                threshold=normalizer.distance_threshold,
                camera_centers=cam_centers,
            )
            R, t, T = normalizer.compute_alignment_matrix(plane, pts_for_plane)
            aligned_pts = (np.asarray(loaded.vertices, dtype=np.float64) @ R.T) + t
            aligned_mesh = loaded.copy()
            aligned_mesh.apply_transform(T)
            align_result = AlignmentResult(
                rotation_matrix=R,
                translation_vector=t,
                transform_4x4=T,
                support_plane=plane,
                aligned_points=aligned_pts,
                inlier_count=len(plane.inlier_indices),
            )
        else:
            aligned_mesh, align_result = normalizer.normalize(loaded, camera_centers=cam_centers)

        aligned_path = workspace / f"aligned_{raw_mesh_path.stem}.ply"
        aligned_mesh.export(str(aligned_path))
        raw_mesh_path = aligned_path
        final_mesh_path = aligned_path

        # If a point cloud exists, transform it by the identical 4x4 matrix so KDTree culling matches
        if loaded_pc is not None and pc_candidate:
            loaded_pc.apply_transform(align_result.transform_4x4)
            aligned_pc_path = workspace / f"aligned_{Path(pc_candidate).name}"
            loaded_pc.export(str(aligned_pc_path))
            dense_source = aligned_pc_path
            point_cloud = aligned_pc_path

        logger.info(
            "Canonical alignment complete: support plane sitting at Z=0 (normal: %s, inliers: %d)",
            align_result.support_plane.normal,
            align_result.inlier_count,
        )

    # 4b. Optional Phase 3 mesh repair (with robust floor removal, centroid component isolation, and base capping)
    if clean_mesh and raw_mesh_path and raw_mesh_path.is_file():
        t_clean = time.time()
        logger.info("Running Phase 3 mesh cleaning on %s...", raw_mesh_path)
        from loom.config.models import MeshConfig
        from loom.mesh.processor import MeshProcessor

        cleaned_path = workspace / f"cleaned_{raw_mesh_path.name}"
        pc_path = (
            point_cloud
            or (dense_source if dense_source and Path(dense_source).is_file() else None)
        )
        eff_base_z = base_z
        if eff_base_z is None and (align_support or turbo):
            eff_base_z = 0.005

        mesh_cfg = MeshConfig(
            floor_removal_enabled=remove_floor and not turbo,
            base_capping_enabled=cap_base or clean_mesh or turbo,
            base_capping_z=eff_base_z,
            component_strategy=component_strategy,
            point_cloud_culling_enabled=(pc_path is not None) and not turbo,
            point_cloud_path=pc_path if not turbo else None,
            close_all_holes=False if turbo else True,
            turbo=turbo,
        )
        processor = MeshProcessor(mesh_cfg)
        clean_result = processor.process(raw_mesh_path, cleaned_path, point_cloud_path=None if turbo else pc_path)
        if clean_result.success and clean_result.output_mesh_path:
            final_mesh_path = clean_result.output_mesh_path
        stage_timings["Mesh Cleaning & Base Capping"] = round(time.time() - t_clean, 2)

        # Update checkpoints if intermediate floor removal or base capping was performed
        floor_file = workspace / "04_floor_removed.ply"
        capped_file = workspace / "05_base_capped.ply"
        if floor_file.is_file() or capped_file.is_file():
            checkpoints = export_reconstruction_checkpoints(
                run_name=run_name,
                output_root=output_root,
                sparse_source=resolved_sparse,
                dense_source=dense_source if dense_source and Path(dense_source).is_file() else None,
                mesh_source=raw_mesh_path,
                floor_removed_source=floor_file if floor_file.is_file() else None,
                base_capped_source=capped_file if capped_file.is_file() else None,
            )

    # 5. Optional Phase 4 metric scaling (preserved logic)
    scale_factor: float | None = None
    if scale and final_mesh_path and final_mesh_path.is_file():
        logger.info("Running Phase 4 metric scaling on %s...", final_mesh_path)
        from loom.config.models import ScalingConfig
        from loom.scaling.processor import ScalingProcessor

        scaled_path = workspace / f"scaled_{final_mesh_path.stem}.obj"
        scaling_cfg = ScalingConfig(
            marker_size_mm=reference_size,
            marker_id=marker_id,
            colmap_dir=resolved_sparse,
            images_dir=active_images_dir,
        )
        scaling_proc = ScalingProcessor(scaling_cfg)
        try:
            scale_res = scaling_proc.process(
                input_mesh_path=final_mesh_path,
                output_mesh_path=scaled_path,
                colmap_dir=resolved_sparse,
                images_dir=active_images_dir,
                raise_on_error=False,
            )
            if scale_res.success and scale_res.output_mesh_path and Path(scale_res.output_mesh_path).is_file():
                final_mesh_path = Path(scale_res.output_mesh_path)
                scale_factor = scale_res.scale_factor
            else:
                logger.warning(
                    "[WARNING] ArUco marker not observed in registered views. "
                    "Bypassing metric scaling; preserving photogrammetric units."
                )
                scale_factor = 1.0
        except Exception as exc:
            logger.warning(
                "[WARNING] ArUco marker not observed in registered views (%s). "
                "Bypassing metric scaling; preserving photogrammetric units.",
                exc,
            )
            scale_factor = 1.0

    # 6. Optional Target-Length Uniform Scaling (prevents float32 STL coordinate quantization collapse)
    mesh_to_export: Any = final_mesh_path
    if (
        target_length is not None
        and (scale_factor is None or scale_factor == 1.0)
        and isinstance(final_mesh_path, (Path, str))
        and Path(final_mesh_path).is_file()
    ):
        logger.info(
            "Applying target-length uniform scaling: target maximum dimension = %.2f mm",
            target_length,
        )
        loaded_mesh = trimesh.load(str(final_mesh_path), process=False)
        if isinstance(loaded_mesh, trimesh.Scene):
            loaded_mesh = trimesh.util.concatenate(list(loaded_mesh.geometry.values()))
        max_extent = float(max(loaded_mesh.extents)) if len(loaded_mesh.extents) > 0 else 0.0
        if max_extent > 1e-8:
            s = float(target_length) / max_extent
            loaded_mesh.vertices = np.asarray(loaded_mesh.vertices, dtype=np.float64)
            loaded_mesh.apply_scale(s)
            try:
                trimesh.repair.fix_winding(loaded_mesh)
            except Exception:
                pass
            loaded_mesh.fix_normals()
            loaded_mesh.vertices[:, 2] -= float(loaded_mesh.bounds[0][2])
            loaded_mesh.vertices[:, :2] -= loaded_mesh.bounds.mean(axis=0)[:2]
            mesh_to_export = loaded_mesh
            scale_factor = s
            logger.info(
                "Scaled mesh in float64 memory by factor %.5f (extents: %s mm, Z_min=%.6f mm)",
                s,
                loaded_mesh.extents,
                float(loaded_mesh.bounds[0][2]),
            )
            scaled_out = workspace / f"scaled_{final_mesh_path.stem}.ply"
            loaded_mesh.export(str(scaled_out))
            final_mesh_path = scaled_out

    # 7. Optional Validated Binary STL Export
    exported_stl_path: Path | None = None
    manifest_path: Path | None = None
    if export_stl and final_mesh_path and (final_mesh_path.is_file() or isinstance(mesh_to_export, trimesh.Trimesh)):
        t_export = time.time()
        logger.info("Running manufacturing readiness check and binary STL export...")
        from loom.config.models import ExportConfig
        from loom.export.stl import StlExporter
        from loom.printability.exceptions import PrintabilityValidationError

        target_stl_dir = Path(stl_dir or "outputs/stl")
        exporter = StlExporter(config=ExportConfig(output_dir=target_stl_dir), enforce_printability_gate=True)
        base_name = final_mesh_path.stem if final_mesh_path else "model"
        clean_base = base_name.replace("scaled_", "").replace("_scaled", "")
        target_stl_file = target_stl_dir / f"{clean_base}_metric.stl"
        try:
            exported_stl_path = exporter.export(
                mesh_path=mesh_to_export,
                output_stl_path=target_stl_file,
                scale_factor_applied=scale_factor if scale_factor is not None else 1.0,
                project_name="LOOM_DEMO",
                enforce_gate=True,
            )
            manifest_path = exporter.last_manifest_path
            logger.info("Validated metric binary STL exported: %s (manifest: %s)", exported_stl_path, manifest_path)
        except PrintabilityValidationError as p_exc:
            logger.warning(
                "Printability gate validation warning: %s. Proceeding with STL export...",
                p_exc,
            )
            exported_stl_path = exporter.export(
                mesh_path=mesh_to_export,
                output_stl_path=target_stl_file,
                scale_factor_applied=scale_factor if scale_factor is not None else 1.0,
                project_name="LOOM_DEMO",
                enforce_gate=False,
                validation_result=getattr(p_exc, "validation_result", None),
            )
            manifest_path = exporter.last_manifest_path
            logger.info("Binary STL exported with gate warnings: %s (manifest: %s)", exported_stl_path, manifest_path)
        except Exception as exc:
            logger.error("STL export failed manufacturing readiness gate: %s", exc)
            if not allow_sparse_fallback and mesh_only is None:
                raise
        stage_timings["Scaling & Validated STL Export"] = round(time.time() - t_export, 2)

    total_time = round(time.time() - t0_total, 2)
    stage_timings["Total Turnaround Time"] = total_time

    return {
        "success": True,
        "mode": "dense" if dense else "sparse_diagnostic_preview",
        "mesh_path": final_mesh_path,
        "raw_mesh_path": raw_mesh_path,
        "point_cloud_path": getattr(reconstruction_artifact, "point_cloud_path", None),
        "execution_time_seconds": total_time,
        "scale_factor": scale_factor,
        "workspace": workspace,
        "checkpoints": checkpoints,
        "exported_stl_path": exported_stl_path,
        "manifest_path": manifest_path,
        "stage_timings": stage_timings,
        "total_turnaround_seconds": total_time,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for demo runner."""
    parser = argparse.ArgumentParser(
        prog="demo.py",
        description="VIDEO2PRINT: End-to-End COLMAP 3D Reconstruction Demo & Diagnostic Runner",
    )
    parser.add_argument(
        "--dense",
        action="store_true",
        default=False,
        help="Execute full dense MVS reconstruction (image_undistorter -> patch_match_stereo -> stereo_fusion -> poisson_mesher).",
    )
    parser.add_argument(
        "--allow-sparse-fallback",
        action="store_true",
        default=False,
        help="Allow sparse Delaunay meshing as an explicitly labeled diagnostic preview when --dense is omitted.",
    )
    parser.add_argument(
        "--images",
        "--frames",
        "-i",
        dest="images_dir",
        type=Path,
        default=None,
        help="Path to directory containing RGB frames or keyframes.",
    )
    parser.add_argument(
        "--sparse-dir",
        "-s",
        type=Path,
        default=None,
        help="Path to pre-computed sparse SfM directory (containing cameras.bin / images.bin).",
    )
    parser.add_argument(
        "--video",
        "-v",
        type=Path,
        default=None,
        help="Path to input smartphone video.",
    )
    parser.add_argument(
        "--output-dir",
        "--workspace",
        "-o",
        dest="output_dir",
        type=Path,
        default=Path("outputs/demo"),
        help="Working directory for outputs (default: outputs/demo).",
    )
    parser.add_argument(
        "--colmap-path",
        type=Path,
        default=None,
        help="Explicit path to colmap binary (default: searches PATH or /usr/bin/colmap).",
    )
    parser.add_argument(
        "--gpu-index",
        type=int,
        default=0,
        help="CUDA GPU device index for dense stereo (default: 0).",
    )
    parser.add_argument(
        "--max-image-size",
        type=int,
        default=1600,
        help="Max image dimension for stereo to safeguard 8 GB VRAM buffer (default: 1600).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Execution timeout per step in seconds (default: 1800s).",
    )
    parser.add_argument(
        "--clean-mesh",
        action="store_true",
        default=False,
        help="Execute Phase 3 geometry cleaning and repair on the reconstructed mesh.",
    )
    parser.add_argument(
        "--remove-floor",
        action="store_true",
        default=False,
        help="Identify and remove dominant horizontal floor plane using RANSAC.",
    )
    parser.add_argument(
        "--cap-base",
        action="store_true",
        default=False,
        help="Slice and cleanly cap the planar base boundary loop for 3D printing build plate contact.",
    )
    parser.add_argument(
        "--align-support",
        action="store_true",
        default=False,
        help="Apply Phase 4 canonical coordinate frame normalization via RANSAC support plane alignment.",
    )
    parser.add_argument(
        "--component-strategy",
        default="centroid_proximity",
        choices=["centroid_proximity", "largest", "largest_by_area", "min_faces", "keep_all"],
        help="Component selection strategy (default: centroid_proximity).",
    )
    parser.add_argument(
        "--scale",
        action="store_true",
        default=False,
        help="Execute Phase 4 metric scaling on mesh.",
    )
    parser.add_argument(
        "--reference-size",
        type=float,
        default=50.0,
        help="Physical reference marker size in mm (default: 50.0).",
    )
    parser.add_argument(
        "--marker-id",
        type=int,
        default=0,
        help="Expected ArUco marker ID (default: 0).",
    )
    parser.add_argument(
        "--export-stl",
        action="store_true",
        default=False,
        help="Enforce manufacturing readiness checks and export validated binary STL.",
    )
    parser.add_argument(
        "--stl-dir",
        type=Path,
        default=Path("outputs/stl"),
        help="Output directory for validated metric STL and build manifest (default: outputs/stl).",
    )
    parser.add_argument(
        "--sample-interval",
        type=int,
        default=1,
        help="Frame extraction step interval from video (default: 1).",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=75,
        help="Maximum number of frames to extract from video (default: 75).",
    )
    parser.add_argument(
        "--target-fps",
        type=float,
        default=None,
        help="Target frame rate for video extraction (e.g. 5.0).",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        default=False,
        help="Use sequential feature matching instead of exhaustive (automatically enabled for video inputs).",
    )
    parser.add_argument(
        "--min-num-pixels",
        type=int,
        default=2,
        help="Minimum number of pixel/view observations for stereo fusion (default: 2).",
    )
    parser.add_argument(
        "--mesh-only",
        type=Path,
        default=None,
        help="Path to an existing .ply/.obj mesh file. Bypasses video ingest and COLMAP reconstruction entirely.",
    )
    parser.add_argument(
        "--point-cloud",
        type=Path,
        default=None,
        help="Path to point cloud .ply for KDTree distance culling (e.g. outputs/demo/dense/fused.ply).",
    )
    parser.add_argument(
        "--target-length",
        type=float,
        default=200.0,
        help="Target maximum dimension in mm (default: 200.0). Applies uniform scaling in float64 prior to STL export when fiducial scaling is absent.",
    )
    parser.add_argument(
        "--base-z",
        type=float,
        default=None,
        help="Explicit Z coordinate for planar base slicing (defaults to 0.005 when --align-support is enabled).",
    )
    parser.add_argument(
        "--turbo",
        action="store_true",
        default=False,
        help="Enable Turbo Pipeline (<200s): caps frames to 36 downscaled to 960px, GPU sequential matching, "
             "single-pass photometric stereo, support plane normalization, and cylindrical foreground cropping.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level.",
    )

    args = parser.parse_args(argv)
    setup_logging(level=args.log_level)

    if args.turbo:
        if not args.dense:
            args.dense = True
        args.max_image_size = min(args.max_image_size, 960)
        if not args.clean_mesh:
            args.clean_mesh = True
            args.remove_floor = True
            args.cap_base = True
        args.align_support = False
        if args.target_length is None:
            args.target_length = 200.0
        if not args.export_stl:
            args.export_stl = True
        if args.base_z is None:
            args.base_z = 0.005
        if args.max_frames in (42, 65, 75):
            args.max_frames = 68

    if args.mesh_only:
        # In mesh-only mode, enable cleaning and STL export by default unless explicitly disabled
        if not args.clean_mesh:
            args.clean_mesh = True
            args.remove_floor = True
            args.cap_base = True
        if not args.export_stl:
            args.export_stl = True

    print("\n" + "=" * 65)
    print("VIDEO2PRINT: End-to-End COLMAP 3D Reconstruction Demo")
    print("=" * 65)
    if args.mesh_only:
        print(f"Mode:                  Mesh-Only Direct Processing ({args.mesh_only})")
    else:
        print(f"Mode:                  {'Turbo Dense MVS' if args.turbo else ('Dense MVS' if args.dense else 'Sparse Diagnostic Preview')}")
        print(f"Turbo Mode:            {args.turbo}")
        print(f"Allow Sparse Fallback: {args.allow_sparse_fallback}")
        print(f"GPU Index:             {args.gpu_index}")
        print(f"Max Image Size:        {args.max_image_size}")
    print(f"Output Directory:      {args.output_dir}")
    print("=" * 65 + "\n")

    try:
        summary = run_demo(
            dense=args.dense,
            allow_sparse_fallback=args.allow_sparse_fallback,
            sparse_dir=args.sparse_dir,
            images_dir=args.images_dir,
            video_path=args.video,
            output_dir=args.output_dir,
            colmap_path=args.colmap_path,
            gpu_index=args.gpu_index,
            max_image_size=args.max_image_size,
            timeout=args.timeout,
            clean_mesh=args.clean_mesh,
            remove_floor=args.remove_floor,
            cap_base=args.cap_base,
            component_strategy=args.component_strategy,
            scale=args.scale,
            reference_size=args.reference_size,
            marker_id=args.marker_id,
            export_stl=args.export_stl,
            stl_dir=args.stl_dir,
            sample_interval=args.sample_interval,
            max_frames=args.max_frames,
            target_fps=args.target_fps,
            sequential=args.sequential,
            min_num_pixels=args.min_num_pixels,
            mesh_only=args.mesh_only,
            point_cloud=args.point_cloud,
            target_length=args.target_length,
            align_support=args.align_support,
            base_z=args.base_z,
            turbo=args.turbo,
        )
        print("\n" + "=" * 65)
        print("DEMO EXECUTION SUCCESSFUL")
        print("=" * 65)
        print(f"Generated Mesh:        {summary['mesh_path']}")
        print(f"Mode:                  {summary['mode']}")
        print(f"Execution Time:        {summary['execution_time_seconds']:.2f}s")
        if summary.get("scale_factor"):
            print(f"Scale Factor:          {summary['scale_factor']:.5f}")
        if summary.get("exported_stl_path"):
            print(f"Exported Metric STL:   {summary['exported_stl_path']}")
            print(f"Export Manifest:       {summary.get('manifest_path')}")
        if summary.get("stage_timings"):
            print("-" * 65)
            print("STAGE TIMING BREAKDOWN:")
            for stage_name, duration in summary["stage_timings"].items():
                if stage_name == "Total Turnaround Time":
                    print("-" * 65)
                print(f"  {stage_name:<36} : {duration:>7.2f}s")
        print("=" * 65 + "\n")
        return 0
    except ReconstructionError as exc:
        print(f"\n[ERROR] Reconstruction failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\n[ERROR] Demo execution error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

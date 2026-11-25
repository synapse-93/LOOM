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
from loom.pipeline.manifest import (
    PipelineManifest,
    detect_existing_frame_resolution,
    prepare_workspace,
)
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
    max_frames: int = 130,
    target_fps: float | None = None,
    sequential: bool = False,
    min_num_pixels: int = 2,
    mesh_only: Path | None = None,
    point_cloud: Path | None = None,
    target_length: float | None = 200.0,
    align_support: bool = False,
    base_z: float | None = None,
    turbo: bool = False,
    engine: str = "colmap",
    sfm_only: bool = False,
    stop_after: str | None = None,
    from_stage: str | None = None,
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
    aligned_by_2dgs = False
    solidified_2dgs_res: Any = None
    masking_dict: dict[str, Any] = {}
    vh_dict: dict[str, Any] = {}
    gs_dict: dict[str, Any] = {}
    tsdf_dict: dict[str, Any] = {}
    export_dict: dict[str, Any] = {}
    pipeline_manifest: PipelineManifest | None = None

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

        # 2. Input validation, cache hygiene (pipeline_manifest.json), and frame extraction
        if active_images_dir is None and video_path is not None:
            if not video_path.is_file():
                candidate = Path("data/raw") / video_path.name
                if candidate.is_file():
                    logger.warning("Input video '%s' not found. Resolved via data/raw: '%s'", video_path, candidate)
                    video_path = candidate
            if not video_path.is_file():
                raise ReconstructionInvalidInputError(f"Input video does not exist: {video_path}")

            effective_max_frames = max_frames
            if turbo and (max_frames is None or max_frames in (42, 75, 130)):
                effective_max_frames = 68 if engine == "2dgs" else 65
            # When explicitly resuming a downstream stage (mask/visual_hull/2dgs/tsdf/export),
            # preserve cached upstream frames; otherwise enforce max_frames cache hygiene.
            cache_max_frames = (
                None
                if from_stage in ("sfm", "undistort", "mask", "visual_hull", "2dgs", "tsdf", "export")
                else effective_max_frames
            )
            pipeline_manifest = prepare_workspace(
                workspace=workspace,
                video_path=video_path,
                engine=engine,
                turbo=turbo,
                max_frames=cache_max_frames,
            )
            if from_stage is not None:
                logger.info("[RESUME] Invalidating pipeline manifest from stage '%s' onward.", from_stage)
                pipeline_manifest.invalidate_from_stage(from_stage)
                pipeline_manifest.save(workspace)
            extracted_dir = ensure_directory(workspace / "extracted_frames")

            existing_frames = sorted(
                list(extracted_dir.glob("*.jpg"))
                + list(extracted_dir.glob("*.jpeg"))
                + list(extracted_dir.glob("*.png"))
            )
            if pipeline_manifest.is_stage_complete("frames") and existing_frames:
                logger.info(
                    "[RESUME] Skipping frame extraction; reusing %d cached frames in %s",
                    len(existing_frames),
                    extracted_dir,
                )
                active_images_dir = extracted_dir
            else:
                from loom.video.frames import FrameExtractor
                from loom.config.models import VideoConfig

                effective_max_frames = max_frames
                if turbo and (max_frames is None or max_frames in (42, 75, 130)):
                    effective_max_frames = 68 if engine == "2dgs" else 65
                if engine == "2dgs":
                    effective_max_dim = min(max_image_size, 720 if turbo else 960)
                else:
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
                pipeline_manifest.frame_resolution = detect_existing_frame_resolution(workspace)
                pipeline_manifest.mark_stage_complete("frames")
                pipeline_manifest.save(workspace)

        if active_sparse_dir is None and active_images_dir is not None:
            # Resume verified SfM model only when manifest confirms matching cache
            resumed_sfm_dir: Path | None = None
            if (
                pipeline_manifest is not None
                and pipeline_manifest.is_stage_complete("sfm")
                and pipeline_manifest.sfm.get("winning_model_dir")
            ):
                cand_win = Path(pipeline_manifest.sfm["winning_model_dir"])
                if cand_win.is_dir() and any(cand_win.glob("cameras.*")):
                    resumed_sfm_dir = cand_win

            if resumed_sfm_dir is not None:
                logger.info("[RESUME] Reusing verified sparse SfM model: %s", resumed_sfm_dir)
                active_sparse_dir = resumed_sfm_dir
            else:
                candidate_sparse = workspace / "sparse"
                has_unmanaged_sparse = pipeline_manifest is None and (
                    (candidate_sparse / "0").is_dir()
                    or (candidate_sparse / "cameras.bin").is_file()
                    or (candidate_sparse / "cameras.txt").is_file()
                )
                if has_unmanaged_sparse:
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

                    # Ensure workspace/images, sparse/, and database.db are purged before fresh SfM
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

                    if candidate_sparse.is_dir():
                        shutil.rmtree(candidate_sparse, ignore_errors=True)

                    # Adaptive GPU matching: exhaustive <= 150 frames, sequential > 150 frames
                    is_seq = len(frame_files) > 150
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
                            "gpu_index": str(gpu_index),
                        },
                    )
                    t_sfm = time.time()
                    adapter.reconstruct(frame_files, job_cfg, sequential=is_seq)
                    stage_timings["Sparse SfM"] = round(time.time() - t_sfm, 2)

                    winning_info = adapter.select_largest_sparse_model(workspace / "sparse")
                    active_sparse_dir = winning_info.model_dir

                    if pipeline_manifest is not None:
                        total_v = len(frame_files)
                        pipeline_manifest.sfm = {
                            "registered_views": winning_info.registered_views,
                            "total_views": total_v,
                            "registration_ratio": round(winning_info.registered_views / total_v, 4) if total_v > 0 else 0.0,
                            "num_cameras": winning_info.num_cameras,
                            "sparse_points": winning_info.sparse_points,
                            "winning_model_dir": str(winning_info.model_dir),
                        }
                        pipeline_manifest.mark_stage_complete("sfm")
                        pipeline_manifest.save(workspace)

        if active_sparse_dir is None:
            raise ReconstructionInvalidInputError(
                "Missing reconstruction inputs. Please specify --sparse-dir (and --images for dense)."
            )

        resolved_sparse = adapter.resolve_sparse_model_dir(active_sparse_dir)
        effective_stop_after = "sfm" if sfm_only else stop_after

        if effective_stop_after == "sfm":
            if active_images_dir is not None and active_images_dir.is_dir():
                dense_ws = ensure_directory(workspace / "dense")
                t_undistort = time.time()
                cmd_undistort = adapter.build_image_undistorter_args(
                    binary_path=resolved_bin,
                    image_path=active_images_dir,
                    input_path=resolved_sparse,
                    output_path=dense_ws,
                    output_type="COLMAP",
                )
                adapter._execute_step("image_undistorter", cmd_undistort, cwd=dense_ws, timeout=timeout)
                stage_timings["Image Undistortion"] = round(time.time() - t_undistort, 2)
                if pipeline_manifest is not None:
                    pipeline_manifest.mark_stage_complete("undistort")
                    pipeline_manifest.save(workspace)

            total_time = round(time.time() - t0_total, 2)
            stage_timings["Total Turnaround Time"] = total_time
            return {
                "success": True,
                "mode": "sfm_only",
                "engine": engine,
                "mesh_path": None,
                "raw_mesh_path": None,
                "sparse_model_dir": resolved_sparse,
                "sfm": pipeline_manifest.sfm if pipeline_manifest is not None else {},
                "pipeline_manifest_path": (workspace / "pipeline_manifest.json") if pipeline_manifest is not None else None,
                "execution_time_seconds": total_time,
                "workspace": workspace,
                "stage_timings": stage_timings,
                "total_turnaround_seconds": total_time,
            }

        # 3. Reconstruction step execution via selected engine (2DGS+TSDF or classical COLMAP)
        aligned_by_2dgs = False
        if engine == "2dgs":
            logger.info("Executing Masked 2DGS + TSDF reconstruction pipeline...")
            if active_images_dir is None or not active_images_dir.is_dir():
                raise ReconstructionInvalidInputError(
                    "2DGS reconstruction requires valid --images directory."
                )

            from loom.geometry.alignment import CoordinateNormalizer
            from loom.reconstruction.masking import ForegroundMasker
            from loom.reconstruction.visual_hull import VisualHullFilter

            dense_ws = ensure_directory(workspace / "dense")

            # 3a. COLMAP Image Undistorter ONLY (skip PatchMatch Stereo & COLMAP Poisson)
            if (
                pipeline_manifest is not None
                and pipeline_manifest.is_stage_complete("undistort")
                and (dense_ws / "images").is_dir()
                and any((dense_ws / "sparse").glob("cameras.*"))
            ):
                logger.info("[RESUME] Reusing cached undistorted workspace in %s", dense_ws)
            else:
                t_undistort = time.time()
                cmd_undistort = adapter.build_image_undistorter_args(
                    binary_path=resolved_bin,
                    image_path=active_images_dir,
                    input_path=resolved_sparse,
                    output_path=dense_ws,
                    output_type="COLMAP",
                )
                adapter._execute_step("image_undistorter", cmd_undistort, cwd=dense_ws, timeout=timeout)
                stage_timings["Image Undistortion"] = round(time.time() - t_undistort, 2)
                if pipeline_manifest is not None:
                    pipeline_manifest.mark_stage_complete("undistort")
                    pipeline_manifest.save(workspace)

            undist_images_dir = dense_ws / "images"
            undist_sparse_dir = adapter.resolve_sparse_model_dir(dense_ws / "sparse")

            # 3b. Semantic foreground masking on undistorted images (bounded CPU ONNX + 4x4 audit)
            debug_masks_dir = ensure_directory(workspace / "debug_masks")
            masks_dir = workspace / "masks"
            if (
                pipeline_manifest is not None
                and pipeline_manifest.is_stage_complete("mask")
                and pipeline_manifest.masking.get("valid_views")
                and masks_dir.is_dir()
            ):
                logger.info(
                    "[RESUME] Reusing cached foreground masks (%d/%d valid views) in %s",
                    len(pipeline_manifest.masking["valid_views"]),
                    pipeline_manifest.masking.get("total_frames", 0),
                    masks_dir,
                )
                valid_views_list = list(pipeline_manifest.masking["valid_views"])
                masking_dict = dict(pipeline_manifest.masking)
            else:
                t_mask = time.time()
                masker = ForegroundMasker()
                try:
                    mask_res = masker.mask_directory(
                        undist_images_dir,
                        masks_dir,
                        debug_dir=debug_masks_dir,
                    )
                finally:
                    masker.close()
                stage_timings["Foreground Masking"] = round(time.time() - t_mask, 2)
                valid_views_list = list(mask_res.valid_views)
                masking_dict = mask_res.to_manifest_dict()
                if pipeline_manifest is not None:
                    pipeline_manifest.masking = masking_dict
                    pipeline_manifest.mark_stage_complete("mask")
                    pipeline_manifest.save(workspace)

            if effective_stop_after == "mask":
                total_time = round(time.time() - t0_total, 2)
                stage_timings["Total Turnaround Time"] = total_time
                return {
                    "success": True,
                    "mode": "stop_after_mask",
                    "engine": engine,
                    "mesh_path": None,
                    "raw_mesh_path": None,
                    "masking": masking_dict,
                    "pipeline_manifest_path": (workspace / "pipeline_manifest.json") if pipeline_manifest is not None else None,
                    "execution_time_seconds": total_time,
                    "workspace": workspace,
                    "stage_timings": stage_timings,
                    "total_turnaround_seconds": total_time,
                }

            # 3c. True Multi-View Visual-Hull Filter + DBSCAN Core on UNDISTORTED dense/sparse/
            vh_ply_path = debug_masks_dir / "visual_hull_points.ply"
            if (
                pipeline_manifest is not None
                and pipeline_manifest.is_stage_complete("visual_hull")
                and pipeline_manifest.visual_hull.get("object_radius")
                and vh_ply_path.is_file()
            ):
                logger.info(
                    "[RESUME] Reusing cached visual-hull core (%d pts, object_radius=%.4f) from %s",
                    pipeline_manifest.visual_hull.get("foreground_points", 0),
                    float(pipeline_manifest.visual_hull["object_radius"]),
                    vh_ply_path,
                )
                vh_dict = dict(pipeline_manifest.visual_hull)
            else:
                t_vh = time.time()
                vh_filter = VisualHullFilter()
                vh_res = vh_filter.run(
                    undistorted_sparse_dir=undist_sparse_dir,
                    masks_dir=masks_dir,
                    output_ply_path=vh_ply_path,
                    valid_view_names=valid_views_list,
                )
                stage_timings["Visual-Hull Filtering"] = round(time.time() - t_vh, 2)
                vh_dict = vh_res.to_manifest_dict()
                if pipeline_manifest is not None:
                    pipeline_manifest.visual_hull = vh_dict
                    pipeline_manifest.mark_stage_complete("visual_hull")
                    pipeline_manifest.save(workspace)

            if effective_stop_after == "visual_hull":
                total_time = round(time.time() - t0_total, 2)
                stage_timings["Total Turnaround Time"] = total_time
                return {
                    "success": True,
                    "mode": "stop_after_visual_hull",
                    "engine": engine,
                    "mesh_path": None,
                    "raw_mesh_path": None,
                    "masking": masking_dict,
                    "visual_hull": vh_dict,
                    "pipeline_manifest_path": (workspace / "pipeline_manifest.json") if pipeline_manifest is not None else None,
                    "execution_time_seconds": total_time,
                    "workspace": workspace,
                    "stage_timings": stage_timings,
                    "total_turnaround_seconds": total_time,
                }

            # 3d. Masked 2D Gaussian Splatting + 3e. Masked TSDF (resumable when --from-stage export)
            raw_2dgs_mesh_path = workspace / "mesh_2dgs_raw.ply"
            can_resume_tsdf = (
                pipeline_manifest is not None
                and pipeline_manifest.is_stage_complete("tsdf")
                and raw_2dgs_mesh_path.is_file()
                and effective_stop_after not in ("2dgs", "tsdf")
            )

            if can_resume_tsdf:
                logger.info("[RESUME] Reusing cached 2DGS + TSDF raw mesh: %s", raw_2dgs_mesh_path)
                gs_dict = dict(pipeline_manifest.gaussian_2dgs)
                tsdf_dict = dict(pipeline_manifest.tsdf)
                tsdf_mesh_path = raw_2dgs_mesh_path
            else:
                from loom.reconstruction.gaussian_2dgs import (
                    Gaussian2DGSConfig,
                    Gaussian2DGSReconstructor,
                )
                from loom.reconstruction.tsdf_mesh import TsdfMeshExtractor

                t_2dgs = time.time()
                gs_cfg = Gaussian2DGSConfig(
                    turbo=turbo,
                    max_image_size=min(max_image_size, 720 if turbo else 960),
                    max_gaussians=150_000,
                    packed=False,
                )
                reconstructor = Gaussian2DGSReconstructor(gs_cfg)
                trained_model = reconstructor.train(
                    images_dir=undist_images_dir,
                    masks_dir=masks_dir,
                    sparse_dir=undist_sparse_dir,
                    valid_view_names=valid_views_list,
                    init_ply_path=vh_dict.get("filtered_ply_path"),
                    object_center=vh_dict.get("object_center"),
                    object_radius=vh_dict.get("object_radius"),
                    debug_dir=workspace / "debug_2dgs",
                )
                stage_timings["Masked 2DGS Optimization"] = round(time.time() - t_2dgs, 2)
                gs_dict = trained_model.to_manifest_dict()
                if pipeline_manifest is not None:
                    pipeline_manifest.gaussian_2dgs = gs_dict
                    pipeline_manifest.mark_stage_complete("2dgs")
                    pipeline_manifest.save(workspace)

                if effective_stop_after == "2dgs":
                    total_time = round(time.time() - t0_total, 2)
                    stage_timings["Total Turnaround Time"] = total_time
                    return {
                        "success": True,
                        "mode": "stop_after_2dgs",
                        "engine": engine,
                        "mesh_path": None,
                        "raw_mesh_path": None,
                        "masking": masking_dict,
                        "visual_hull": vh_dict,
                        "gaussian_2dgs": gs_dict,
                        "pipeline_manifest_path": (workspace / "pipeline_manifest.json") if pipeline_manifest is not None else None,
                        "execution_time_seconds": total_time,
                        "workspace": workspace,
                        "stage_timings": stage_timings,
                        "total_turnaround_seconds": total_time,
                    }

                # 3e. Masked TSDF Volumetric Fusion & Marching Cubes around tight surfel core
                t_tsdf = time.time()
                tsdf_extractor = TsdfMeshExtractor()
                tsdf_res = tsdf_extractor.extract_from_2dgs(
                    reconstructor=reconstructor,
                    trained_model=trained_model,
                    output_path=raw_2dgs_mesh_path,
                )
                stage_timings["TSDF Mesh Extraction"] = round(time.time() - t_tsdf, 2)
                tsdf_dict = tsdf_res.to_manifest_dict()
                tsdf_mesh_path = tsdf_res.mesh_path
                if pipeline_manifest is not None:
                    pipeline_manifest.tsdf = tsdf_dict
                    pipeline_manifest.mark_stage_complete("tsdf")
                    pipeline_manifest.save(workspace)

                if effective_stop_after == "tsdf":
                    total_time = round(time.time() - t0_total, 2)
                    stage_timings["Total Turnaround Time"] = total_time
                    return {
                        "success": True,
                        "mode": "stop_after_tsdf",
                        "engine": engine,
                        "mesh_path": tsdf_mesh_path,
                        "raw_mesh_path": tsdf_mesh_path,
                        "masking": masking_dict,
                        "visual_hull": vh_dict,
                        "gaussian_2dgs": gs_dict,
                        "tsdf": tsdf_dict,
                        "pipeline_manifest_path": (workspace / "pipeline_manifest.json") if pipeline_manifest is not None else None,
                        "execution_time_seconds": total_time,
                        "workspace": workspace,
                        "stage_timings": stage_timings,
                        "total_turnaround_seconds": total_time,
                    }

            # 3f. Fit canonical support plane on UNMASKED sparse points + camera-centroid polarity
            t_align = time.time()
            sparse_meta = adapter.extract_sparse_scene_metadata(undist_sparse_dir)
            sparse_pts = sparse_meta.points_xyz
            cam_centers = sparse_meta.camera_centers
            normalizer = CoordinateNormalizer()
            support_plane = normalizer.fit_support_plane_ransac(
                sparse_pts,
                threshold=normalizer.distance_threshold,
                camera_centers=cam_centers,
            )
            _, _, T_align = normalizer.compute_alignment_matrix(
                support_plane,
                sparse_pts,
                center_elevated=True,
            )
            stage_timings["Canonical Support Alignment"] = round(time.time() - t_align, 2)
            logger.info(
                "Canonical alignment computed from unmasked sparse points (normal=%s, inliers=%d)",
                support_plane.normal,
                len(support_plane.inlier_indices),
            )

            # 3g. Apply canonical alignment transform T_align synchronously to vertices and normals
            loaded_2dgs = trimesh.load(str(tsdf_mesh_path), process=False)
            if isinstance(loaded_2dgs, trimesh.Scene):
                loaded_2dgs = trimesh.util.concatenate(list(loaded_2dgs.geometry.values()))
            loaded_2dgs.apply_transform(T_align)
            _ = loaded_2dgs.vertex_normals
            aligned_2dgs_path = workspace / "aligned_mesh_2dgs.ply"
            loaded_2dgs.export(str(aligned_2dgs_path))

            # 3h. Feature-preserving Taubin smoothing, planar base cut, guaranteed watertight
            # solidification, quadric decimation, float64 metric scaling & PrintabilityGate
            t_solid = time.time()
            from loom.mesh.processor import MeshProcessor

            solid_res = MeshProcessor.solidify_for_print(
                loaded_2dgs,
                target_length_mm=float(target_length if target_length is not None else 200.0),
                base_z=base_z,
            )
            stage_timings["Polish & Watertight Solidification"] = round(time.time() - t_solid, 2)

            solid_mesh_path = workspace / "solid_mesh_2dgs.ply"
            solid_res.mesh.export(str(solid_mesh_path))

            raw_mesh_path = aligned_2dgs_path
            final_mesh_path = solid_mesh_path
            aligned_by_2dgs = True
            solidified_2dgs_res = solid_res

            checkpoints = export_reconstruction_checkpoints(
                run_name=run_name,
                output_root=output_root,
                sparse_source=undist_sparse_dir,
                mesh_source=raw_mesh_path,
            )
        elif dense:
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

        if engine != "2dgs":
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
    if align_support and not turbo and not aligned_by_2dgs and raw_mesh_path and raw_mesh_path.is_file():
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

    # 4b. Optional Phase 3 mesh repair (legacy COLMAP & mesh-only; 2DGS already polished & solidified in 3h)
    if clean_mesh and not aligned_by_2dgs and raw_mesh_path and raw_mesh_path.is_file():
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
    scale_factor: float | None = solidified_2dgs_res.scale_factor if solidified_2dgs_res is not None else None
    if scale and not aligned_by_2dgs and final_mesh_path and final_mesh_path.is_file():
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

    # 6. Optional Target-Length Uniform Scaling (2DGS already scaled in float64 inside solidify_for_print)
    mesh_to_export: Any = solidified_2dgs_res.mesh if solidified_2dgs_res is not None else final_mesh_path
    if (
        not aligned_by_2dgs
        and target_length is not None
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
        logger.info("[EXPORT] Running PrintabilityGate and binary STL export...")
        from loom.config.models import ExportConfig
        from loom.export.stl import StlExporter
        from loom.printability.exceptions import PrintabilityValidationError

        if engine == "2dgs" and mesh_only is None and stl_dir is None:
            target_stl_dir = workspace
            target_stl_file = workspace / "loom_output.stl"
            target_manifest_file: Path | None = workspace / "printability_manifest.json"
        else:
            target_stl_dir = Path(stl_dir or "outputs/stl")
            base_name = final_mesh_path.stem if final_mesh_path else "model"
            clean_base = base_name.replace("scaled_", "").replace("_scaled", "")
            target_stl_file = (
                (target_stl_dir / "loom_output.stl")
                if (engine == "2dgs" and mesh_only is None)
                else (target_stl_dir / f"{clean_base}_metric.stl")
            )
            target_manifest_file = (
                (target_stl_dir / "printability_manifest.json")
                if (engine == "2dgs" and mesh_only is None)
                else None
            )

        exporter = StlExporter(config=ExportConfig(output_dir=target_stl_dir), enforce_printability_gate=True)
        try:
            exported_stl_path = exporter.export(
                mesh_path=mesh_to_export,
                output_stl_path=target_stl_file,
                manifest_path=target_manifest_file,
                scale_factor_applied=scale_factor if scale_factor is not None else 1.0,
                project_name="LOOM_DEMO",
                enforce_gate=True,
            )
            manifest_path = exporter.last_manifest_path
            logger.info("[EXPORT] Validated metric binary STL exported: %s (manifest: %s)", exported_stl_path, manifest_path)
        except PrintabilityValidationError as p_exc:
            logger.warning(
                "Printability gate validation warning: %s. Proceeding with STL export...",
                p_exc,
            )
            exported_stl_path = exporter.export(
                mesh_path=mesh_to_export,
                output_stl_path=target_stl_file,
                manifest_path=target_manifest_file,
                scale_factor_applied=scale_factor if scale_factor is not None else 1.0,
                project_name="LOOM_DEMO",
                enforce_gate=False,
                validation_result=getattr(p_exc, "validation_result", None),
            )
            manifest_path = exporter.last_manifest_path
            logger.info("[EXPORT] Binary STL exported with gate warnings: %s (manifest: %s)", exported_stl_path, manifest_path)
        except Exception as exc:
            logger.error("STL export failed manufacturing readiness gate: %s", exc)
            if not allow_sparse_fallback and mesh_only is None:
                raise
        stage_timings["Scaling & Validated STL Export"] = round(time.time() - t_export, 2)

        if exported_stl_path is not None and solidified_2dgs_res is not None:
            export_dict = {
                "stl_path": str(exported_stl_path),
                "manifest_path": str(manifest_path) if manifest_path is not None else None,
                "vertices": int(len(solidified_2dgs_res.mesh.vertices)),
                "faces": int(len(solidified_2dgs_res.mesh.faces)),
                "is_watertight": bool(solidified_2dgs_res.is_watertight),
                "is_winding_consistent": bool(solidified_2dgs_res.is_winding_consistent),
                "volume_cm3": round(float(solidified_2dgs_res.volume_mm3) / 1000.0, 4),
                "extents_mm": [round(float(e), 3) for e in solidified_2dgs_res.extents_mm],
                "z_min_mm": round(float(solidified_2dgs_res.z_min_mm), 6),
                "solidification_method": solidified_2dgs_res.solidification_method,
            }
            if pipeline_manifest is not None:
                pipeline_manifest.export = export_dict
                pipeline_manifest.mark_stage_complete("export")
                pipeline_manifest.save(workspace)

    total_time = round(time.time() - t0_total, 2)
    stage_timings["Total Turnaround Time"] = total_time

    return {
        "success": True,
        "mode": "2dgs" if engine == "2dgs" else ("dense" if dense else "sparse_diagnostic_preview"),
        "engine": engine,
        "mesh_path": final_mesh_path,
        "raw_mesh_path": raw_mesh_path,
        "point_cloud_path": getattr(reconstruction_artifact, "point_cloud_path", None),
        "execution_time_seconds": total_time,
        "scale_factor": scale_factor,
        "workspace": workspace,
        "checkpoints": checkpoints,
        "masking": masking_dict,
        "visual_hull": vh_dict,
        "gaussian_2dgs": gs_dict,
        "tsdf": tsdf_dict,
        "export": export_dict,
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
        default=None,
        help="Output directory for validated metric STL and build manifest (defaults to <output-dir> for 2dgs or outputs/stl for colmap).",
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
        default=130,
        help="Maximum number of frames to extract from video (default: 130).",
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
        "--engine",
        default="2dgs",
        choices=["2dgs", "colmap"],
        help="Reconstruction engine: '2dgs' (Masked 2D Gaussian Splatting + TSDF, default) or 'colmap' (PatchMatch + Poisson).",
    )
    parser.add_argument(
        "--turbo",
        action="store_true",
        default=False,
        help="Enable Turbo Pipeline: caps frames and resolution (720px for 2DGS / 960px for COLMAP), GPU sequential matching, "
             "3500 2DGS iterations, support plane normalization, and validated STL export.",
    )
    parser.add_argument(
        "--sfm-only",
        action="store_true",
        default=False,
        help="Backward-compatible alias for '--stop-after sfm'.",
    )
    parser.add_argument(
        "--stop-after",
        default=None,
        choices=["sfm", "mask", "visual_hull", "2dgs", "tsdf", "export"],
        help="Stop cleanly after a diagnostic stage gate ('sfm', 'mask', 'visual_hull', '2dgs', 'tsdf', or 'export').",
    )
    parser.add_argument(
        "--from-stage",
        default=None,
        choices=["frames", "sfm", "undistort", "mask", "visual_hull", "2dgs", "tsdf", "export"],
        help="Invalidate cached manifest stages from this stage onward while reusing verified upstream stages.",
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
        args.max_image_size = min(args.max_image_size, 720 if args.engine == "2dgs" else 960)
        if not args.clean_mesh:
            args.clean_mesh = True
            args.remove_floor = args.engine == "colmap"
            args.cap_base = True
        args.align_support = False
        if args.target_length is None:
            args.target_length = 200.0
        if not args.export_stl:
            args.export_stl = True
        if args.base_z is None and args.engine == "colmap":
            args.base_z = 0.005
        if args.max_frames in (42, 65, 75, 130):
            args.max_frames = 68

    if args.engine == "2dgs" and not args.mesh_only:
        if not args.clean_mesh:
            args.clean_mesh = True
            args.cap_base = True
        args.remove_floor = False

    if args.mesh_only:
        # In mesh-only mode, enable cleaning and STL export by default unless explicitly disabled
        if not args.clean_mesh:
            args.clean_mesh = True
            args.remove_floor = True
            args.cap_base = True
        if not args.export_stl:
            args.export_stl = True

    print("\n" + "=" * 65)
    print("VIDEO2PRINT: End-to-End 3D Reconstruction Pipeline")
    print("=" * 65)
    if args.mesh_only:
        print(f"Mode:                  Mesh-Only Direct Processing ({args.mesh_only})")
    else:
        engine_label = "Masked 2DGS + TSDF" if args.engine == "2dgs" else "Classical COLMAP MVS"
        eff_stop = "sfm" if args.sfm_only else args.stop_after
        if eff_stop:
            mode_label = f"Stage Gate (--stop-after {eff_stop})"
        elif args.engine == "2dgs":
            mode_label = "Turbo 2DGS + TSDF" if args.turbo else "Standard 2DGS + TSDF"
        else:
            mode_label = (
                "Turbo Dense MVS"
                if args.turbo
                else ("Dense MVS" if args.dense else "Sparse Diagnostic Preview")
            )
        print(f"Engine:                {engine_label}")
        print(f"Mode:                  {mode_label}")
        print(f"Turbo Mode:            {args.turbo}")
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
            engine=args.engine,
            sfm_only=args.sfm_only,
            stop_after=args.stop_after,
            from_stage=args.from_stage,
        )
        print("\n" + "=" * 65)
        print("DEMO EXECUTION SUCCESSFUL")
        print("=" * 65)
        print(f"Generated Mesh:        {summary['mesh_path']}")
        print(f"Mode:                  {summary['mode']}")
        print(f"Execution Time:        {summary['execution_time_seconds']:.2f}s")
        if summary.get("masking"):
            m_info = summary["masking"]
            print(
                f"Masking Views:         {len(m_info.get('valid_views', []))} / {m_info.get('total_frames', 0)} valid "
                f"(median coverage: {m_info.get('median_coverage', 0.0) * 100.0:.1f}%)"
            )
            print(f"Mask Contact Sheet:    {m_info.get('contact_sheet_path')}")
        if summary.get("visual_hull"):
            vh_info = summary["visual_hull"]
            print(
                f"Visual-Hull Points:    {vh_info.get('total_sparse_points', 0)} -> {vh_info.get('foreground_points', 0)} "
                f"(ratio >= {vh_info.get('hit_ratio_threshold_used', 0.0):.2f})"
            )
            print(
                f"Radii (obj vs scene):  object_radius={vh_info.get('object_radius', 0.0):.4f} "
                f"vs scene_radius={vh_info.get('scene_radius', 0.0):.4f}"
            )
            print(f"Visual-Hull PLY:       {vh_info.get('filtered_ply_path')}")
        if summary.get("gaussian_2dgs"):
            g_info = summary["gaussian_2dgs"]
            print(
                f"2DGS Optimization:     {g_info.get('iterations', 0)} iters | "
                f"{g_info.get('init_surfels', 0)} -> {g_info.get('final_surfels', 0)} surfels | "
                f"loss={g_info.get('final_loss', 0.0):.4f} | peak VRAM={g_info.get('peak_vram_mib', 0.0):.0f} MiB"
            )
        if summary.get("tsdf"):
            t_info = summary["tsdf"]
            print(
                f"TSDF Mesh Extraction:  {t_info.get('vertices', 0)} verts, {t_info.get('faces', 0)} faces | "
                f"tight_radius={t_info.get('tight_radius', 0.0):.4f}, voxel={t_info.get('voxel_length', 0.0):.5f}"
            )
            print(f"Raw TSDF Mesh PLY:     {t_info.get('raw_mesh_path')}")
        if summary.get("scale_factor"):
            print(f"Scale Factor:          {summary['scale_factor']:.5f}")
        if summary.get("export"):
            e_info = summary["export"]
            print(
                f"Solidification:        method={e_info.get('solidification_method')} | "
                f"{e_info.get('vertices', 0)} verts, {e_info.get('faces', 0)} faces | "
                f"watertight={e_info.get('is_watertight')} | vol={e_info.get('volume_cm3', 0.0):.2f} cm^3"
            )
            print(
                f"Metric Extents:        {e_info.get('extents_mm')} mm | Z_min={e_info.get('z_min_mm', 0.0):.6f} mm"
            )
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

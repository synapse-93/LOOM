"""CLI entrypoint for running LOOM as a module (`python -m loom`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loom import __version__
from loom.config.loader import load_config
from loom.config.models import LoomConfig
from loom.pipeline.runner import run_phase1_pipeline, run_phase3_mesh_pipeline
from loom.reconstruction.models import ReconstructionStatus
from loom.utils.logging import get_logger, setup_logging

logger = get_logger("loom.cli")


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="loom",
        description="VIDEO2PRINT: Smartphone Video to 3D Printable Object (Phase 1: Video Ingest & Keyframe Selection)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"loom {__version__}",
    )
    parser.add_argument(
        "--video",
        "-v",
        type=Path,
        default=None,
        help="Path to input smartphone video file.",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to YAML configuration file.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Optional override for pipeline outputs directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and stage prerequisites without executing compute.",
    )
    parser.add_argument(
        "--reconstruct",
        action="store_true",
        help="Execute 3D reconstruction stage on selected keyframes (Phase 2).",
    )
    parser.add_argument(
        "--meshroom-path",
        type=Path,
        default=None,
        help="Explicit path to meshroom_batch executable binary.",
    )
    parser.add_argument(
        "--mesh",
        "-m",
        type=Path,
        default=None,
        help="Path to raw 3D mesh (.obj, .ply, .stl) for Phase 3 cleaning and repair.",
    )
    parser.add_argument(
        "--clean-mesh",
        action="store_true",
        help="Execute Phase 3 geometry cleaning and repair on raw mesh.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level.",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="subcommand", help="Optional command mode")
    geom_parser = subparsers.add_parser("geometry", help="Phase 3 raw geometry & mesh processing")
    geom_parser.add_argument(
        "--input",
        "-i",
        type=Path,
        required=False,
        default=None,
        help="Path to input 3D mesh file (.obj, .ply, .stl)",
    )
    geom_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to YAML configuration file.",
    )
    geom_parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Optional override for pipeline outputs directory.",
    )

    args = parser.parse_args(argv)
    log_level = getattr(args, "log_level", "INFO")
    setup_logging(level=log_level)

    logger.info("Initializing LOOM (version %s)", __version__)

    config_path = getattr(args, "config", None)
    if config_path is not None:
        try:
            config = load_config(config_path)
            logger.info("Loaded configuration: '%s' from %s", config.name, config_path)
        except Exception as exc:
            logger.error("Failed to load configuration: %s", exc)
            return 1
    else:
        config = LoomConfig()
        logger.info("Using default configuration ('%s')", config.name)

    output_dir_arg = getattr(args, "output_dir", None)
    if output_dir_arg is not None:
        config.output_dir = output_dir_arg

    meshroom_path_arg = getattr(args, "meshroom_path", None)
    if meshroom_path_arg is not None:
        config.reconstruction.binary_path = meshroom_path_arg

    # Determine if this is a standalone mesh processing run
    target_mesh = None
    if getattr(args, "subcommand", None) == "geometry":
        target_mesh = getattr(args, "input", None) or getattr(args, "mesh", None)
    elif getattr(args, "mesh", None) is not None:
        target_mesh = args.mesh

    if target_mesh is not None:
        mesh_path = Path(target_mesh).resolve()
        if not mesh_path.is_file():
            logger.error("Input mesh file does not exist: %s", mesh_path)
            return 1

        dry_run_active = getattr(args, "dry_run", False)
        if dry_run_active:
            logger.info("Dry-run mode selected. Validating mesh file: %s", mesh_path)
            logger.info("Dry-run completed successfully.")
            return 0

        logger.info("Executing Phase 3 raw geometry & mesh processing on: %s", mesh_path)
        mesh_result, report_path = run_phase3_mesh_pipeline(
            mesh_path=mesh_path,
            config=config,
            output_dir=output_dir_arg,
        )

        diag_b = mesh_result.diagnostics_before
        diag_a = mesh_result.diagnostics_after
        comp_act = mesh_result.components_action
        clean_act = mesh_result.cleanup_action
        rep_act = mesh_result.repair_action

        print("\n" + "=" * 65)
        print("LOOM GEOMETRY PROCESSING - Phase 3 Summary")
        print("=" * 65)


        print(f"Input Mesh:             {mesh_path.name}")
        if diag_b:
            print("\nInitial Diagnostics:")
            print(f"  Vertices:             {diag_b.vertex_count}")
            print(f"  Faces:                {diag_b.face_count}")
            print(f"  Components:           {diag_b.component_count}")
            print(f"  Boundary Edges:       {diag_b.boundary_edge_count}")
            print(f"  Boundary Loops:       {diag_b.boundary_loop_count}")
            print(f"  Degenerate Faces:     {diag_b.degenerate_face_count}")
            print(f"  Duplicate Faces:      {diag_b.duplicate_face_count}")
            print(f"  Unreferenced Verts:   {diag_b.unreferenced_vertex_count}")
            print(f"  Status:               {diag_b.status}")

        print("\nProcessing Actions:")
        print("  [OK] Validate mesh and load geometry")
        if comp_act:
            print(f"  [OK] Component filtering ({comp_act.strategy}): removed {comp_act.removed_components} components")
        if clean_act:
            print(f"  [OK] Invalid/degenerate cleanup: removed {clean_act.degenerate_faces_removed} degenerate, {clean_act.unreferenced_vertices_removed} unreferenced")
        if rep_act:
            print(f"  [OK] Conservative repair: attempted {rep_act.repairs_attempted}, successfully closed {rep_act.repairs_successful} loops")
        print("  [OK] Mesh normalization and outward normal unification")


        if diag_a:
            print("\nCleaned Mesh Diagnostics:")
            print(f"  Vertices:             {diag_a.vertex_count}")
            print(f"  Faces:                {diag_a.face_count}")
            print(f"  Components:           {diag_a.component_count}")
            print(f"  Boundary Edges:       {diag_a.boundary_edge_count}")
            print(f"  Boundary Loops:       {diag_a.boundary_loop_count}")
            print(f"  Watertight:           {diag_a.is_watertight}")
            print(f"  Status:               {diag_a.status}")

        print("\nOutputs:")
        print(f"  Cleaned Intermediate: {mesh_result.output_mesh_path}")
        print(f"  Geometry Report JSON: {report_path}")
        print(f"  Execution Time:       {mesh_result.execution_time_seconds:.4f} seconds")
        if mesh_result.error_message:
            print(f"  Error Details:        {mesh_result.error_message}")
        print("-" * 65)
        print(f"Status: {mesh_result.status}")
        print("=" * 65 + "\n")
        return 0 if mesh_result.success else 1

    video_input = getattr(args, "video", None) or config.input_video

    if getattr(args, "dry_run", False):
        logger.info("Dry-run mode selected. Validating configuration and prerequisites.")
        if video_input is not None:
            p = Path(video_input).resolve()
            if not p.is_file():
                logger.error("Input video file does not exist: %s", p)
                return 1
            logger.info("Input video verified: %s (%d bytes)", p.name, p.stat().st_size)
        logger.info("Dry-run completed successfully.")
        return 0

    if video_input is None:
        logger.info(
            "No input specified. Use '--video <path>' for video processing, or '--mesh <path>' for geometry processing."
        )
        return 0

    try:
        video_path = Path(video_input).resolve()
        result = run_phase1_pipeline(
            video_path=video_path,
            config=config,
            reconstruct=getattr(args, "reconstruct", False),
            clean_mesh=getattr(args, "clean_mesh", False),
        )

        # Print clean, structured terminal summary
        meta = result.video_artifact
        analysis = result.capture_analysis_artifact
        frames = result.frame_set_artifact

        print("\n" + "=" * 65)
        print("LOOM: Phase 1 Video & Capture Analysis Summary")
        print("=" * 65)
        print(f"Input Video:            {video_path.name}")
        print(f"Resolution:             {meta.resolution[0]}x{meta.resolution[1]}")
        print(f"Framerate:              {meta.fps:.2f} FPS")
        print(f"Duration:               {meta.duration_seconds:.2f} seconds")
        print(f"Source Frame Count:     {meta.frame_count}")
        print(f"Extracted Frame Count:  {len(frames.frame_paths)}")
        print(f"Accepted Keyframes:     {len(analysis.selected_frames)}")
        print(f"Rejected Frames:        {len(analysis.rejected_frames)}")
        print(f"Average Sharpness:      {analysis.average_sharpness:.2f}")
        print(f"Viewpoint Diversity:    {analysis.coverage_score:.3f}")
        print(f"Run ID:                 {result.run_id}")
        print(f"Selected Frames Dir:    {result.selected_frames_dir}")
        print(f"Capture Report JSON:    {result.capture_report_path}")
        print(f"Metadata Report JSON:   {result.metadata_report_path}")

        print("\nCapture Guidance:")
        for note in analysis.guidance_notes:
            print(f"  * {note}")

        print("-" * 65)
        if result.reconstruction_result is None:
            print("Status: READY FOR RECONSTRUCTION (Phase 1 Complete)")
            print("=" * 65 + "\n")
        else:
            recon = result.reconstruction_result
            status_name = recon.status.value.upper() if recon.status else ("SUCCESS" if recon.success else "FAILED")
            print("\n" + "=" * 65)
            print("LOOM: Phase 2 3D Reconstruction Summary")
            print("=" * 65)
            print(f"Backend:                {recon.backend}")
            print(f"Status:                 {status_name}")
            print(f"Input Frames:           {recon.input_frames_count}")
            reg_cam = f"{recon.registered_cameras_count}" if recon.registered_cameras_count is not None else "N/A"
            print(f"Registered Cameras:     {reg_cam}")
            reg_ratio = f"{recon.registration_ratio:.1%}" if recon.registration_ratio is not None else "N/A"
            print(f"Registration Ratio:     {reg_ratio}")
            sparse_name = recon.sparse_reconstruction_path.name if recon.sparse_reconstruction_path else "None"
            print(f"Sparse SFM Cloud:       {sparse_name}")
            dense_name = (
                recon.dense_point_cloud_path.name
                if recon.dense_point_cloud_path
                else (recon.point_cloud_path.name if recon.point_cloud_path else "None")
            )
            print(f"Dense Point Cloud:      {dense_name}")
            print(f"Mesh Output:            {recon.mesh_path if recon.mesh_path else 'None'}")
            print(f"Execution Time:         {recon.execution_time_seconds:.2f} seconds")
            print(f"Workspace:              {recon.workspace_path if recon.workspace_path else 'N/A'}")
            print(f"Log File:               {recon.log_path if recon.log_path else 'None'}")
            print(f"Reconstruction Report:  {result.reconstruction_report_path}")
            if recon.error_message:
                print(f"Error Details:          {recon.error_message}")
            print("-" * 65)
            if recon.status == ReconstructionStatus.SUCCESS or recon.success:
                status_text = "RECONSTRUCTION COMPLETED (Raw Mesh Generated)"
            elif recon.status == ReconstructionStatus.PARTIAL:
                status_text = "RECONSTRUCTION PARTIAL (Point Cloud/Poses Generated, Mesh Missing)"
            elif recon.status == ReconstructionStatus.BINARY_UNAVAILABLE:
                status_text = "RECONSTRUCTION BLOCKED (Backend Executable Unavailable on Host)"
            elif recon.status == ReconstructionStatus.TIMEOUT:
                status_text = "RECONSTRUCTION TIMED OUT"
            elif recon.status == ReconstructionStatus.INVALID_INPUT:
                status_text = "RECONSTRUCTION FAILED (Invalid Inputs)"
            elif recon.status == ReconstructionStatus.ARTIFACT_MISSING:
                status_text = "RECONSTRUCTION FAILED (Expected Output Artifact Missing)"
            else:
                status_text = "RECONSTRUCTION FAILED"
            print(f"Status: {status_text}")
            print("=" * 65 + "\n")

        if result.mesh_processing_result is not None:
            mr = result.mesh_processing_result
            diag_b = mr.diagnostics_before
            diag_a = mr.diagnostics_after
            print("\n" + "=" * 65)
            print("LOOM: Phase 3 Geometry & Mesh Processing Summary")
            print("=" * 65)
            if diag_b:
                print(f"Input Mesh Vertices:    {diag_b.vertex_count}")
                print(f"Input Mesh Faces:       {diag_b.face_count}")
            if diag_a:
                print(f"Cleaned Vertices:       {diag_a.vertex_count}")
                print(f"Cleaned Faces:          {diag_a.face_count}")
                print(f"Cleaned Components:     {diag_a.component_count}")
                print(f"Watertight:             {diag_a.is_watertight}")
            print(f"Cleaned Mesh:           {mr.output_mesh_path}")
            print(f"Geometry Report JSON:   {result.geometry_report_path}")
            print(f"Execution Time:         {mr.execution_time_seconds:.4f} seconds")
            print("-" * 65)
            print(f"Status: {mr.status}")
            print("=" * 65 + "\n")

        return 0

    except Exception as exc:
        logger.error("Pipeline execution failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

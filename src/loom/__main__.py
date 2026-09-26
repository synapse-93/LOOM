"""CLI entrypoint for running LOOM as a module (`python -m loom`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loom import __version__
from loom.config.loader import load_config
from loom.config.models import LoomConfig
from loom.pipeline.runner import run_phase1_pipeline
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
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level.",
    )

    args = parser.parse_args(argv)
    setup_logging(level=args.log_level)

    logger.info("Initializing LOOM (version %s)", __version__)

    if args.config is not None:
        try:
            config = load_config(args.config)
            logger.info("Loaded configuration: '%s' from %s", config.name, args.config)
        except Exception as exc:
            logger.error("Failed to load configuration: %s", exc)
            return 1
    else:
        config = LoomConfig()
        logger.info("Using default configuration ('%s')", config.name)

    if args.output_dir is not None:
        config.output_dir = args.output_dir

    video_input = args.video or config.input_video

    if args.dry_run:
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
            "No input video specified. Use '--video <path>' to process a smartphone video."
        )
        return 0

    try:
        video_path = Path(video_input).resolve()
        result = run_phase1_pipeline(video_path=video_path, config=config)

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
        print("Status: READY FOR RECONSTRUCTION (Phase 1 Complete)")
        print("=" * 65 + "\n")

        return 0

    except Exception as exc:
        logger.error("Pipeline execution failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

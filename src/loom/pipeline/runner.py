"""Pipeline runner orchestrating staged execution of VIDEO2PRINT."""

from __future__ import annotations

import datetime
import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from loom.capture.quality import FrameQualityAssessor, FrameQualityResult
from loom.config.models import LoomConfig
from loom.pipeline.artifacts import (
    BaseArtifact,
    CaptureAnalysisArtifact,
    FrameSetArtifact,
    VideoArtifact,
)
from loom.pipeline.stages import PipelineStage
from loom.reconstruction.models import ReconstructionJobConfig, ReconstructionResult
from loom.reconstruction.runner import ReconstructionRunner
from loom.utils.paths import ensure_directory
from loom.video.frames import FrameExtractor
from loom.video.ingest import VideoIngestor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Phase1Result:
    """Consolidated terminal output of the Phase 1 & 2 video-to-keyframes pipeline."""

    run_id: str
    run_dir: Path
    video_artifact: VideoArtifact
    frame_set_artifact: FrameSetArtifact
    capture_analysis_artifact: CaptureAnalysisArtifact
    metadata_report_path: Path
    capture_report_path: Path
    selected_frames_dir: Path
    raw_frames_dir: Path
    quality_results: list[FrameQualityResult]
    reconstruction_result: Optional[ReconstructionResult] = None
    reconstruction_report_path: Optional[Path] = None


class PipelineRunner:
    """Orchestrator for running staged pipeline sequences."""

    def __init__(self, config: LoomConfig) -> None:
        self.config = config
        self._stages: list[PipelineStage[Any, Any]] = []

    def register_stage(self, stage: PipelineStage[Any, Any]) -> None:
        """Register a pipeline stage in sequential order."""
        self._stages.append(stage)

    @property
    def stages(self) -> Sequence[PipelineStage[Any, Any]]:
        """Return registered stages."""
        return tuple(self._stages)

    def dry_run(self, initial_artifact: BaseArtifact) -> dict[str, bool]:
        """Validate preconditions across all registered stages without executing compute.

        Returns:
            Dictionary mapping stage name to boolean readiness status.
        """
        results: dict[str, bool] = {}
        current_artifact: Any = initial_artifact
        for stage in self._stages:
            logger.info("Dry-run checking stage: %s", stage.name)
            is_ready = stage.dry_run(current_artifact, self.config)
            results[stage.name] = is_ready
        return results

    def run(self, initial_artifact: BaseArtifact) -> BaseArtifact:
        """Execute all registered pipeline stages sequentially.

        Raises:
            NotImplementedError: For scaffolded stages that have not been implemented yet.
        """
        current_artifact: Any = initial_artifact
        for stage in self._stages:
            logger.info("Executing stage: %s", stage.name)
            current_artifact = stage.execute(current_artifact, self.config)
        return current_artifact


def run_phase1_pipeline(
    video_path: Path,
    config: LoomConfig,
    run_id: str | None = None,
    reconstruct: bool = False,
) -> Phase1Result:
    """Execute the complete Phase 1 pipeline on a video file.

    Pipeline sequence:
        1. Validate source video file container
        2. Extract video stream metadata without full decoding
        3. Stream & sample video frames sequentially to raw frames directory
        4. Generate machine-readable frame extraction manifest
        5. Evaluate sharpness (Laplacian var), brightness, contrast, and redundancy
        6. Separate accepted keyframes from blurry/redundant/defect frames
        7. Copy accepted keyframes to selected/ directory for future 3D reconstruction
        8. Write metadata.json and capture_analysis.json reports

    Args:
        video_path: Path to target smartphone video.
        config: LoomConfig settings.
        run_id: Optional explicit run identifier; generated if None.

    Returns:
        Phase1Result containing artifacts, directories, and detailed metrics.
    """
    resolved_video = Path(video_path).resolve()
    if not resolved_video.is_file():
        raise FileNotFoundError(f"Input video file not found: {resolved_video}")

    # Generate collision-safe run ID
    if run_id is None:
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", resolved_video.stem)
        run_id = f"run_{timestamp_str}_{sanitized_stem}"

    # Build standardized output directory structure
    base_run_dir = ensure_directory(config.output_dir / "runs" / run_id)
    raw_frames_dir = ensure_directory(base_run_dir / "frames" / "raw")
    selected_frames_dir = ensure_directory(base_run_dir / "frames" / "selected")
    reports_dir = ensure_directory(base_run_dir / "reports")
    logs_dir = ensure_directory(base_run_dir / "logs")

    # Add file handler to loom logger for this run
    log_file = logs_dir / "pipeline.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    loom_logger = logging.getLogger("loom")
    if loom_logger.level > logging.INFO or loom_logger.level == logging.NOTSET:
        loom_logger.setLevel(logging.INFO)
    loom_logger.addHandler(file_handler)

    try:
        logger.info("=== Starting LOOM Phase 1 Run: %s ===", run_id)
        logger.info("Source video: %s", resolved_video)

        # Stage 1: Video Ingest
        ingestor = VideoIngestor()
        video_artifact = ingestor.ingest(resolved_video)

        # Write metadata.json report
        metadata_report_path = reports_dir / "metadata.json"
        metadata_dict = {
            "file_name": resolved_video.name,
            "file_path": str(resolved_video),
            "file_size_bytes": video_artifact.metadata.get("file_size_bytes", 0),
            "duration_seconds": video_artifact.duration_seconds,
            "frame_count": video_artifact.frame_count,
            "fps": video_artifact.fps,
            "width": video_artifact.resolution[0],
            "height": video_artifact.resolution[1],
            "resolution": {
                "width": video_artifact.resolution[0],
                "height": video_artifact.resolution[1],
            },
            "codec": video_artifact.metadata.get("codec", "unknown"),
        }
        with open(metadata_report_path, "w", encoding="utf-8") as f:
            json.dump(metadata_dict, f, indent=2)

        # Stage 2: Streaming Frame Extraction
        extractor = FrameExtractor(config=config.video)
        frame_set_artifact = extractor.extract(resolved_video, raw_frames_dir)

        # Stage 3: Frame Quality Analysis & Redundancy Filtering
        assessor = FrameQualityAssessor(config=config.capture)
        capture_analysis_artifact, quality_results = assessor.assess_and_filter(
            frame_set_artifact.frame_paths
        )

        # Copy selected frames to dedicated selected/ directory
        selected_copied_paths: list[Path] = []
        for src_frame in capture_analysis_artifact.selected_frames:
            dest_frame = selected_frames_dir / src_frame.name
            shutil.copy2(src_frame, dest_frame)
            selected_copied_paths.append(dest_frame)

        # Update capture artifact with copied paths
        final_capture_artifact = CaptureAnalysisArtifact(
            stage_name="capture_quality",
            selected_frames=selected_copied_paths,
            rejected_frames=capture_analysis_artifact.rejected_frames,
            average_sharpness=capture_analysis_artifact.average_sharpness,
            coverage_score=capture_analysis_artifact.coverage_score,
            guidance_notes=capture_analysis_artifact.guidance_notes,
            metadata=capture_analysis_artifact.metadata,
        )

        # Write capture_analysis.json report
        capture_report_path = reports_dir / "capture_analysis.json"
        capture_report_dict = {
            "run_id": run_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "summary": final_capture_artifact.metadata,
            "metadata": final_capture_artifact.metadata,
            "selected_frames": [str(p) for p in final_capture_artifact.selected_frames],
            "rejected_frames": [str(p) for p in final_capture_artifact.rejected_frames],
            "average_sharpness": final_capture_artifact.average_sharpness,
            "viewpoint_diversity_score": final_capture_artifact.coverage_score,
            "guidance_notes": final_capture_artifact.guidance_notes,
            "selected_frames_dir": str(selected_frames_dir),
            "frame_results": [
                {
                    "filename": r.frame_path.name,
                    "sharpness": r.sharpness,
                    "brightness": r.brightness,
                    "contrast": r.contrast,
                    "is_blurry": r.is_blurry,
                    "is_underexposed": r.is_underexposed,
                    "is_overexposed": r.is_overexposed,
                    "is_low_contrast": r.is_low_contrast,
                    "is_redundant": r.is_redundant,
                    "is_accepted": r.is_accepted,
                    "rejection_reasons": list(r.rejection_reasons),
                }
                for r in quality_results
            ],
        }
        with open(capture_report_path, "w", encoding="utf-8") as f:
            json.dump(capture_report_dict, f, indent=2)

        logger.info(
            "Phase 1 complete. %d/%d frames ready for 3D reconstruction in %s",
            len(selected_copied_paths),
            len(frame_set_artifact.frame_paths),
            selected_frames_dir,
        )

        # Stage 4: Optional 3D Reconstruction (Phase 2)
        reconstruction_result: Optional[ReconstructionResult] = None
        reconstruction_report_path: Optional[Path] = None

        if reconstruct:
            logger.info(
                "=== Starting Phase 2: 3D Reconstruction (%s) ===",
                config.reconstruction.backend,
            )
            recon_workspace = ensure_directory(base_run_dir / "reconstruction")
            job_cfg = ReconstructionJobConfig(
                workspace_dir=recon_workspace,
                quality_preset=config.reconstruction.quality,
                timeout_seconds=config.reconstruction.timeout_seconds,
                binary_path=config.reconstruction.binary_path,
                keep_workspace=config.reconstruction.keep_workspace,
                additional_args=config.reconstruction.additional_args,
            )

            try:
                engine = ReconstructionRunner.get_engine(
                    config.reconstruction.backend,
                    binary_path=config.reconstruction.binary_path,
                )
                if not engine.is_available():
                    logger.warning(
                        "Reconstruction backend '%s' executable is not available on host system.",
                        config.reconstruction.backend,
                    )
                    reconstruction_result = ReconstructionResult(
                        mesh_path=None,
                        point_cloud_path=None,
                        camera_poses_path=None,
                        success=False,
                        backend_name=config.reconstruction.backend,
                        error_message=(
                            f"Reconstruction backend '{config.reconstruction.backend}' executable not found. "
                            "Ensure Meshroom is installed or configure 'binary_path'."
                        ),
                        input_frames_count=len(selected_copied_paths),
                    )
                else:
                    reconstruction_result = engine.reconstruct(selected_copied_paths, job_cfg)
            except Exception as e:
                logger.error("Reconstruction execution failed: %s", e)
                reconstruction_result = ReconstructionResult(
                    mesh_path=None,
                    point_cloud_path=None,
                    camera_poses_path=None,
                    success=False,
                    backend_name=config.reconstruction.backend,
                    error_message=str(e),
                    input_frames_count=len(selected_copied_paths),
                )

            # Write reconstruction.json report
            reconstruction_report_path = reports_dir / "reconstruction.json"
            recon_report_dict = {
                "run_id": run_id,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "backend": reconstruction_result.backend_name,
                "success": reconstruction_result.success,
                "input_frames": reconstruction_result.input_frames_count,
                "registered_cameras": reconstruction_result.registered_cameras_count,
                "registration_ratio": reconstruction_result.registration_ratio,
                "point_count": reconstruction_result.point_count,
                "mesh_generated": (
                    reconstruction_result.mesh_path is not None
                    and reconstruction_result.mesh_path.is_file()
                    and reconstruction_result.mesh_path.stat().st_size > 0
                ),
                "mesh_path": str(reconstruction_result.mesh_path) if reconstruction_result.mesh_path else None,
                "point_cloud_path": (
                    str(reconstruction_result.point_cloud_path)
                    if reconstruction_result.point_cloud_path
                    else None
                ),
                "camera_poses_path": (
                    str(reconstruction_result.camera_poses_path)
                    if reconstruction_result.camera_poses_path
                    else None
                ),
                "execution_time_seconds": reconstruction_result.execution_time_seconds,
                "workspace_dir": str(recon_workspace),
                "error_message": reconstruction_result.error_message,
            }
            with open(reconstruction_report_path, "w", encoding="utf-8") as rf:
                json.dump(recon_report_dict, rf, indent=2)

        return Phase1Result(
            run_id=run_id,
            run_dir=base_run_dir,
            video_artifact=video_artifact,
            frame_set_artifact=frame_set_artifact,
            capture_analysis_artifact=final_capture_artifact,
            metadata_report_path=metadata_report_path,
            capture_report_path=capture_report_path,
            selected_frames_dir=selected_frames_dir,
            raw_frames_dir=raw_frames_dir,
            quality_results=quality_results,
            reconstruction_result=reconstruction_result,
            reconstruction_report_path=reconstruction_report_path,
        )
    finally:
        file_handler.flush()
        loom_logger.removeHandler(file_handler)
        file_handler.close()

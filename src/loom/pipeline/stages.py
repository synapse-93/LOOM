"""Abstract interface and concrete stages for LOOM pipeline execution."""

from __future__ import annotations

import json
import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generic, TypeVar

from loom.capture.quality import FrameQualityAssessor, FrameQualityResult
from loom.config.models import LoomConfig
from loom.pipeline.artifacts import (
    BaseArtifact,
    CaptureAnalysisArtifact,
    FrameSetArtifact,
    VideoArtifact,
)
from loom.utils.paths import ensure_directory
from loom.video.frames import FrameExtractor
from loom.video.ingest import VideoIngestor

logger = logging.getLogger(__name__)

InputArtifactT = TypeVar("InputArtifactT", bound=BaseArtifact)
OutputArtifactT = TypeVar("OutputArtifactT", bound=BaseArtifact)


class PipelineStage(ABC, Generic[InputArtifactT, OutputArtifactT]):
    """Abstract base contract for a discrete, testable pipeline stage."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def execute(self, input_artifact: InputArtifactT, config: LoomConfig) -> OutputArtifactT:
        """Execute stage processing logic on input artifact."""
        ...

    def dry_run(self, input_artifact: InputArtifactT, config: LoomConfig) -> bool:
        """Verify preconditions and artifact validity without executing compute."""
        return input_artifact is not None


class VideoIngestStage(PipelineStage[BaseArtifact, VideoArtifact]):
    """Stage 1: Validate input video container and extract stream metadata."""

    def __init__(self, name: str = "video_ingest") -> None:
        super().__init__(name=name)

    def execute(self, input_artifact: BaseArtifact, config: LoomConfig) -> VideoArtifact:
        if config.input_video is None:
            raise ValueError("Input video path is not specified in configuration.")
        ingestor = VideoIngestor()
        return ingestor.ingest(config.input_video)


class FrameExtractionStage(PipelineStage[VideoArtifact, FrameSetArtifact]):
    """Stage 2: Sequentially stream and sample video frames to disk."""

    def __init__(
        self,
        name: str = "frame_extraction",
        output_dir: Path | None = None,
    ) -> None:
        super().__init__(name=name)
        self._output_dir = output_dir

    def execute(self, input_artifact: VideoArtifact, config: LoomConfig) -> FrameSetArtifact:
        dest_dir = self._output_dir or (config.output_dir / "frames" / "raw")
        extractor = FrameExtractor(config=config.video)
        return extractor.extract(input_artifact.video_path, dest_dir)


class CaptureQualityStage(PipelineStage[FrameSetArtifact, CaptureAnalysisArtifact]):
    """Stage 3: Assess frame sharpness, exposure, contrast, and redundancy."""

    def __init__(
        self,
        name: str = "capture_quality",
        selected_dir: Path | None = None,
        report_dir: Path | None = None,
    ) -> None:
        super().__init__(name=name)
        self._selected_dir = selected_dir
        self._report_dir = report_dir

    def execute(self, input_artifact: FrameSetArtifact, config: LoomConfig) -> CaptureAnalysisArtifact:
        assessor = FrameQualityAssessor(config=config.capture)
        artifact, results = assessor.assess_and_filter(input_artifact.frame_paths)

        # Copy selected frames to dedicated selected/ directory if specified
        if self._selected_dir is not None:
            sel_dir = ensure_directory(self._selected_dir)
            selected_copied: list[Path] = []
            for frame_path in artifact.selected_frames:
                target_dest = sel_dir / frame_path.name
                shutil.copy2(frame_path, target_dest)
                selected_copied.append(target_dest)
            artifact = CaptureAnalysisArtifact(
                stage_name=artifact.stage_name,
                selected_frames=selected_copied,
                rejected_frames=artifact.rejected_frames,
                average_sharpness=artifact.average_sharpness,
                coverage_score=artifact.coverage_score,
                guidance_notes=artifact.guidance_notes,
                metadata=artifact.metadata,
            )

        # Write capture analysis report JSON if report_dir is specified
        if self._report_dir is not None:
            rep_dir = ensure_directory(self._report_dir)
            report_file = rep_dir / "capture_analysis.json"
            report_data = {
                "summary": artifact.metadata,
                "guidance_notes": artifact.guidance_notes,
                "average_sharpness": artifact.average_sharpness,
                "diversity_score": artifact.coverage_score,
                "frames": [
                    {
                        "path": str(r.frame_path),
                        "filename": r.frame_path.name,
                        "sharpness": r.sharpness,
                        "brightness": r.brightness,
                        "contrast": r.contrast,
                        "is_accepted": r.is_accepted,
                        "rejection_reasons": list(r.rejection_reasons),
                    }
                    for r in results
                ],
            }
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2)

        return artifact

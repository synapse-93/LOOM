"""Pipeline orchestration and artifact contracts for LOOM."""

from __future__ import annotations

from loom.pipeline.artifacts import (
    BaseArtifact,
    CaptureAnalysisArtifact,
    ExportArtifact,
    FrameSetArtifact,
    MeshArtifact,
    PointCloudArtifact,
    PrintabilityArtifact,
    ReconstructionArtifact,
    ScaledMeshArtifact,
    ValidationArtifact,
    VideoArtifact,
)
from loom.pipeline.runner import Phase1Result, PipelineRunner, run_phase1_pipeline
from loom.pipeline.stages import (
    CaptureQualityStage,
    FrameExtractionStage,
    PipelineStage,
    VideoIngestStage,
)

__all__ = [
    "BaseArtifact",
    "CaptureAnalysisArtifact",
    "CaptureQualityStage",
    "ExportArtifact",
    "FrameExtractionStage",
    "FrameSetArtifact",
    "MeshArtifact",
    "Phase1Result",
    "PipelineRunner",
    "PipelineStage",
    "PointCloudArtifact",
    "PrintabilityArtifact",
    "ReconstructionArtifact",
    "ScaledMeshArtifact",
    "ValidationArtifact",
    "VideoArtifact",
    "VideoIngestStage",
    "run_phase1_pipeline",
]

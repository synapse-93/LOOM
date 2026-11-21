"""Pipeline orchestration and artifact contracts for LOOM."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loom.pipeline.artifacts import (
    BaseArtifact,
    CaptureAnalysisArtifact,
    ExportArtifact,
    FrameSetArtifact,
    MeshArtifact,
    PointCloudArtifact,
    PrintabilityArtifact,
    ReconstructionArtifact,
    ReconstructionCheckpointsArtifact,
    ScaledMeshArtifact,
    ValidationArtifact,
    VideoArtifact,
    compute_ply_density,
    export_reconstruction_checkpoints,
    export_sparse_points_ply,
    read_ply_vertex_count,
)

if TYPE_CHECKING:
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
    "ReconstructionCheckpointsArtifact",
    "ScaledMeshArtifact",
    "ValidationArtifact",
    "VideoArtifact",
    "VideoIngestStage",
    "compute_ply_density",
    "export_reconstruction_checkpoints",
    "export_sparse_points_ply",
    "read_ply_vertex_count",
    "run_phase1_pipeline",
]


def __getattr__(name: str) -> Any:
    if name in {"Phase1Result", "PipelineRunner", "run_phase1_pipeline"}:
        import loom.pipeline.runner as _runner

        return getattr(_runner, name)
    if name in {"CaptureQualityStage", "FrameExtractionStage", "PipelineStage", "VideoIngestStage"}:
        import loom.pipeline.stages as _stages

        return getattr(_stages, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""3D Reconstruction abstraction and engine adapters for LOOM."""

from __future__ import annotations

from loom.reconstruction.base import ReconstructionEngine
from loom.reconstruction.colmap import (
    ColmapAdapter,
    ColmapDenseArtifact,
    ColmapSparseArtifact,
    SparseModelInfo,
    SparseSceneMetadata,
)
from loom.reconstruction.gaussian_2dgs import (
    Gaussian2DGSConfig,
    Gaussian2DGSReconstructor,
    Trained2DGSModel,
)
from loom.reconstruction.masking import ForegroundMasker, MaskingResult
from loom.reconstruction.models import ReconstructionJobConfig, ReconstructionResult
from loom.reconstruction.runner import ReconstructionRunner
from loom.reconstruction.tsdf_mesh import (
    TsdfExtractionConfig,
    TsdfExtractionResult,
    TsdfMeshExtractor,
)
from loom.reconstruction.visual_hull import (
    VisualHullConfig,
    VisualHullFilter,
    VisualHullResult,
)

__all__ = [
    "ColmapAdapter",
    "ColmapDenseArtifact",
    "ColmapSparseArtifact",
    "ForegroundMasker",
    "Gaussian2DGSConfig",
    "Gaussian2DGSReconstructor",
    "MaskingResult",
    "MeshroomAdapter",
    "ReconstructionEngine",
    "ReconstructionJobConfig",
    "ReconstructionResult",
    "ReconstructionRunner",
    "SparseModelInfo",
    "SparseSceneMetadata",
    "Trained2DGSModel",
    "TsdfExtractionConfig",
    "TsdfExtractionResult",
    "TsdfMeshExtractor",
    "VisualHullConfig",
    "VisualHullFilter",
    "VisualHullResult",
]

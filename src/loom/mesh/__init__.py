"""3D Mesh processing, repair, topology analysis, and surface reconstruction for LOOM."""

from __future__ import annotations

from loom.mesh.cleanup import MeshCleaner
from loom.mesh.components import MeshComponentAnalyzer
from loom.mesh.diagnostics import MeshDiagnostics
from loom.mesh.exceptions import (
    MeshError,
    MeshFormatError,
    MeshInvalidError,
    MeshLoadError,
    MeshProcessingError,
)
from loom.mesh.models import (
    CleanupActionResult,
    ComponentActionResult,
    ComponentInfo,
    GeometryDiagnostics,
    MeshProcessingResult,
    MeshProcessingStage,
    RepairActionResult,
)
from loom.mesh.processor import MeshProcessor
from loom.mesh.reconstruction import SurfaceReconstructor
from loom.mesh.repair import MeshRepairer
from loom.mesh.topology import MeshTopologyAnalyzer

__all__ = [
    "CleanupActionResult",
    "ComponentActionResult",
    "ComponentInfo",
    "GeometryDiagnostics",
    "MeshCleaner",
    "MeshComponentAnalyzer",
    "MeshDiagnostics",
    "MeshError",
    "MeshFormatError",
    "MeshInvalidError",
    "MeshLoadError",
    "MeshProcessingError",
    "MeshProcessingResult",
    "MeshProcessingStage",
    "MeshProcessor",
    "MeshRepairer",
    "MeshTopologyAnalyzer",
    "RepairActionResult",
    "SurfaceReconstructor",
]

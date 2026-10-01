"""Typed data models and diagnostic reporting structures for Phase 3 mesh processing."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class MeshProcessingStage(str, Enum):
    """Sequential stages of Phase 3 mesh processing."""

    VALIDATE_INPUT = "validate_input"
    DIAGNOSTICS_BEFORE = "diagnostics_before"
    ANALYZE_COMPONENTS = "analyze_components"
    CLEAN_INVALID = "clean_invalid_geometry"
    REPAIR_DEFECTS = "repair_defects"
    NORMALIZE = "normalize_mesh"
    DIAGNOSTICS_AFTER = "diagnostics_after"
    EXPORT_REPORT = "export_report"


@dataclass(frozen=True)
class GeometryDiagnostics:
    """Read-only diagnostic metrics describing the geometric and topological state of a mesh."""

    vertex_count: int
    face_count: int
    bounding_box_min: tuple[float, float, float]
    bounding_box_max: tuple[float, float, float]
    extents: tuple[float, float, float]
    surface_area: Optional[float] = None
    volume: Optional[float] = None
    component_count: int = 1
    boundary_edge_count: int = 0
    boundary_loop_count: int = 0
    non_manifold_edge_count: int = 0
    non_manifold_vertex_count: int = 0
    is_watertight: bool = False
    is_winding_consistent: bool = False
    euler_characteristic: int = 0
    nan_vertex_count: int = 0
    infinite_vertex_count: int = 0
    invalid_face_count: int = 0
    degenerate_face_count: int = 0
    duplicate_face_count: int = 0
    unreferenced_vertex_count: int = 0
    status: str = "VALID"  # Options: 'VALID', 'WARNING', 'ERROR'
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_nan_or_inf(self) -> bool:
        """Return True if vertex coordinates contain any NaN or Inf values."""
        return self.nan_vertex_count > 0 or self.infinite_vertex_count > 0

    @property
    def bounding_box(self) -> dict[str, tuple[float, float, float]]:
        """Dictionary access to bounding box min and max points."""
        return {"min": self.bounding_box_min, "max": self.bounding_box_max}

    def to_dict(self) -> dict[str, Any]:
        """Convert diagnostics to a JSON-serializable dictionary."""
        d = asdict(self)
        # Format floating points rounded for clean JSON
        if d["surface_area"] is not None:
            d["surface_area"] = round(d["surface_area"], 4)
        if d["volume"] is not None:
            d["volume"] = round(d["volume"], 4)
        d["bounding_box_min"] = [round(x, 4) for x in d["bounding_box_min"]]
        d["bounding_box_max"] = [round(x, 4) for x in d["bounding_box_max"]]
        d["extents"] = [round(x, 4) for x in d["extents"]]
        return d



@dataclass(frozen=True)
class ComponentInfo:
    """Diagnostic profile for a single connected component."""

    index: int
    vertex_count: int
    face_count: int
    bounding_box_min: tuple[float, float, float]
    bounding_box_max: tuple[float, float, float]
    surface_area: float
    is_kept: bool = True

    @property
    def component_id(self) -> int:
        return self.index

    def to_dict(self) -> dict[str, Any]:

        return {
            "index": self.index,
            "vertex_count": self.vertex_count,
            "face_count": self.face_count,
            "bounding_box_min": [round(x, 4) for x in self.bounding_box_min],
            "bounding_box_max": [round(x, 4) for x in self.bounding_box_max],
            "surface_area": round(self.surface_area, 4),
            "is_kept": self.is_kept,
        }


@dataclass(frozen=True)
class ComponentActionResult:
    """Summary of connected component filtering action."""

    strategy: str
    components_before: int
    components_after: int
    removed_components: int
    removed_faces: int
    removed_vertices: int
    component_details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CleanupActionResult:
    """Summary of invalid and degenerate geometry cleanup actions."""

    invalid_vertices_removed: int
    invalid_faces_removed: int
    degenerate_faces_removed: int
    duplicate_faces_removed: int
    unreferenced_vertices_removed: int
    vertices_before: int = 0
    vertices_after: int = 0
    faces_before: int = 0
    faces_after: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RepairActionResult:
    """Summary of topological defect and hole repair actions."""

    boundary_loops_before: int
    boundary_edges_before: int
    repairs_attempted: int
    repairs_successful: int
    remaining_boundary_loops: int
    remaining_boundary_edges: int
    normals_unified: bool = False
    faces_added: int = 0
    defect_details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def holes_detected(self) -> int:
        return self.boundary_loops_before

    @property
    def holes_eligible(self) -> int:
        return self.repairs_attempted

    @property
    def holes_repaired(self) -> int:
        return self.repairs_successful

    @property
    def remaining_defects(self) -> int:
        return self.remaining_boundary_loops

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["holes_detected"] = self.holes_detected
        d["holes_eligible"] = self.holes_eligible
        d["holes_repaired"] = self.holes_repaired
        d["remaining_defects"] = self.remaining_defects
        return d



@dataclass
class MeshProcessingResult:
    """Consolidated terminal output and diagnostic summary of Phase 3 mesh processing."""

    success: bool = False
    input_mesh_path: Optional[Path] = None
    output_mesh_path: Optional[Path] = None
    execution_time_seconds: float = 0.0
    diagnostics_before: Optional[GeometryDiagnostics] = None
    diagnostics_after: Optional[GeometryDiagnostics] = None
    components_action: Optional[ComponentActionResult] = None
    cleanup_action: Optional[CleanupActionResult] = None
    repair_action: Optional[RepairActionResult] = None
    warnings: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    status: str = "SUCCESS"  # 'SUCCESS', 'WARNING', 'FAILED'
    stages_completed: list[str] = field(default_factory=list)

    @property
    def vertex_count_before(self) -> int:
        return self.diagnostics_before.vertex_count if self.diagnostics_before else 0

    @property
    def vertex_count_after(self) -> int:
        return self.diagnostics_after.vertex_count if self.diagnostics_after else 0

    @property
    def face_count_before(self) -> int:
        return self.diagnostics_before.face_count if self.diagnostics_before else 0

    @property
    def face_count_after(self) -> int:
        return self.diagnostics_after.face_count if self.diagnostics_after else 0

    @property
    def component_count_before(self) -> int:
        return self.diagnostics_before.component_count if self.diagnostics_before else 0

    @property
    def component_count_after(self) -> int:
        return self.diagnostics_after.component_count if self.diagnostics_after else 0

    @property
    def removed_components(self) -> int:
        return self.components_action.removed_components if self.components_action else 0

    @property
    def degenerate_faces_before(self) -> int:
        return self.diagnostics_before.degenerate_face_count if self.diagnostics_before else 0

    @property
    def degenerate_faces_removed(self) -> int:
        return self.cleanup_action.degenerate_faces_removed if self.cleanup_action else 0

    @property
    def boundary_defects_before(self) -> int:
        return self.diagnostics_before.boundary_loop_count if self.diagnostics_before else 0

    @property
    def repairs_attempted(self) -> int:
        return self.repair_action.repairs_attempted if self.repair_action else 0

    @property
    def repairs_successful(self) -> int:
        return self.repair_action.repairs_successful if self.repair_action else 0

    @property
    def remaining_boundary_defects(self) -> int:
        return self.repair_action.remaining_boundary_loops if self.repair_action else 0

    @property
    def processing_time_s(self) -> float:
        return self.execution_time_seconds

    @property
    def before_diagnostics(self) -> Optional[GeometryDiagnostics]:
        return self.diagnostics_before

    @property
    def after_diagnostics(self) -> Optional[GeometryDiagnostics]:
        return self.diagnostics_after

    def to_dict(self) -> dict[str, Any]:
        """Generate structured JSON-serializable report dictionary."""
        return {
            "success": self.success,
            "status": self.status,
            "input_mesh_path": str(self.input_mesh_path) if self.input_mesh_path else None,
            "output_mesh_path": str(self.output_mesh_path) if self.output_mesh_path else None,
            "execution_time_seconds": round(self.execution_time_seconds, 4),
            "vertex_count_before": self.vertex_count_before,
            "vertex_count_after": self.vertex_count_after,
            "face_count_before": self.face_count_before,
            "face_count_after": self.face_count_after,
            "component_count_before": self.component_count_before,
            "component_count_after": self.component_count_after,
            "removed_components": self.removed_components,
            "degenerate_faces_before": self.degenerate_faces_before,
            "degenerate_faces_removed": self.degenerate_faces_removed,
            "boundary_defects_before": self.boundary_defects_before,
            "repairs_attempted": self.repairs_attempted,
            "repairs_successful": self.repairs_successful,
            "remaining_boundary_defects": self.remaining_boundary_defects,
            "stages_completed": list(self.stages_completed),
            "diagnostics_before": self.diagnostics_before.to_dict() if self.diagnostics_before else None,
            "diagnostics_after": self.diagnostics_after.to_dict() if self.diagnostics_after else None,
            "actions": {
                "components": self.components_action.to_dict() if self.components_action else None,
                "cleanup": self.cleanup_action.to_dict() if self.cleanup_action else None,
                "repair": self.repair_action.to_dict() if self.repair_action else None,
            },
            "warnings": self.warnings,
            "error_message": self.error_message,
        }


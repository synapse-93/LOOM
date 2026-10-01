"""Typed data models and reporting structures for Phase 4 metric scaling."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class ReferenceMarker:
    """Specification of a known physical reference marker."""

    marker_type: str = "aruco"
    marker_id: int = 0
    known_size_mm: float = 50.0
    dictionary: str = "DICT_4X4_50"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "marker_type": str(self.marker_type),
            "marker_id": int(self.marker_id),
            "known_size_mm": round(float(self.known_size_mm), 4),
            "dictionary": str(self.dictionary),
        }


@dataclass(frozen=True)
class MarkerObservation:
    """Detected 2D/3D fiducial marker observation."""

    marker_id: int
    corners_2d: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ]
    frame_path: Optional[str] = None
    is_valid: bool = True
    edge_lengths_2d: Optional[list[float]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "marker_id": int(self.marker_id),
            "corners_2d": [list(c) for c in self.corners_2d],
            "frame_path": str(self.frame_path) if self.frame_path else None,
            "is_valid": bool(self.is_valid),
            "edge_lengths_2d": [round(float(x), 4) for x in self.edge_lengths_2d] if self.edge_lengths_2d else None,
        }


@dataclass(frozen=True)
class ReferenceMeasurement:
    """Aggregated measurements of the reference object in reconstructed coordinate units."""

    reconstructed_size: float
    observations: list[float]
    mean: float
    median: float
    std_dev: float
    min_val: float
    max_val: float
    spread: float
    measurement_count: int
    units: str = "reconstructed_units"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "reconstructed_size": round(float(self.reconstructed_size), 6),
            "observations": [round(float(x), 6) for x in self.observations],
            "mean": round(float(self.mean), 6),
            "median": round(float(self.median), 6),
            "std_dev": round(float(self.std_dev), 6),
            "min_val": round(float(self.min_val), 6),
            "max_val": round(float(self.max_val), 6),
            "spread": round(float(self.spread), 6),
            "measurement_count": int(self.measurement_count),
            "units": str(self.units),
        }


@dataclass(frozen=True)
class ScaleEstimate:
    """Calculated metric scale estimation from reference measurement."""

    known_physical_size_mm: float
    reconstructed_reference_size: float
    scale_factor: float
    variance: float = 0.0
    confidence: float = 1.0
    method: str = "ratio"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "known_physical_size_mm": round(float(self.known_physical_size_mm), 4),
            "reconstructed_reference_size": round(float(self.reconstructed_reference_size), 6),
            "scale_factor": round(float(self.scale_factor), 6),
            "variance": round(float(self.variance), 8),
            "confidence": round(float(self.confidence), 4),
            "method": str(self.method),
        }


@dataclass
class ScalingResult:
    """Complete summary and diagnostic output of the Phase 4 metric scaling operation."""

    input_mesh_path: str
    output_mesh_path: Optional[str] = None
    status: str = "SUCCESS"  # SUCCESS, FAILED, SKIPPED, INVALID_REFERENCE
    reference: Optional[dict[str, Any]] = None
    measurement: Optional[dict[str, Any]] = None
    scale_estimate: Optional[dict[str, Any]] = None
    scale_factor: float = 1.0
    transformation_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounds_before: Optional[list[list[float]]] = None
    bounds_after: Optional[list[list[float]]] = None
    vertex_count_before: int = 0
    vertex_count_after: int = 0
    face_count_before: int = 0
    face_count_after: int = 0
    execution_time_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Convenience property matching LOOM pipeline stage convention."""
        return self.status == "SUCCESS"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "status": str(self.status),
            "success": self.success,
            "input_mesh_path": str(self.input_mesh_path),
            "output_mesh_path": str(self.output_mesh_path) if self.output_mesh_path else None,
            "scale_factor": round(float(self.scale_factor), 6),
            "transformation_origin": [round(float(x), 4) for x in self.transformation_origin],
            "reference": self.reference,
            "measurement": self.measurement,
            "scale_estimate": self.scale_estimate,
            "bounds_before": self.bounds_before,
            "bounds_after": self.bounds_after,
            "vertex_count_before": int(self.vertex_count_before),
            "vertex_count_after": int(self.vertex_count_after),
            "face_count_before": int(self.face_count_before),
            "face_count_after": int(self.face_count_after),
            "execution_time_seconds": round(float(self.execution_time_seconds), 4),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

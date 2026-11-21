"""Printability validation gate enforcing manufacturing readiness criteria."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import trimesh

from loom.printability.exceptions import PrintabilityValidationError
from loom.printability.manifold import ManifoldChecker
from loom.printability.watertight import WatertightChecker
from loom.utils.logging import get_logger

logger = get_logger("loom.printability.gate")


@dataclass(frozen=True)
class PrintabilityValidationResult:
    """Consolidated results of manufacturing readiness validation checks."""

    passed: bool
    is_watertight: bool
    is_manifold: bool
    is_positive_volume: bool
    boundary_edge_count: int
    non_manifold_edge_count: int
    non_manifold_vertex_count: int
    volume_mm3: float
    triangle_count: int
    vertex_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Convert validation result to dictionary representation."""
        return {
            "passed": self.passed,
            "is_watertight": self.is_watertight,
            "is_manifold": self.is_manifold,
            "is_positive_volume": self.is_positive_volume,
            "boundary_edge_count": self.boundary_edge_count,
            "non_manifold_edge_count": self.non_manifold_edge_count,
            "non_manifold_vertex_count": self.non_manifold_vertex_count,
            "volume_mm3": self.volume_mm3,
            "triangle_count": self.triangle_count,
            "vertex_count": self.vertex_count,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class PrintabilityGate:
    """Enforces manufacturing readiness checks on 3D meshes before STL export.

    Gate Criteria:
        1. Watertight check: Mesh must be a closed 2-manifold with boundary edges == 0.
        2. Manifold check: Non-manifold edge count == 0 and non-manifold vertex count == 0.
        3. Volume check: Mesh must enclose a strictly positive volume (> 0.0 mm^3).
    """

    def __init__(self) -> None:
        self._watertight_checker = WatertightChecker()
        self._manifold_checker = ManifoldChecker()

    @staticmethod
    def _load_mesh(mesh_input: Path | str | trimesh.Trimesh) -> trimesh.Trimesh:
        """Load and resolve a trimesh.Trimesh instance from a path or object."""
        if isinstance(mesh_input, trimesh.Trimesh):
            return mesh_input
        p = Path(mesh_input).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Input mesh file does not exist: {p}")
        loaded = trimesh.load(str(p), process=False)
        if isinstance(loaded, trimesh.Scene):
            if len(loaded.geometry) == 0:
                raise ValueError(f"Mesh file contains no geometry: {p}")
            return trimesh.util.concatenate(list(loaded.geometry.values()))
        return loaded

    def validate(self, mesh_path: Path | str | trimesh.Trimesh) -> PrintabilityValidationResult:
        """Evaluate 3D mesh against manufacturing readiness gate criteria.

        Args:
            mesh_path: Path to mesh file or loaded trimesh instance.

        Returns:
            Populated PrintabilityValidationResult with pass/fail status and defect counts.
        """
        mesh = self._load_mesh(mesh_path)
        v_count = len(mesh.vertices)
        t_count = len(mesh.faces)
        errors: list[str] = []
        warnings: list[str] = []

        if v_count == 0 or t_count == 0:
            errors.append(f"Mesh is empty (vertices={v_count}, faces={t_count}).")
            return PrintabilityValidationResult(
                passed=False,
                is_watertight=False,
                is_manifold=False,
                is_positive_volume=False,
                boundary_edge_count=0,
                non_manifold_edge_count=0,
                non_manifold_vertex_count=0,
                volume_mm3=0.0,
                triangle_count=0,
                vertex_count=0,
                errors=errors,
                warnings=warnings,
            )

        # 1. Watertight & Boundary Edges Check
        is_watertight, boundary_edges, volume = self._watertight_checker.check_watertight(mesh)
        if boundary_edges > 0:
            errors.append(
                f"Watertight check failed: mesh has {boundary_edges} open boundary edges (expected 0)."
            )

        # 2. Manifold Geometry Check
        is_manifold, non_manifold_edges, non_manifold_verts = self._manifold_checker.check_manifold(mesh)
        if non_manifold_edges > 0:
            errors.append(
                f"Edge manifold check failed: {non_manifold_edges} non-manifold edges detected (expected 0)."
            )
        if non_manifold_verts > 0:
            errors.append(
                f"Vertex manifold check failed: {non_manifold_verts} non-manifold vertices detected (expected 0)."
            )

        # 3. Positive Volume Check
        is_positive_volume = volume > 0.0
        if not is_positive_volume:
            errors.append(
                f"Volume check failed: mesh volume is non-positive ({volume:.4f} mm^3, expected > 0.0)."
            )

        passed = len(errors) == 0

        logger.info(
            "Printability gate validation %s for mesh (%d verts, %d faces): "
            "watertight=%s (boundary=%d), manifold=%s (edges=%d, verts=%d), volume=%.2f mm^3",
            "PASSED" if passed else "FAILED",
            v_count,
            t_count,
            is_watertight,
            boundary_edges,
            is_manifold,
            non_manifold_edges,
            non_manifold_verts,
            volume,
        )

        return PrintabilityValidationResult(
            passed=passed,
            is_watertight=is_watertight,
            is_manifold=is_manifold,
            is_positive_volume=is_positive_volume,
            boundary_edge_count=boundary_edges,
            non_manifold_edge_count=non_manifold_edges,
            non_manifold_vertex_count=non_manifold_verts,
            volume_mm3=volume,
            triangle_count=t_count,
            vertex_count=v_count,
            errors=errors,
            warnings=warnings,
        )

    def enforce_gate(self, mesh_path: Path | str | trimesh.Trimesh) -> PrintabilityValidationResult:
        """Validate mesh and raise PrintabilityValidationError if gate fails.

        Args:
            mesh_path: Path to mesh file or loaded trimesh instance.

        Returns:
            PrintabilityValidationResult if validation passed.

        Raises:
            PrintabilityValidationError: If any printability criteria are violated.
        """
        result = self.validate(mesh_path)
        if not result.passed:
            err_msg = "; ".join(result.errors)
            raise PrintabilityValidationError(f"Mesh failed printability validation gate: {err_msg}")
        return result


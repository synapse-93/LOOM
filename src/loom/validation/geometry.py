"""Geometric deviation and distance field comparison interfaces."""

from __future__ import annotations

from pathlib import Path


class GeometryComparator:
    """Computes point-to-mesh and Hausdorff distance metrics between models."""

    def compute_hausdorff_distance(self, mesh_a_path: Path, mesh_b_path: Path) -> tuple[float, float]:
        """Compute directed and symmetric Hausdorff distance (mean, max) between two meshes.

        Raises:
            NotImplementedError: Scheduled for Phase 5.
        """
        raise NotImplementedError("Hausdorff distance computation scheduled for Phase 5.")

    def compute_surface_deviation(self, test_mesh_path: Path, reference_cad_path: Path) -> dict[str, float]:
        """Compute statistical deviation metrics (RMS, mean, max) against ground-truth CAD.

        Raises:
            NotImplementedError: Scheduled for Phase 5.
        """
        raise NotImplementedError("Surface deviation computation scheduled for Phase 5.")

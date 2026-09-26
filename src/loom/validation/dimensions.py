"""Physical dimension and bounding box measurement interfaces."""

from __future__ import annotations

from pathlib import Path
from loom.geometry.measurements import BoundingBox3D


class DimensionAnalyzer:
    """Measures physical extents and principle axes of a reconstructed 3D mesh."""

    def compute_bounding_box(self, mesh_path: Path) -> BoundingBox3D:
        """Compute exact 3D axis-aligned bounding box of mesh vertices in mm.

        Raises:
            NotImplementedError: Scheduled for Phase 5.
        """
        raise NotImplementedError("Mesh bounding box measurement scheduled for Phase 5.")

    def compute_principal_dimensions(self, mesh_path: Path) -> tuple[float, float, float]:
        """Compute oriented principal bounding dimensions (length, width, height) in mm.

        Raises:
            NotImplementedError: Scheduled for Phase 5.
        """
        raise NotImplementedError("Principal dimension measurement scheduled for Phase 5.")

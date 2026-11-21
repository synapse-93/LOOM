"""Physical dimension and bounding box measurement interfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import numpy as np
import trimesh

from loom.geometry.coordinates import Point3D
from loom.geometry.measurements import BoundingBox3D
from loom.utils.logging import get_logger

logger = get_logger("loom.validation.dimensions")


class DimensionAnalyzer:
    """Measures physical extents and principal axes of a reconstructed 3D mesh."""

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

    def compute_bounding_box(self, mesh_path: Path | str | trimesh.Trimesh) -> BoundingBox3D:
        """Compute exact 3D axis-aligned bounding box (AABB) of mesh vertices in mm.

        Args:
            mesh_path: Path to mesh file or loaded trimesh instance.

        Returns:
            BoundingBox3D with min_point and max_point coordinates.
        """
        mesh = self._load_mesh(mesh_path)
        if len(mesh.vertices) == 0:
            raise ValueError("Mesh has 0 vertices.")

        min_coords = [float(x) for x in mesh.bounds[0]]
        max_coords = [float(x) for x in mesh.bounds[1]]

        return BoundingBox3D(
            min_point=Point3D(min_coords[0], min_coords[1], min_coords[2]),
            max_point=Point3D(max_coords[0], max_coords[1], max_coords[2]),
        )

    def compute_principal_dimensions(
        self,
        mesh_path: Path | str | trimesh.Trimesh,
    ) -> tuple[float, float, float]:
        """Compute oriented principal bounding dimensions (Length, Width, Height) in physical millimeters.

        Calculates the Oriented Bounding Box (OBB) using convex-hull oriented bounds
        with a deterministic PCA (Principal Component Analysis) covariance fallback for
        degenerate or coplanar geometry. Extents are returned sorted descending: Length >= Width >= Height.

        Args:
            mesh_path: Path to mesh file or loaded trimesh instance.

        Returns:
            Tuple of (length_mm, width_mm, height_mm).
        """
        mesh = self._load_mesh(mesh_path)
        if len(mesh.vertices) == 0:
            raise ValueError("Mesh has 0 vertices.")

        extents_list: list[float]
        try:
            # Primary: Minimum-volume Oriented Bounding Box
            _, extents = trimesh.bounds.oriented_bounds(mesh)
            extents_list = [float(e) for e in extents]
        except Exception:
            # Robust fallback: PCA on vertex covariance
            v = np.asarray(mesh.vertices, dtype=np.float64)
            centered = v - np.mean(v, axis=0)
            cov = np.cov(centered, rowvar=False)
            evals, evecs = np.linalg.eigh(cov)
            projected = centered @ evecs
            extents_list = [float(e) for e in (np.max(projected, axis=0) - np.min(projected, axis=0))]

        # Sort descending: Length >= Width >= Height
        sorted_extents = sorted(extents_list, reverse=True)
        length_mm = float(sorted_extents[0])
        width_mm = float(sorted_extents[1])
        height_mm = float(sorted_extents[2])

        logger.debug(
            "Computed OBB principal dimensions: Length=%.2f mm, Width=%.2f mm, Height=%.2f mm",
            length_mm,
            width_mm,
            height_mm,
        )
        return (length_mm, width_mm, height_mm)

    def compute_oriented_bounding_box(
        self,
        mesh_path: Path | str | trimesh.Trimesh,
    ) -> dict[str, Any]:
        """Compute oriented bounding box summary dictionary."""
        length_mm, width_mm, height_mm = self.compute_principal_dimensions(mesh_path)
        return {
            "length_mm": length_mm,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "volume_mm3": length_mm * width_mm * height_mm,
            "dimensions_tuple": (length_mm, width_mm, height_mm),
        }

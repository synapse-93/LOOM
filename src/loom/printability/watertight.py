"""Watertightness (closed volume) verification interfaces."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import trimesh

from loom.utils.logging import get_logger

logger = get_logger("loom.printability.watertight")


class WatertightChecker:
    """Verifies that a 3D mesh encloses a positive volume with no open boundary edges."""

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

    def get_boundary_edge_count(self, mesh_path: Path | str | trimesh.Trimesh) -> int:
        """Count open boundary edges (edges shared by exactly one face).

        In a closed 2-manifold surface, every edge must be shared by exactly two faces.
        Boundary edges indicate unclosed holes or open borders.
        """
        mesh = self._load_mesh(mesh_path)
        if len(mesh.faces) == 0:
            return 0
        edges = mesh.edges_sorted
        _, counts = np.unique(edges, axis=0, return_counts=True)
        return int(np.sum(counts == 1))

    def get_volume(self, mesh_path: Path | str | trimesh.Trimesh) -> float:
        """Compute enclosed physical volume in cubic millimeters (mm^3)."""
        mesh = self._load_mesh(mesh_path)
        if not mesh.is_volume or mesh.volume is None:
            return 0.0
        return float(mesh.volume)

    def is_watertight(self, mesh_path: Path | str | trimesh.Trimesh) -> bool:
        """Check if mesh is a closed 2-manifold with zero boundary edges and positive volume.

        Returns:
            True if boundary edges == 0, mesh.is_watertight is True, and volume > 0.
        """
        mesh = self._load_mesh(mesh_path)
        boundary_count = self.get_boundary_edge_count(mesh)
        volume = self.get_volume(mesh)
        is_closed = boundary_count == 0 and bool(mesh.is_watertight)
        is_positive_vol = volume > 0.0

        logger.debug(
            "Watertight check: boundary_edges=%d, is_watertight=%s, volume=%.3f mm^3",
            boundary_count,
            mesh.is_watertight,
            volume,
        )
        return bool(is_closed and is_positive_vol)

    def check_watertight(self, mesh_path: Path | str | trimesh.Trimesh) -> tuple[bool, int, float]:
        """Perform comprehensive watertight analysis.

        Returns:
            Tuple of (is_watertight, boundary_edge_count, volume_mm3).
        """
        mesh = self._load_mesh(mesh_path)
        boundary_count = self.get_boundary_edge_count(mesh)
        volume = self.get_volume(mesh)
        watertight = (boundary_count == 0) and bool(mesh.is_watertight) and (volume > 0.0)
        return watertight, boundary_count, volume
